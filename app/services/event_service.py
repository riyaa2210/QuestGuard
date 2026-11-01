"""Business logic for event submission, history, and replay."""

import uuid
from typing import Optional

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import AttemptStatus, DeliveryAttempt, EventStatus, WebhookEvent
from app.models.endpoint import CircuitState
from app.schemas.event import EventSubmit
from app.services.idempotency import find_duplicate
from app.services.rate_limiter import check_and_increment
from app.services.schema_validator import validate_payload
from app.services.circuit_breaker import get_effective_state
from app.services.sqs_producer import get_producer
from app.telemetry import get_current_trace_context

logger = structlog.get_logger(__name__)


class RateLimitExceeded(Exception):
    def __init__(self, limit: int, current: int):
        self.limit = limit
        self.current = current
        super().__init__(f"Rate limit exceeded: {current}/{limit} events per minute")


class CircuitOpenError(Exception):
    def __init__(self, endpoint_id: str):
        self.endpoint_id = endpoint_id
        super().__init__(f"Circuit breaker is OPEN for endpoint {endpoint_id}")


class SchemaValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Payload failed schema validation")


class EventService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def submit(
        self, endpoint_id: uuid.UUID, data: EventSubmit, endpoint
    ) -> tuple[WebhookEvent, bool]:
        """
        Create and enqueue a new event.

        Raises:
            RateLimitExceeded    – caller should return HTTP 429
            CircuitOpenError     – caller should return HTTP 503
            SchemaValidationError– caller should return HTTP 422

        Returns (event, is_duplicate) where is_duplicate=True means the
        idempotency key was already seen – existing event returned unchanged.
        """
        # ── Circuit breaker ───────────────────────────────────────────────────
        effective_state = get_effective_state(endpoint)
        if effective_state == CircuitState.OPEN:
            raise CircuitOpenError(str(endpoint_id))

        # ── Rate limit ────────────────────────────────────────────────────────
        allowed, current_count = await check_and_increment(self._db, endpoint)
        if not allowed:
            raise RateLimitExceeded(endpoint.rate_limit_per_minute, current_count)

        # ── JSON Schema validation ────────────────────────────────────────────
        schema_errors = validate_payload(
            data.payload, endpoint.payload_schema, str(endpoint_id), data.event_type
        )
        if schema_errors:
            raise SchemaValidationError(schema_errors)

        # ── Idempotency check ─────────────────────────────────────────────────
        if data.idempotency_key:
            existing = await find_duplicate(self._db, endpoint_id, data.idempotency_key)
            if existing:
                return existing, True

        # ── OTel trace context ────────────────────────────────────────────────
        trace_id, span_id = get_current_trace_context()

        event = WebhookEvent(
            endpoint_id=endpoint_id,
            event_type=data.event_type,
            idempotency_key=data.idempotency_key,
            payload=data.payload,
            status=EventStatus.PENDING,
            trace_id=trace_id or None,
            span_id=span_id or None,
        )
        self._db.add(event)
        await self._db.flush()

        # Enqueue to SQS
        producer = get_producer()
        msg_id = producer.enqueue_event(
            event_id=event.id,
            endpoint_id=endpoint_id,
            event_type=data.event_type,
            payload=data.payload,
            trace_id=trace_id,
            span_id=span_id,
        )
        event.status = EventStatus.QUEUED
        event.sqs_message_id = msg_id

        await self._db.commit()
        await self._db.refresh(event)
        logger.info("event_submitted", event_id=str(event.id), type=data.event_type,
                    trace_id=trace_id or "none")
        return event, False

    async def get(self, event_id: uuid.UUID) -> Optional[WebhookEvent]:
        result = await self._db.execute(
            select(WebhookEvent)
            .options(selectinload(WebhookEvent.attempts))
            .where(WebhookEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def list_for_endpoint(
        self,
        endpoint_id: uuid.UUID,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[WebhookEvent], int]:
        base_q = select(WebhookEvent).where(WebhookEvent.endpoint_id == endpoint_id)
        if status:
            base_q = base_q.where(WebhookEvent.status == status)

        total_result = await self._db.execute(
            select(func.count()).select_from(base_q.subquery())
        )
        total = total_result.scalar_one()

        events_result = await self._db.execute(
            base_q.options(selectinload(WebhookEvent.attempts))
            .order_by(WebhookEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(events_result.scalars().all()), total

    async def replay(self, event_id: uuid.UUID) -> Optional[WebhookEvent]:
        """Re-enqueue a failed or dead-lettered event for another delivery attempt."""
        event = await self.get(event_id)
        if not event:
            return None
        if event.status not in (EventStatus.FAILED, EventStatus.DEAD_LETTERED):
            raise ValueError(
                f"Only failed or dead_lettered events can be replayed. Current status: {event.status}"
            )

        event.status = EventStatus.QUEUED
        event.next_retry_at = None

        producer = get_producer()
        msg_id = producer.enqueue_event(
            event_id=event.id,
            endpoint_id=event.endpoint_id,
            event_type=event.event_type,
            payload=event.payload,
            attempt_number=event.attempt_count + 1,
        )
        event.sqs_message_id = msg_id
        await self._db.commit()
        await self._db.refresh(event)
        logger.info("event_replayed", event_id=str(event.id))
        return event

    async def list_attempts(self, event_id: uuid.UUID) -> list[DeliveryAttempt]:
        result = await self._db.execute(
            select(DeliveryAttempt)
            .where(DeliveryAttempt.event_id == event_id)
            .order_by(DeliveryAttempt.attempt_number)
        )
        return list(result.scalars().all())
