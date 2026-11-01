"""Webhook fan-out service.

A fan-out event is submitted to the global events bus without specifying a
target endpoint.  QueueGuard finds all active endpoints that subscribe to
the event type and creates one WebhookEvent per matching endpoint, each
enqueued independently.

Fan-out endpoint matching
--------------------------
- An endpoint with `event_types = NULL` (i.e. "all events") always matches.
- An endpoint with a non-empty `event_types` list matches only if the submitted
  `event_type` is in that list.
- Endpoints whose circuit is OPEN are skipped (the circuit-breaker protects them).

This turns QueueGuard from a point-to-point delivery queue into a proper
HTTP pub/sub fan-out system — similar to how Svix and Hookdeck work.
"""

import uuid
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.endpoint import Endpoint
from app.models.event import EventStatus, WebhookEvent
from app.schemas.event import EventSubmit
from app.services.circuit_breaker import CircuitState, get_effective_state
from app.services.idempotency import find_duplicate
from app.services.sqs_producer import get_producer
from app.telemetry import get_current_trace_context

logger = structlog.get_logger(__name__)


class FanoutService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def fanout(self, data: EventSubmit) -> list[dict]:
        """
        Broadcast `data` to all matching active endpoints.

        Returns a list of result dicts:
        [
          {"endpoint_id": "...", "event_id": "...", "status": "queued"},
          {"endpoint_id": "...", "status": "skipped", "reason": "circuit_open"},
          ...
        ]
        """
        trace_id, span_id = get_current_trace_context()
        endpoints = await self._get_matching_endpoints(data.event_type)
        results: list[dict] = []
        producer = get_producer()

        for endpoint in endpoints:
            result = await self._dispatch_to_endpoint(
                endpoint, data, producer, trace_id, span_id
            )
            results.append(result)

        logger.info(
            "fanout_complete",
            event_type=data.event_type,
            total=len(endpoints),
            queued=sum(1 for r in results if r.get("status") == "queued"),
        )
        return results

    async def _get_matching_endpoints(self, event_type: str) -> list[Endpoint]:
        result = await self._db.execute(
            select(Endpoint).where(Endpoint.is_active.is_(True))
        )
        all_active = list(result.scalars().all())

        matching = []
        for ep in all_active:
            # Null event_types = subscribe to everything
            if ep.event_types is None:
                matching.append(ep)
            else:
                subscribed = [t.strip() for t in ep.event_types.split(",") if t.strip()]
                if event_type in subscribed:
                    matching.append(ep)

        return matching

    async def _dispatch_to_endpoint(
        self,
        endpoint: Endpoint,
        data: EventSubmit,
        producer,
        trace_id: str,
        span_id: str,
    ) -> dict:
        # Circuit-breaker check
        effective_state = get_effective_state(endpoint)
        if effective_state == CircuitState.OPEN:
            logger.warning(
                "fanout_skipped_circuit_open",
                endpoint_id=str(endpoint.id),
                event_type=data.event_type,
            )
            return {
                "endpoint_id": str(endpoint.id),
                "status": "skipped",
                "reason": "circuit_open",
            }

        # Idempotency check
        if data.idempotency_key:
            existing = await find_duplicate(self._db, endpoint.id, data.idempotency_key)
            if existing:
                return {
                    "endpoint_id": str(endpoint.id),
                    "event_id": str(existing.id),
                    "status": "duplicate",
                }

        event = WebhookEvent(
            endpoint_id=endpoint.id,
            event_type=data.event_type,
            idempotency_key=data.idempotency_key,
            payload=data.payload,
            status=EventStatus.PENDING,
            trace_id=trace_id or None,
            span_id=span_id or None,
        )
        self._db.add(event)
        await self._db.flush()

        msg_id = producer.enqueue_event(
            event_id=event.id,
            endpoint_id=endpoint.id,
            event_type=data.event_type,
            payload=data.payload,
            trace_id=trace_id,
            span_id=span_id,
        )
        event.status = EventStatus.QUEUED
        event.sqs_message_id = msg_id

        return {
            "endpoint_id": str(endpoint.id),
            "event_id": str(event.id),
            "status": "queued",
        }
