"""Alert rule management and delivery stats routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.alert import AlertRuleCreate, AlertRuleResponse, DeliveryStatsResponse, FanoutResult, FanoutSubmit
from app.services.alert_service import AlertService
from app.services.endpoint_service import EndpointService
from app.services.fanout_service import FanoutService
from app.services.stats_service import get_endpoint_stats

router = APIRouter()


# ── Delivery stats ─────────────────────────────────────────────────────────────

@router.get(
    "/endpoints/{endpoint_id}/stats",
    response_model=DeliveryStatsResponse,
    summary="Delivery latency percentiles (p50/p95/p99) for an endpoint",
)
async def endpoint_stats(
    endpoint_id: uuid.UUID,
    window_hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    ep_svc = EndpointService(db)
    if not await ep_svc.get(endpoint_id):
        raise HTTPException(status_code=404, detail="Endpoint not found")

    stats = await get_endpoint_stats(db, endpoint_id, window_hours)
    return DeliveryStatsResponse(
        endpoint_id=stats.endpoint_id,
        window_hours=stats.window_hours,
        total_attempts=stats.total_attempts,
        success_count=stats.success_count,
        failure_count=stats.failure_count,
        success_rate=stats.success_rate,
        p50_ms=stats.p50_ms,
        p95_ms=stats.p95_ms,
        p99_ms=stats.p99_ms,
    )


# ── Alert rules ────────────────────────────────────────────────────────────────

@router.post(
    "/endpoints/{endpoint_id}/alerts",
    response_model=AlertRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an alert rule for an endpoint",
)
async def create_alert_rule(
    endpoint_id: uuid.UUID,
    body: AlertRuleCreate,
    db: AsyncSession = Depends(get_db),
):
    ep_svc = EndpointService(db)
    if not await ep_svc.get(endpoint_id):
        raise HTTPException(status_code=404, detail="Endpoint not found")

    svc = AlertService(db)
    rule = await svc.create_rule(endpoint_id, body)
    return AlertRuleResponse.model_validate(rule, from_attributes=True)


@router.get(
    "/endpoints/{endpoint_id}/alerts",
    response_model=list[AlertRuleResponse],
    summary="List alert rules for an endpoint",
)
async def list_alert_rules(
    endpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    ep_svc = EndpointService(db)
    if not await ep_svc.get(endpoint_id):
        raise HTTPException(status_code=404, detail="Endpoint not found")

    svc = AlertService(db)
    rules = await svc.list_rules(endpoint_id)
    return [AlertRuleResponse.model_validate(r, from_attributes=True) for r in rules]


@router.delete(
    "/alerts/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an alert rule",
)
async def delete_alert_rule(rule_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = AlertService(db)
    if not await svc.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Alert rule not found")


# ── Fan-out ────────────────────────────────────────────────────────────────────

@router.post(
    "/fanout",
    response_model=FanoutResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Broadcast an event to all matching active endpoints (fan-out)",
)
async def fanout_event(body: FanoutSubmit, db: AsyncSession = Depends(get_db)):
    svc = FanoutService(db)
    results = await svc.fanout(body)
    await db.commit()
    return FanoutResult(
        event_type=body.event_type,
        matched_endpoints=len(results),
        results=results,
    )
