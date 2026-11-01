"""Pydantic schemas for AlertRule."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import AnyHttpUrl, BaseModel, Field


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    window_minutes: int = Field(5, ge=1, le=60)
    failure_rate_threshold: float = Field(0.2, ge=0.0, le=1.0)
    min_sample_size: int = Field(3, ge=1)
    notification_url: Optional[AnyHttpUrl] = Field(
        None,
        description="Webhook URL to POST an alert payload to when the rule fires.",
    )


class AlertRuleResponse(BaseModel):
    id: uuid.UUID
    endpoint_id: uuid.UUID
    name: str
    window_minutes: int
    failure_rate_threshold: float
    min_sample_size: int
    is_active: bool
    last_fired_at: Optional[datetime]
    notification_url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DeliveryStatsResponse(BaseModel):
    endpoint_id: uuid.UUID
    window_hours: int
    total_attempts: int
    success_count: int
    failure_count: int
    success_rate: float
    p50_ms: Optional[float]
    p95_ms: Optional[float]
    p99_ms: Optional[float]


class FanoutSubmit(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=128, pattern=r"^[\w.\-]+$")
    payload: dict = Field(default_factory=dict)
    idempotency_key: Optional[str] = Field(None, max_length=256)


class FanoutResult(BaseModel):
    event_type: str
    matched_endpoints: int
    results: list[dict]
