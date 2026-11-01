"""Business logic for Endpoint CRUD."""

import uuid
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.endpoint import Endpoint
from app.schemas.endpoint import EndpointCreate, EndpointUpdate

logger = structlog.get_logger(__name__)


class EndpointService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, data: EndpointCreate) -> Endpoint:
        event_types_str = ",".join(data.event_types) if data.event_types else None
        endpoint = Endpoint(
            url=str(data.url),
            description=data.description,
            # Store raw secret for HMAC signing by the Lambda delivery handler.
            # Never return this value in API responses.
            secret_raw=data.secret or None,
            event_types=event_types_str,
            payload_schema=data.payload_schema,
            rate_limit_per_minute=data.rate_limit_per_minute,
            circuit_threshold=data.circuit_threshold,
            circuit_cooldown_s=data.circuit_cooldown_s,
        )
        self._db.add(endpoint)
        await self._db.commit()
        await self._db.refresh(endpoint)
        logger.info("endpoint_created", endpoint_id=str(endpoint.id), url=endpoint.url)
        return endpoint

    async def get(self, endpoint_id: uuid.UUID) -> Optional[Endpoint]:
        result = await self._db.execute(
            select(Endpoint).where(Endpoint.id == endpoint_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, skip: int = 0, limit: int = 50) -> list[Endpoint]:
        result = await self._db.execute(select(Endpoint).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def update(self, endpoint_id: uuid.UUID, data: EndpointUpdate) -> Optional[Endpoint]:
        endpoint = await self.get(endpoint_id)
        if not endpoint:
            return None
        if data.url is not None:
            endpoint.url = str(data.url)
        if data.description is not None:
            endpoint.description = data.description
        if data.is_active is not None:
            endpoint.is_active = data.is_active
        if data.event_types is not None:
            endpoint.event_types = ",".join(data.event_types) if data.event_types else None
        if data.payload_schema is not None:
            endpoint.payload_schema = data.payload_schema
        if data.rate_limit_per_minute is not None:
            endpoint.rate_limit_per_minute = data.rate_limit_per_minute
        if data.circuit_threshold is not None:
            endpoint.circuit_threshold = data.circuit_threshold
        if data.circuit_cooldown_s is not None:
            endpoint.circuit_cooldown_s = data.circuit_cooldown_s
        await self._db.commit()
        await self._db.refresh(endpoint)
        return endpoint

    async def delete(self, endpoint_id: uuid.UUID) -> bool:
        endpoint = await self.get(endpoint_id)
        if not endpoint:
            return False
        await self._db.delete(endpoint)
        await self._db.commit()
        return True
