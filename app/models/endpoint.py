"""Registered webhook endpoint model."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CircuitState:
    CLOSED = "closed"      # normal – deliveries proceed
    OPEN = "open"          # tripped – deliveries paused until cool-down expires
    HALF_OPEN = "half_open"  # cool-down elapsed – next delivery is a probe


class Endpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A registered destination that can receive webhook events.

    Fields
    ------
    url                  : Destination HTTPS URL.
    description          : Free-form label.
    secret_raw           : Plaintext HMAC secret (write-only; used by Lambda to sign).
                           Stored in plaintext so the Lambda can re-derive the signature.
                           Rotate via PATCH; never returned in API responses.
    is_active            : Soft-disable without deleting.
    event_types          : Comma-separated list of event type filters (empty = all).
    payload_schema       : Optional JSON Schema (stored as JSONB) for event validation.

    Circuit-breaker fields
    ----------------------
    circuit_state        : closed | open | half_open
    consecutive_failures : Running count of back-to-back failures (reset on success).
    circuit_opened_at    : Timestamp when the circuit tripped open.
    circuit_threshold    : How many consecutive failures trip the breaker (default 5).
    circuit_cooldown_s   : Seconds the circuit stays open before moving to half_open (default 600).

    Rate-limit fields
    -----------------
    rate_limit_per_minute: Max events accepted per minute (0 = unlimited).
    """

    __tablename__ = "endpoints"

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Stored as plaintext so Lambda can compute HMAC without a secrets-manager round-trip.
    # In production, consider using AWS Secrets Manager and referencing the ARN here instead.
    secret_raw: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    event_types: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_schema: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Circuit breaker
    circuit_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CircuitState.CLOSED
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    circuit_opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    circuit_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    circuit_cooldown_s: Mapped[int] = mapped_column(Integer, nullable=False, default=600)

    # Rate limiting
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    events: Mapped[list["WebhookEvent"]] = relationship(  # noqa: F821
        "WebhookEvent", back_populates="endpoint", lazy="raise"
    )
    alert_rules: Mapped[list["AlertRule"]] = relationship(  # noqa: F821
        "AlertRule", back_populates="endpoint", lazy="raise", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Endpoint id={self.id} url={self.url!r} circuit={self.circuit_state}>"
