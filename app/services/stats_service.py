"""Delivery latency percentile statistics service.

Computes p50 / p95 / p99 of `delivery_attempts.duration_ms` over the last
N hours using a single SQL query with PostgreSQL's `percentile_cont` ordered-
set aggregate.  Falls back gracefully when there is no data.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import DeliveryAttempt, AttemptStatus, WebhookEvent


class DeliveryStats:
    def __init__(
        self,
        endpoint_id: uuid.UUID,
        window_hours: int,
        total_attempts: int,
        success_count: int,
        failure_count: int,
        p50_ms: Optional[float],
        p95_ms: Optional[float],
        p99_ms: Optional[float],
        success_rate: float,
    ):
        self.endpoint_id = endpoint_id
        self.window_hours = window_hours
        self.total_attempts = total_attempts
        self.success_count = success_count
        self.failure_count = failure_count
        self.p50_ms = p50_ms
        self.p95_ms = p95_ms
        self.p99_ms = p99_ms
        self.success_rate = success_rate


async def get_endpoint_stats(
    db: AsyncSession,
    endpoint_id: uuid.UUID,
    window_hours: int = 24,
) -> DeliveryStats:
    """Return delivery latency percentiles and counts for an endpoint."""
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    # Sub-query: attempts belonging to this endpoint in the window
    event_ids_sq = (
        select(WebhookEvent.id)
        .where(WebhookEvent.endpoint_id == endpoint_id)
        .scalar_subquery()
    )

    base = select(DeliveryAttempt).where(
        DeliveryAttempt.event_id.in_(event_ids_sq),
        DeliveryAttempt.created_at >= since,
    )

    # Count totals
    count_result = await db.execute(
        select(
            func.count(DeliveryAttempt.id).label("total"),
            func.count(DeliveryAttempt.id)
            .filter(DeliveryAttempt.status == AttemptStatus.SUCCESS)
            .label("success"),
        ).where(
            DeliveryAttempt.event_id.in_(event_ids_sq),
            DeliveryAttempt.created_at >= since,
        )
    )
    row = count_result.one()
    total: int = row.total or 0
    success: int = row.success or 0
    failure: int = total - success

    # Percentile computation – PostgreSQL-specific aggregate
    # percentile_cont(fraction) WITHIN GROUP (ORDER BY duration_ms)
    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    p99_ms: Optional[float] = None

    if total > 0:
        pct_result = await db.execute(
            select(
                func.percentile_cont(0.50)
                .within_group(DeliveryAttempt.duration_ms)
                .label("p50"),
                func.percentile_cont(0.95)
                .within_group(DeliveryAttempt.duration_ms)
                .label("p95"),
                func.percentile_cont(0.99)
                .within_group(DeliveryAttempt.duration_ms)
                .label("p99"),
            ).where(
                DeliveryAttempt.event_id.in_(event_ids_sq),
                DeliveryAttempt.created_at >= since,
                DeliveryAttempt.duration_ms.isnot(None),
            )
        )
        pct_row = pct_result.one_or_none()
        if pct_row:
            p50_ms = round(pct_row.p50, 1) if pct_row.p50 is not None else None
            p95_ms = round(pct_row.p95, 1) if pct_row.p95 is not None else None
            p99_ms = round(pct_row.p99, 1) if pct_row.p99 is not None else None

    return DeliveryStats(
        endpoint_id=endpoint_id,
        window_hours=window_hours,
        total_attempts=total,
        success_count=success,
        failure_count=failure,
        p50_ms=p50_ms,
        p95_ms=p95_ms,
        p99_ms=p99_ms,
        success_rate=round(success / total, 4) if total > 0 else 0.0,
    )
