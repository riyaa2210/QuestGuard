"""WebhookEvent and DeliveryAttempt ORM models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EventStatus:
    PENDING = "pending"
    QUEUED = "queued"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


class AttemptStatus:
    SUCCESS = "success"
    FAILURE = "failure"


class WebhookEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Represents a single incoming webhook event.

    Fields
    ------
    endpoint_id    : Target endpoint.
    event_type     : e.g. "order.created", "payment.failed".
    idempotency_key: Caller-supplied key; duplicate keys within the same endpoint
                     are rejected (or short-circuited) after the first success.
    payload        : Raw JSON payload from the caller.
    status         : pending → queued → delivered | failed | dead_lettered.
    sqs_message_id : The SQS message ID for traceability.
    attempt_count  : Running count of delivery attempts.
    next_retry_at  : Earliest time the next delivery attempt should occur.
    """

    __tablename__ = "webhook_events"

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EventStatus.PENDING, index=True
    )
    sqs_message_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # OpenTelemetry trace context – carried through SQS into Lambda
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    span_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Relationships
    endpoint: Mapped["Endpoint"] = relationship(  # noqa: F821
        "Endpoint", back_populates="events", lazy="raise"
    )
    attempts: Mapped[list["DeliveryAttempt"]] = relationship(
        "DeliveryAttempt", back_populates="event", lazy="raise", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<WebhookEvent id={self.id} type={self.event_type!r} status={self.status!r}>"


class DeliveryAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Records each individual delivery attempt for an event.

    Fields
    ------
    event_id        : Parent event.
    attempt_number  : 1-based sequence for this event.
    status          : success | failure.
    http_status_code: Response code from the destination endpoint.
    response_body   : First 4 KB of the response body (or error message).
    duration_ms     : How long the HTTP call took.
    error_detail    : Exception or transport error description.
    ai_explanation  : Optional LLM-generated explanation of the failure.
    """

    __tablename__ = "delivery_attempts"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    http_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    event: Mapped["WebhookEvent"] = relationship("WebhookEvent", back_populates="attempts", lazy="raise")

    def __repr__(self) -> str:
        return f"<DeliveryAttempt event={self.event_id} #{self.attempt_number} {self.status}>"
