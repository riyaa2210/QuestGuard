"""AlertRule and RateLimitBucket ORM models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AlertRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Threshold-based alert rule attached to an endpoint.

    An alert fires when:
        (failures in the last `window_minutes` minutes) / total_attempts
        >= `failure_rate_threshold`
    AND total attempts in the window >= `min_sample_size`.

    Fields
    ------
    endpoint_id           : Owning endpoint.
    name                  : Human-readable rule name.
    window_minutes        : Look-back window (default 5 min).
    failure_rate_threshold: 0.0–1.0. E.g. 0.2 = fire when ≥ 20% of attempts fail.
    min_sample_size       : Minimum attempts before the rule can fire (avoids noise).
    is_active             : Toggle without deleting.
    last_fired_at         : Timestamp of the most recent alert trigger.
    notification_url      : Optional webhook to POST the alert payload to.
    """

    __tablename__ = "alert_rules"

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    failure_rate_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    min_sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_fired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notification_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    endpoint: Mapped["Endpoint"] = relationship(  # noqa: F821
        "Endpoint", back_populates="alert_rules", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<AlertRule id={self.id} name={self.name!r} threshold={self.failure_rate_threshold}>"


class RateLimitBucket(Base):
    """
    Sliding-window rate-limit counter stored in PostgreSQL.

    Each row represents one 1-minute bucket for an endpoint.
    Old buckets are cheap to delete (one DELETE per submit call when expired).

    Fields
    ------
    endpoint_id : Owning endpoint.
    bucket_ts   : Truncated-to-minute UTC timestamp (the bucket key).
    count       : Number of events submitted in this minute.
    """

    __tablename__ = "rate_limit_buckets"

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("endpoints.id", ondelete="CASCADE"),
        primary_key=True,
    )
    bucket_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<RateLimitBucket endpoint={self.endpoint_id} ts={self.bucket_ts} count={self.count}>"
