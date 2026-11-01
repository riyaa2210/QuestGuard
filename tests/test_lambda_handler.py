"""Tests for the Lambda delivery handler.

Tests cover: successful delivery, HTTP failure + retry scheduling,
timeout handling, retry exhaustion → dead_lettered, and idempotent
re-processing of an already-succeeded attempt.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import respx
import httpx

from app.models.event import AttemptStatus, DeliveryAttempt, EventStatus, WebhookEvent
from app.models.endpoint import Endpoint


def _make_sqs_record(
    event_id: str,
    endpoint_id: str,
    event_type: str = "order.created",
    payload: dict | None = None,
    attempt_number: int = 1,
) -> dict:
    return {
        "messageId": str(uuid.uuid4()),
        "body": json.dumps(
            {
                "event_id": event_id,
                "endpoint_id": endpoint_id,
                "event_type": event_type,
                "payload": payload or {"k": "v"},
                "attempt_number": attempt_number,
            }
        ),
    }


def _seed_db(db, *, event_status: str = EventStatus.QUEUED, attempt_count: int = 0):
    """Insert an Endpoint + WebhookEvent into a sync session and return (endpoint, event)."""
    ep_id = uuid.uuid4()
    ev_id = uuid.uuid4()
    endpoint = Endpoint(
        id=ep_id, url="https://dest.example.com/hook", is_active=True
    )
    event = WebhookEvent(
        id=ev_id,
        endpoint_id=ep_id,
        event_type="order.created",
        payload={"k": "v"},
        status=event_status,
        attempt_count=attempt_count,
    )
    db.add(endpoint)
    db.add(event)
    db.commit()
    return endpoint, event


class FakeSession:
    """Minimal synchronous session stub backed by a list of known objects."""

    def __init__(self, objects: list):
        self._objects = objects
        self._added: list = []
        self.committed = False

    def execute(self, stmt):
        # Very simplified: return the first matching object by model class
        # This is enough for our unit tests
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        return result

    def add(self, obj):
        self._added.append(obj)

    def commit(self):
        self.committed = True


# ── Delivery success ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
@respx.mock
async def test_successful_delivery():
    from lambda import handler as h

    ep_id = uuid.uuid4()
    ev_id = uuid.uuid4()

    endpoint = Endpoint(id=ep_id, url="https://dest.example.com/hook", is_active=True)
    event = WebhookEvent(
        id=ev_id, endpoint_id=ep_id, event_type="order.created",
        payload={"k": "v"}, status=EventStatus.QUEUED, attempt_count=0,
    )

    # Mock httpx delivery
    respx.post("https://dest.example.com/hook").mock(return_value=httpx.Response(200))

    db_mock = MagicMock()
    db_mock.execute.return_value.scalar_one_or_none.side_effect = [event, None, endpoint]

    with patch("lambda.handler.get_session") as mock_ctx:
        mock_ctx.return_value.__enter__ = MagicMock(return_value=db_mock)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        record = _make_sqs_record(str(ev_id), str(ep_id))
        result = h.lambda_handler({"Records": [record]}, None)

    assert result["batchItemFailures"] == []
    # Event should be marked delivered
    assert event.status == EventStatus.DELIVERED
    assert event.attempt_count == 1


# ── HTTP 500 → retry scheduled ─────────────────────────────────────────────────
@pytest.mark.asyncio
@respx.mock
async def test_http_500_schedules_retry():
    from lambda import handler as h

    ep_id = uuid.uuid4()
    ev_id = uuid.uuid4()

    endpoint = Endpoint(id=ep_id, url="https://dest.example.com/hook", is_active=True)
    event = WebhookEvent(
        id=ev_id, endpoint_id=ep_id, event_type="order.created",
        payload={"k": "v"}, status=EventStatus.QUEUED, attempt_count=0,
    )

    respx.post("https://dest.example.com/hook").mock(return_value=httpx.Response(500, text="err"))

    db_mock = MagicMock()
    db_mock.execute.return_value.scalar_one_or_none.side_effect = [event, None, endpoint]

    sqs_mock = MagicMock()

    with patch("lambda.handler.get_session") as mock_ctx, \
         patch("lambda.handler._sqs_client", sqs_mock), \
         patch("lambda.handler.cw_emit"):
        mock_ctx.return_value.__enter__ = MagicMock(return_value=db_mock)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        record = _make_sqs_record(str(ev_id), str(ep_id), attempt_number=1)
        result = h.lambda_handler({"Records": [record]}, None)

    assert result["batchItemFailures"] == []
    # A retry should have been scheduled via SQS
    sqs_mock.send_message.assert_called_once()
    call_kwargs = sqs_mock.send_message.call_args.kwargs
    assert call_kwargs["DelaySeconds"] == h.INITIAL_RETRY_DELAY_SECONDS  # 30s for attempt 1→2
    # Event stays queued (not failed) while retries remain
    assert event.status == EventStatus.QUEUED


# ── Timeout → retry scheduled ──────────────────────────────────────────────────
@pytest.mark.asyncio
@respx.mock
async def test_timeout_schedules_retry():
    from lambda import handler as h

    ep_id = uuid.uuid4()
    ev_id = uuid.uuid4()

    endpoint = Endpoint(id=ep_id, url="https://dest.example.com/hook", is_active=True)
    event = WebhookEvent(
        id=ev_id, endpoint_id=ep_id, event_type="order.created",
        payload={"k": "v"}, status=EventStatus.QUEUED, attempt_count=0,
    )

    respx.post("https://dest.example.com/hook").mock(side_effect=httpx.TimeoutException("timed out"))

    db_mock = MagicMock()
    db_mock.execute.return_value.scalar_one_or_none.side_effect = [event, None, endpoint]

    sqs_mock = MagicMock()

    with patch("lambda.handler.get_session") as mock_ctx, \
         patch("lambda.handler._sqs_client", sqs_mock), \
         patch("lambda.handler.cw_emit"):
        mock_ctx.return_value.__enter__ = MagicMock(return_value=db_mock)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        record = _make_sqs_record(str(ev_id), str(ep_id), attempt_number=1)
        result = h.lambda_handler({"Records": [record]}, None)

    assert result["batchItemFailures"] == []
    sqs_mock.send_message.assert_called_once()
    assert "Timeout" in str(db_mock.add.call_args_list)  # error_detail recorded


# ── Retry exhaustion → dead_lettered ──────────────────────────────────────────
@pytest.mark.asyncio
@respx.mock
async def test_retry_exhaustion_marks_dead_lettered():
    from lambda import handler as h

    ep_id = uuid.uuid4()
    ev_id = uuid.uuid4()

    endpoint = Endpoint(id=ep_id, url="https://dest.example.com/hook", is_active=True)
    # Simulate we are on the final attempt
    max_attempt = h.MAX_RETRY_ATTEMPTS
    event = WebhookEvent(
        id=ev_id, endpoint_id=ep_id, event_type="order.created",
        payload={"k": "v"}, status=EventStatus.QUEUED, attempt_count=max_attempt - 1,
    )

    respx.post("https://dest.example.com/hook").mock(return_value=httpx.Response(503))

    db_mock = MagicMock()
    db_mock.execute.return_value.scalar_one_or_none.side_effect = [event, None, endpoint]

    sqs_mock = MagicMock()

    with patch("lambda.handler.get_session") as mock_ctx, \
         patch("lambda.handler._sqs_client", sqs_mock), \
         patch("lambda.handler.cw_emit"):
        mock_ctx.return_value.__enter__ = MagicMock(return_value=db_mock)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        record = _make_sqs_record(str(ev_id), str(ep_id), attempt_number=max_attempt)
        result = h.lambda_handler({"Records": [record]}, None)

    assert result["batchItemFailures"] == []
    # No further retry should be scheduled
    sqs_mock.send_message.assert_not_called()
    assert event.status == EventStatus.DEAD_LETTERED


# ── Idempotent re-processing ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_already_succeeded_attempt_is_skipped():
    from lambda import handler as h

    ep_id = uuid.uuid4()
    ev_id = uuid.uuid4()

    existing_success_attempt = DeliveryAttempt(
        id=uuid.uuid4(),
        event_id=ev_id,
        attempt_number=1,
        status=AttemptStatus.SUCCESS,
    )
    event = WebhookEvent(
        id=ev_id, endpoint_id=ep_id, event_type="order.created",
        payload={}, status=EventStatus.DELIVERED, attempt_count=1,
    )

    db_mock = MagicMock()
    # First call → event, second call → existing success attempt (idempotency check)
    db_mock.execute.return_value.scalar_one_or_none.side_effect = [event, existing_success_attempt]

    with patch("lambda.handler.get_session") as mock_ctx:
        mock_ctx.return_value.__enter__ = MagicMock(return_value=db_mock)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        record = _make_sqs_record(str(ev_id), str(ep_id), attempt_number=1)
        result = h.lambda_handler({"Records": [record]}, None)

    assert result["batchItemFailures"] == []
    # No new DeliveryAttempt should have been added
    db_mock.add.assert_not_called()


# ── Exponential backoff delays ────────────────────────────────────────────────
def test_backoff_delay_values():
    from lambda.handler import _backoff_delay

    assert _backoff_delay(1) == 30    # 30 * 2^0
    assert _backoff_delay(2) == 60    # 30 * 2^1
    assert _backoff_delay(3) == 120
    assert _backoff_delay(4) == 240
    assert _backoff_delay(5) == 480
    # Must never exceed SQS max of 900 s
    assert _backoff_delay(100) == 900
