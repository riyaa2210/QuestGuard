"""Pydantic schemas for Endpoint CRUD."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class EndpointCreate(BaseModel):
    url: AnyHttpUrl = Field(..., description="Destination URL that will receive webhook events")
    description: Optional[str] = Field(None, max_length=512)
    secret: Optional[str] = Field(
        None,
        min_length=8,
        max_length=256,
        description=(
            "HMAC-SHA256 signing secret. "
            "Each delivery will include X-QueueGuard-Signature: sha256=<hmac>. "
            "Stored in plaintext for Lambda signing; never returned in API responses."
        ),
    )
    event_types: Optional[list[str]] = Field(
        None,
        description="List of event type filters, e.g. ['order.created']. Empty = all events.",
    )
    payload_schema: Optional[dict[str, Any]] = Field(
        None,
        description="Optional JSON Schema (Draft 7). Submitted payloads are validated before enqueueing.",
    )
    rate_limit_per_minute: int = Field(
        0,
        ge=0,
        description="Max events per minute. 0 = unlimited.",
    )
    circuit_threshold: int = Field(5, ge=1, le=100)
    circuit_cooldown_s: int = Field(600, ge=10, le=86400)

    @field_validator("event_types")
    @classmethod
    def _normalise_event_types(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is not None:
            v = [e.strip().lower() for e in v if e.strip()]
        return v or None


class EndpointUpdate(BaseModel):
    url: Optional[AnyHttpUrl] = None
    description: Optional[str] = Field(None, max_length=512)
    is_active: Optional[bool] = None
    event_types: Optional[list[str]] = None
    payload_schema: Optional[dict[str, Any]] = None
    rate_limit_per_minute: Optional[int] = Field(None, ge=0)
    circuit_threshold: Optional[int] = Field(None, ge=1)
    circuit_cooldown_s: Optional[int] = Field(None, ge=10)


class EndpointResponse(BaseModel):
    id: uuid.UUID
    url: str
    description: Optional[str]
    is_active: bool
    event_types: Optional[list[str]]
    payload_schema: Optional[dict[str, Any]]
    rate_limit_per_minute: int
    circuit_state: str
    consecutive_failures: int
    circuit_threshold: int
    circuit_cooldown_s: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, obj) -> "EndpointResponse":
        event_types = None
        if obj.event_types:
            event_types = [e for e in obj.event_types.split(",") if e]
        return cls(
            id=obj.id,
            url=obj.url,
            description=obj.description,
            is_active=obj.is_active,
            event_types=event_types,
            payload_schema=obj.payload_schema,
            rate_limit_per_minute=obj.rate_limit_per_minute,
            circuit_state=obj.circuit_state,
            consecutive_failures=obj.consecutive_failures,
            circuit_threshold=obj.circuit_threshold,
            circuit_cooldown_s=obj.circuit_cooldown_s,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )
