"""Idempotency guard – prevents duplicate event processing.

Strategy
--------
We use a PostgreSQL partial unique index on (endpoint_id, idempotency_key)
WHERE idempotency_key IS NOT NULL (created in migration 0001).

When a caller submits an event with an idempotency_key we already have for
that endpoint, the INSERT will raise an IntegrityError.  We catch it and
return the existing event to the caller with HTTP 200 (not 201).

This gives at-least-once semantics with a best-effort deduplication window
limited only by how long the row exists in the database.
"""

import uuid
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import WebhookEvent

logger = structlog.get_logger(__name__)


async def find_duplicate(
    db: AsyncSession,
    endpoint_id: uuid.UUID,
    idempotency_key: str,
) -> Optional[WebhookEvent]:
    """Return the existing event if this (endpoint_id, idempotency_key) pair
    has already been recorded, otherwise None."""
    result = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.endpoint_id == endpoint_id,
            WebhookEvent.idempotency_key == idempotency_key,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        logger.info(
            "idempotency_duplicate_detected",
            event_id=str(existing.id),
            idempotency_key=idempotency_key,
        )
    return existing
