"""DLQ Lambda handler – processes messages from the dead-letter queue.

Triggered by an SQS event source mapping on the queueguard-events-dlq queue.

Responsibilities
----------------
1. Mark the event as dead_lettered in the database (if not already done).
2. Emit a CloudWatch metric / log entry for alerting.
3. Optionally enrich the final DeliveryAttempt row with an AI explanation.

This handler does NOT perform any further delivery retries.  Operators
can trigger a manual replay via the API (POST /api/v1/events/detail/{id}/replay).
"""

import json
import uuid
from typing import Any, Optional

import structlog
from sqlalchemy import select

from lambda.ai_explainer import explain_failure
from lambda.cloudwatch_logger import emit as cw_emit
from lambda.db import get_session
from app.models.event import DeliveryAttempt, EventStatus, WebhookEvent
from app.models.endpoint import Endpoint

logger = structlog.get_logger(__name__)


def _process_dlq_record(record: dict[str, Any]) -> None:
    body = json.loads(record["body"])
    event_id = uuid.UUID(body["event_id"])
    event_type: str = body.get("event_type", "unknown")
    attempt_number: int = int(body.get("attempt_number", 1))

    log = logger.bind(event_id=str(event_id), attempt=attempt_number)
    log.error("dlq_message_received")

    with get_session() as db:
        event: Optional[WebhookEvent] = db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        ).scalar_one_or_none()

        if not event:
            log.warning("dlq_event_not_found")
            return

        # Ensure final status is persisted
        if event.status != EventStatus.DEAD_LETTERED:
            event.status = EventStatus.DEAD_LETTERED

        # Enrich the latest failure attempt with an AI explanation if missing
        endpoint: Optional[Endpoint] = db.execute(
            select(Endpoint).where(Endpoint.id == event.endpoint_id)
        ).scalar_one_or_none()

        last_attempt: Optional[DeliveryAttempt] = db.execute(
            select(DeliveryAttempt)
            .where(DeliveryAttempt.event_id == event_id)
            .order_by(DeliveryAttempt.attempt_number.desc())
            .limit(1)
        ).scalar_one_or_none()

        if last_attempt and not last_attempt.ai_explanation and endpoint:
            explanation = explain_failure(
                event_type=event_type,
                endpoint_url=endpoint.url,
                http_status_code=last_attempt.http_status_code,
                error_detail=last_attempt.error_detail,
                response_body=last_attempt.response_body,
            )
            if explanation:
                last_attempt.ai_explanation = explanation

        db.commit()

        cw_emit(
            "ERROR",
            "event_dead_lettered",
            event_id=str(event_id),
            event_type=event_type,
            total_attempts=event.attempt_count,
        )
        log.error("event_dead_lettered", total_attempts=event.attempt_count)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    records = event.get("Records", [])
    batch_item_failures: list[dict] = []

    for record in records:
        message_id = record.get("messageId", "unknown")
        try:
            _process_dlq_record(record)
        except Exception as exc:
            logger.error("dlq_record_failed", message_id=message_id, error=str(exc), exc_info=True)
            batch_item_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_item_failures}
