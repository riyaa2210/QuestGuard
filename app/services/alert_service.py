"""Alert rule evaluation and management.

Alert rules are evaluated after each delivery attempt (in the Lambda handler).
When a rule fires, QueueGuard POSTs a structured alert payload to the rule's
`notification_url` (if configured) and updates `last_fired_at`.

Alert payload shape
-------------------
{
  "alert_rule_id": "<uuid>",
  "rule_name": "High failure rate",
  "endpoint_id": "<uuid>",
  "endpoint_url": "https://...",
  "window_minutes": 5,
  "failure_rate": 0.45,
  "failure_count": 9,
  "total_count": 20,
  "fired_at": "2024-06-01T12:00:00Z"
}
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertRule
from app.models.event import AttemptStatus, DeliveryAttempt
from app.schemas.alert import AlertRuleCreate, AlertRuleResponse

if TYPE_CHECKING:
    from app.models.endpoint import Endpoint

logger = structlog.get_logger(__name__)


class AlertService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_rule(self, endpoint_id: uuid.UUID, data: AlertRuleCreate) -> AlertRule:
        rule = AlertRule(
            endpoint_id=endpoint_id,
            name=data.name,
            window_minutes=data.window_minutes,
            failure_rate_threshold=data.failure_rate_threshold,
            min_sample_size=data.min_sample_size,
            notification_url=str(data.notification_url) if data.notification_url else None,
        )
        self._db.add(rule)
        await self._db.commit()
        await self._db.refresh(rule)
        return rule

    async def list_rules(self, endpoint_id: uuid.UUID) -> list[AlertRule]:
        result = await self._db.execute(
            select(AlertRule).where(AlertRule.endpoint_id == endpoint_id)
        )
        return list(result.scalars().all())

    async def delete_rule(self, rule_id: uuid.UUID) -> bool:
        result = await self._db.execute(select(AlertRule).where(AlertRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            return False
        await self._db.delete(rule)
        await self._db.commit()
        return True

    async def evaluate_rules(self, endpoint_id: uuid.UUID, endpoint_url: str) -> None:
        """Evaluate all active alert rules for an endpoint.

        Called after every delivery attempt.  Uses a single aggregation query
        per rule window to avoid N+1 queries.
        """
        rules_result = await self._db.execute(
            select(AlertRule).where(
                AlertRule.endpoint_id == endpoint_id,
                AlertRule.is_active.is_(True),
            )
        )
        rules = list(rules_result.scalars().all())
        if not rules:
            return

        now = datetime.now(timezone.utc)

        for rule in rules:
            window_start = now - timedelta(minutes=rule.window_minutes)

            # Count total and failed attempts in the window
            total_result = await self._db.execute(
                select(func.count(DeliveryAttempt.id))
                .join(DeliveryAttempt.event)  # type: ignore[arg-type]
                .where(
                    DeliveryAttempt.created_at >= window_start,
                )
                # Filter by endpoint via the joined event
                .where(
                    DeliveryAttempt.event_id.in_(  # type: ignore[attr-defined]
                        select(
                            __import__("app.models.event", fromlist=["WebhookEvent"])
                            .WebhookEvent.id
                        ).where(
                            __import__("app.models.event", fromlist=["WebhookEvent"])
                            .WebhookEvent.endpoint_id
                            == endpoint_id
                        )
                    )
                )
            )
            total: int = total_result.scalar_one() or 0

            if total < rule.min_sample_size:
                continue

            failure_result = await self._db.execute(
                select(func.count(DeliveryAttempt.id))
                .where(
                    DeliveryAttempt.created_at >= window_start,
                    DeliveryAttempt.status == AttemptStatus.FAILURE,
                    DeliveryAttempt.event_id.in_(
                        select(
                            __import__("app.models.event", fromlist=["WebhookEvent"])
                            .WebhookEvent.id
                        ).where(
                            __import__("app.models.event", fromlist=["WebhookEvent"])
                            .WebhookEvent.endpoint_id
                            == endpoint_id
                        )
                    ),
                )
            )
            failures: int = failure_result.scalar_one() or 0
            failure_rate = failures / total if total > 0 else 0.0

            if failure_rate >= rule.failure_rate_threshold:
                await self._fire_alert(rule, endpoint_url, failure_rate, failures, total, now)
                rule.last_fired_at = now
                await self._db.commit()

    async def _fire_alert(
        self,
        rule: AlertRule,
        endpoint_url: str,
        failure_rate: float,
        failure_count: int,
        total_count: int,
        fired_at: datetime,
    ) -> None:
        payload = {
            "alert_rule_id": str(rule.id),
            "rule_name": rule.name,
            "endpoint_id": str(rule.endpoint_id),
            "endpoint_url": endpoint_url,
            "window_minutes": rule.window_minutes,
            "failure_rate": round(failure_rate, 4),
            "failure_count": failure_count,
            "total_count": total_count,
            "fired_at": fired_at.isoformat(),
        }
        logger.warning("alert_fired", **payload)

        if rule.notification_url:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(rule.notification_url, json=payload)
                logger.info("alert_notification_sent", rule_id=str(rule.id))
            except Exception as exc:
                logger.error("alert_notification_failed", rule_id=str(rule.id), error=str(exc))
