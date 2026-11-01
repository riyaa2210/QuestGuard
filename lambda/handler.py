"""Lambda handler – processes SQS delivery jobs.

Trigger: SQS event source mapping on the queueguard-events queue.

Features added in v0.2
----------------------
- HMAC-SHA256 signing: adds X-QueueGuard-Signature header using the endpoint's
  raw secret (identical format to GitHub/Stripe webhooks).
- Circuit-breaker integration: records success/failure outcomes and trips the
  breaker on consecutive failures.
- Alert evaluation: after each delivery outcome, active alert rules are checked
  synchronously using a single aggregation query.
- OTel trace context: trace_id / span_id from the SQS message are attached to
  all structured log entries.
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
import httpx
import structlog
from sqlalchemy import select

# Make app/ importable inside Lambda bundle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lambda.ai_explainer import explain_failure
from lambda.cloudwatch_logger import emit as cw_emit
from lambda.db import get_session
from app.models.endpoint import Endpoint, CircuitState
from app.models.event import AttemptStatus, DeliveryAttempt, EventStatus, WebhookEvent
from app.models.alert import AlertRule
from app.services.hmac_signing import sign_payload

logger = structlog.get_logger(__name__)

MAX_RETRY_ATTEMPTS = int(os.environ.get("MAX_RETRY_ATTEMPTS", "5"))
INITIAL_RETRY_DELAY_SECONDS = int(os.environ.get("INITIAL_RETRY_DELAY_SECONDS", "30"))
DELIVERY_TIMEOUT_SECONDS = int(os.environ.get("DELIVERY_TIMEOUT_SECONDS", "10"))
SQS_QUEUE_URL = os.environ.get("SQS_WEBHOOK_QUEUE_URL", "")
_LOCALSTACK = os.environ.get("LOCALSTACK_ENDPOINT", "")

_sqs_kwargs: dict = {"region_name": os.environ.get("AWS_REGION", "us-east-1")}
if _LOCALSTACK:
    _sqs_kwargs["endpoint_url"] = _LOCALSTACK
    _sqs_kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
    _sqs_kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")
_sqs_client = boto3.client("sqs", **_sqs_kwargs)


def _backoff_delay(attempt_number: int) -> int:
    """Exponential backoff: 30 s, 60 s, 120 s, … capped at 900 s (SQS max)."""
    delay = INITIAL_RETRY_DELAY_SECONDS * (2 ** (attempt_number - 1))
    return min(delay, 900)


def _re_enqueue(
    event_id: str,
    endpoint_id: str,
    event_type: str,
    payload: dict,
    attempt_number: int,
    trace_id: str = "",
    span_id: str = "",
) -> None:
    delay = _backoff_delay(attempt_number)
    body = json.dumps({
        "event_id": event_id,
        "endpoint_id": endpoint_id,
        "event_type": event_type,
        "payload": payload,
        "attempt_number": attempt_number,
        "trace_id": trace_id,
        "span_id": span_id,
    })
    attrs: dict = {
        "attempt_number": {"DataType": "Number", "StringValue": str(attempt_number)},
    }
    if trace_id:
        attrs["trace_id"] = {"DataType": "String", "StringValue": trace_id}
    _sqs_client.send_message(
        QueueUrl=SQS_QUEUE_URL,
        MessageBody=body,
        DelaySeconds=delay,
        MessageAttributes=attrs,
    )
    logger.info("retry_scheduled", event_id=event_id, next_attempt=attempt_number, delay_s=delay)


def _deliver(
    url: str,
    payload: dict,
    event_type: str,
    secret: Optional[str],
    trace_id: str = "",
) -> tuple[int, str, int]:
    """HTTP POST the payload; returns (status_code, body_truncated, duration_ms)."""
    headers = {
        "Content-Type": "application/json",
        "X-QueueGuard-Event": event_type,
        "User-Agent": "QueueGuard/0.2",
    }
    if secret:
        headers["X-QueueGuard-Signature"] = sign_payload(payload, secret)
    if trace_id:
        headers["X-Trace-Id"] = trace_id

    start = time.monotonic()
    with httpx.Client(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
        resp = client.post(url, json=payload, headers=headers)
    duration_ms = int((time.monotonic() - start) * 1000)
    return resp.status_code, resp.text[:4096], duration_ms


def _update_circuit_breaker(endpoint: Endpoint, success: bool, db) -> None:
    """Update circuit-breaker state based on delivery outcome."""
    if success:
        endpoint.consecutive_failures = 0
        endpoint.circuit_state = CircuitState.CLOSED
        endpoint.circuit_opened_at = None
    else:
        endpoint.consecutive_failures += 1
        if endpoint.consecutive_failures >= endpoint.circuit_threshold:
            if endpoint.circuit_state != CircuitState.OPEN:
                endpoint.circuit_state = CircuitState.OPEN
                endpoint.circuit_opened_at = datetime.now(timezone.utc)
                logger.warning(
                    "circuit_opened",
                    endpoint_id=str(endpoint.id),
                    consecutive_failures=endpoint.consecutive_failures,
                )
                cw_emit(
                    "WARNING",
                    "circuit_opened",
                    endpoint_id=str(endpoint.id),
                    consecutive_failures=endpoint.consecutive_failures,
                )


def _evaluate_alerts_sync(endpoint: Endpoint, db) -> None:
    """Synchronous alert evaluation inside Lambda (no asyncio)."""
    from datetime import timedelta
    from sqlalchemy import func

    rules = db.execute(
        select(AlertRule).where(
            AlertRule.endpoint_id == endpoint.id,
            AlertRule.is_active.is_(True),
        )
    ).scalars().all()

    if not rules:
        return

    now = datetime.now(timezone.utc)

    for rule in rules:
        window_start = now - timedelta(minutes=rule.window_minutes)

        # Get event IDs for this endpoint
        event_ids = db.execute(
            select(WebhookEvent.id).where(WebhookEvent.endpoint_id == endpoint.id)
        ).scalars().all()

        if not event_ids:
            continue

        total = db.execute(
            select(func.count(DeliveryAttempt.id)).where(
                DeliveryAttempt.event_id.in_(event_ids),
                DeliveryAttempt.created_at >= window_start,
            )
        ).scalar_one() or 0

        if total < rule.min_sample_size:
            continue

        failures = db.execute(
            select(func.count(DeliveryAttempt.id)).where(
                DeliveryAttempt.event_id.in_(event_ids),
                DeliveryAttempt.created_at >= window_start,
                DeliveryAttempt.status == AttemptStatus.FAILURE,
            )
        ).scalar_one() or 0

        rate = failures / total if total > 0 else 0.0

        if rate >= rule.failure_rate_threshold:
            logger.warning(
                "alert_fired",
                rule_id=str(rule.id),
                rule_name=rule.name,
                endpoint_id=str(endpoint.id),
                failure_rate=round(rate, 4),
                failures=failures,
                total=total,
            )
            cw_emit(
                "WARNING",
                "alert_fired",
                rule_id=str(rule.id),
                endpoint_id=str(endpoint.id),
                failure_rate=round(rate, 4),
            )
            # Fire notification webhook if configured (fire-and-forget)
            if rule.notification_url:
                try:
                    import httpx as _httpx
                    _httpx.post(
                        rule.notification_url,
                        json={
                            "alert_rule_id": str(rule.id),
                            "rule_name": rule.name,
                            "endpoint_id": str(endpoint.id),
                            "failure_rate": round(rate, 4),
                            "fired_at": now.isoformat(),
                        },
                        timeout=5,
                    )
                except Exception as exc:
                    logger.error("alert_notification_failed", rule_id=str(rule.id), error=str(exc))

            rule.last_fired_at = now


def _process_record(record: dict[str, Any]) -> None:
    body = json.loads(record["body"])
    event_id = uuid.UUID(body["event_id"])
    endpoint_id = uuid.UUID(body["endpoint_id"])
    event_type: str = body["event_type"]
    payload: dict = body["payload"]
    attempt_number: int = int(body.get("attempt_number", 1))
    trace_id: str = body.get("trace_id", "")
    span_id: str = body.get("span_id", "")

    log = logger.bind(
        event_id=str(event_id),
        attempt=attempt_number,
        trace_id=trace_id or "none",
    )

    with get_session() as db:
        event: Optional[WebhookEvent] = db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        ).scalar_one_or_none()

        if not event:
            log.warning("event_not_found_skipping")
            return

        # Idempotency guard
        existing_attempt: Optional[DeliveryAttempt] = db.execute(
            select(DeliveryAttempt).where(
                DeliveryAttempt.event_id == event_id,
                DeliveryAttempt.attempt_number == attempt_number,
                DeliveryAttempt.status == AttemptStatus.SUCCESS,
            )
        ).scalar_one_or_none()
        if existing_attempt:
            log.info("attempt_already_succeeded_skipping")
            return

        endpoint: Optional[Endpoint] = db.execute(
            select(Endpoint).where(Endpoint.id == endpoint_id)
        ).scalar_one_or_none()

        if not endpoint or not endpoint.is_active:
            log.warning("endpoint_inactive_or_missing")
            event.status = EventStatus.FAILED
            db.commit()
            return

        # Circuit-breaker: half_open probe is allowed through; open is blocked
        if endpoint.circuit_state == CircuitState.OPEN:
            # Check if cool-down has elapsed
            if endpoint.circuit_opened_at:
                elapsed = (datetime.now(timezone.utc) - endpoint.circuit_opened_at).total_seconds()
                if elapsed < endpoint.circuit_cooldown_s:
                    log.warning("delivery_skipped_circuit_open")
                    # Re-enqueue with delay to try again after cool-down
                    _re_enqueue(str(event_id), str(endpoint_id), event_type, payload,
                                attempt_number, trace_id, span_id)
                    db.commit()
                    return
                # Cool-down elapsed → move to half_open for this probe
                endpoint.circuit_state = CircuitState.HALF_OPEN

        # ── Deliver ───────────────────────────────────────────────────────────
        http_status: Optional[int] = None
        response_body: Optional[str] = None
        duration_ms: Optional[int] = None
        error_detail: Optional[str] = None
        success = False

        try:
            http_status, response_body, duration_ms = _deliver(
                endpoint.url, payload, event_type, endpoint.secret_raw, trace_id
            )
            success = 200 <= http_status < 300
        except httpx.TimeoutException as exc:
            error_detail = f"Timeout after {DELIVERY_TIMEOUT_SECONDS}s: {exc}"
            log.warning("delivery_timeout", error=error_detail)
        except httpx.RequestError as exc:
            error_detail = f"Request error: {exc}"
            log.warning("delivery_request_error", error=error_detail)

        # ── Circuit breaker update ─────────────────────────────────────────────
        _update_circuit_breaker(endpoint, success, db)

        # ── AI explanation ─────────────────────────────────────────────────────
        ai_explanation: Optional[str] = None
        if not success:
            ai_explanation = explain_failure(
                event_type=event_type,
                endpoint_url=endpoint.url,
                http_status_code=http_status,
                error_detail=error_detail,
                response_body=response_body,
            )

        # ── Persist attempt ────────────────────────────────────────────────────
        attempt = DeliveryAttempt(
            event_id=event_id,
            attempt_number=attempt_number,
            status=AttemptStatus.SUCCESS if success else AttemptStatus.FAILURE,
            http_status_code=http_status,
            response_body=response_body,
            duration_ms=duration_ms,
            error_detail=error_detail,
            ai_explanation=ai_explanation,
        )
        db.add(attempt)
        event.attempt_count = attempt_number

        if success:
            event.status = EventStatus.DELIVERED
            event.next_retry_at = None
            log.info("delivery_success", http_status=http_status, duration_ms=duration_ms)
            cw_emit("INFO", "delivery_success", event_id=str(event_id),
                    http_status=http_status, duration_ms=duration_ms, trace_id=trace_id)
        else:
            next_attempt = attempt_number + 1
            if next_attempt <= MAX_RETRY_ATTEMPTS:
                delay = _backoff_delay(next_attempt)
                event.status = EventStatus.QUEUED
                event.next_retry_at = datetime.now(timezone.utc)
                _re_enqueue(str(event_id), str(endpoint_id), event_type, payload,
                            next_attempt, trace_id, span_id)
                log.warning("delivery_failed_retrying", http_status=http_status,
                            next_attempt=next_attempt, delay_s=delay)
                cw_emit("WARNING", "delivery_failed_retrying", event_id=str(event_id),
                        attempt=attempt_number, next_attempt=next_attempt, trace_id=trace_id)
            else:
                event.status = EventStatus.DEAD_LETTERED
                event.next_retry_at = None
                log.error("delivery_exhausted", http_status=http_status,
                          total_attempts=attempt_number)
                cw_emit("ERROR", "delivery_exhausted", event_id=str(event_id),
                        total_attempts=attempt_number, trace_id=trace_id)

        # Flush attempt before evaluating alerts so counts are current
        db.flush()

        # ── Alert evaluation ───────────────────────────────────────────────────
        _evaluate_alerts_sync(endpoint, db)

        db.commit()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    records = event.get("Records", [])
    batch_item_failures: list[dict] = []

    for record in records:
        message_id = record.get("messageId", "unknown")
        try:
            _process_record(record)
        except Exception as exc:
            logger.error("record_processing_failed", message_id=message_id,
                         error=str(exc), exc_info=True)
            batch_item_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_item_failures}
