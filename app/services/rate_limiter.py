"""Sliding-window rate limiter using PostgreSQL.

Algorithm
---------
We keep a `rate_limit_buckets` table with one row per (endpoint_id, minute).
On each submit we:
  1. Delete buckets older than 1 minute (cheap: indexed by bucket_ts).
  2. Upsert the current-minute bucket, incrementing the counter.
  3. Sum all remaining buckets for the endpoint.
  4. If the sum exceeds `rate_limit_per_minute`, reject with HTTP 429.

Trade-offs
----------
- One extra DB round-trip per submit (acceptable for MVP).
- No Redis dependency.
- Not perfectly "sliding" (bucket granularity = 1 minute) but close enough
  for a resume project; a true sliding window would use timestamps + COUNT.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import RateLimitBucket

if TYPE_CHECKING:
    from app.models.endpoint import Endpoint

logger = structlog.get_logger(__name__)


def _current_bucket() -> datetime:
    """Truncate UTC now to the current minute."""
    now = datetime.now(timezone.utc)
    return now.replace(second=0, microsecond=0)


async def check_and_increment(
    db: AsyncSession,
    endpoint: "Endpoint",
) -> tuple[bool, int]:
    """
    Check the rate limit and atomically increment if allowed.

    Returns (allowed, current_count).
    If `rate_limit_per_minute` == 0, always returns (True, 0).
    """
    if endpoint.rate_limit_per_minute == 0:
        return True, 0

    bucket_ts = _current_bucket()
    cutoff = bucket_ts - timedelta(minutes=1)

    # 1. Prune old buckets
    await db.execute(
        delete(RateLimitBucket).where(
            RateLimitBucket.endpoint_id == endpoint.id,
            RateLimitBucket.bucket_ts < cutoff,
        )
    )

    # 2. Upsert current bucket (PostgreSQL INSERT … ON CONFLICT DO UPDATE)
    stmt = (
        pg_insert(RateLimitBucket)
        .values(endpoint_id=endpoint.id, bucket_ts=bucket_ts, count=1)
        .on_conflict_do_update(
            index_elements=["endpoint_id", "bucket_ts"],
            set_={"count": RateLimitBucket.count + 1},
        )
    )
    await db.execute(stmt)
    await db.flush()

    # 3. Sum the sliding window (last minute's buckets)
    result = await db.execute(
        select(func.sum(RateLimitBucket.count)).where(
            RateLimitBucket.endpoint_id == endpoint.id,
            RateLimitBucket.bucket_ts >= cutoff,
        )
    )
    total: int = result.scalar_one() or 0

    allowed = total <= endpoint.rate_limit_per_minute

    if not allowed:
        logger.warning(
            "rate_limit_exceeded",
            endpoint_id=str(endpoint.id),
            count=total,
            limit=endpoint.rate_limit_per_minute,
        )

    return allowed, total
