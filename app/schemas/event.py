"""Pydantic schemas for WebhookEvent and DeliveryAttempt."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class EventSubmit(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=128, pattern=r"^[\w.\-]+$")
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = Field(
        None,
        max_length=256,
        description="Caller-supplied deduplication key. Same key+endpoint = no duplicate delivery.",
    )


class DeliveryAttemptResponse(BaseModel):
    id: uuid.UUID
    attempt_number: int
    status: str
    http_status_code: Optional[int]
    response_body: Optional[str]
    duration_ms: Optional[int]
    error_detail: Optional[str]
    ai_explanation: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class EventResponse(BaseModel):
    id: uuid.UUID
    endpoint_id: uuid.UUID
    event_type: str
    idempotency_key: Optional[str]
    payload: dict[str, Any]
    status: str
    sqs_message_id: Optional[str]
    attempt_count: int
    next_retry_at: Optional[datetime]
    trace_id: Optional[str]
    span_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    attempts: list[DeliveryAttemptResponse] = []

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    items: list[EventResponse]
    total: int
    page: int
    page_size: int
