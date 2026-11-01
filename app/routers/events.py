"""Event submission, history, and replay routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.event import DeliveryAttemptResponse, EventListResponse, EventResponse, EventSubmit
from app.services.endpoint_service import EndpointService
from app.services.event_service import CircuitOpenError, EventService, RateLimitExceeded, SchemaValidationError

router = APIRouter()


@router.post(
    "/{endpoint_id}",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a webhook event to a registered endpoint",
)
async def submit_event(
    endpoint_id: uuid.UUID,
    body: EventSubmit,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    ep_svc = EndpointService(db)
    endpoint = await ep_svc.get(endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
    if not endpoint.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Endpoint is disabled"
        )

    ev_svc = EventService(db)
    try:
        event, is_duplicate = await ev_svc.submit(endpoint_id, body, endpoint)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": "60"},
        )
    except CircuitOpenError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Circuit breaker is open for this endpoint. Deliveries are paused. {exc}",
        )
    except SchemaValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Payload failed schema validation", "errors": exc.errors},
        )

    if is_duplicate:
        response.status_code = status.HTTP_200_OK

    return EventResponse.model_validate(event, from_attributes=True)


@router.get(
    "/{endpoint_id}",
    response_model=EventListResponse,
    summary="List delivery history for an endpoint",
)
async def list_events(
    endpoint_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    ep_svc = EndpointService(db)
    if not await ep_svc.get(endpoint_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    ev_svc = EventService(db)
    events, total = await ev_svc.list_for_endpoint(
        endpoint_id, status=status_filter, page=page, page_size=page_size
    )
    return EventListResponse(
        items=[EventResponse.model_validate(e, from_attributes=True) for e in events],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/detail/{event_id}",
    response_model=EventResponse,
    summary="Get a single event with all delivery attempts",
)
async def get_event(event_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    ev_svc = EventService(db)
    event = await ev_svc.get(event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return EventResponse.model_validate(event, from_attributes=True)


@router.post(
    "/detail/{event_id}/replay",
    response_model=EventResponse,
    summary="Re-enqueue a failed or dead-lettered event",
)
async def replay_event(event_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    ev_svc = EventService(db)
    try:
        event = await ev_svc.replay(event_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return EventResponse.model_validate(event, from_attributes=True)


@router.get(
    "/detail/{event_id}/attempts",
    response_model=list[DeliveryAttemptResponse],
    summary="List all delivery attempts for an event",
)
async def list_attempts(event_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    ev_svc = EventService(db)
    event = await ev_svc.get(event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    attempts = await ev_svc.list_attempts(event_id)
    return [DeliveryAttemptResponse.model_validate(a, from_attributes=True) for a in attempts]
