"""Tests for event submission, history, replay, and idempotency."""

import uuid
import pytest
from httpx import AsyncClient

from tests.conftest import create_endpoint, submit_event


@pytest.mark.asyncio
async def test_submit_event(client: AsyncClient):
    ep = await create_endpoint(client)
    resp = await client.post(
        f"/api/v1/events/{ep['id']}",
        json={"event_type": "order.created", "payload": {"order_id": 42}},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["event_type"] == "order.created"
    assert data["status"] == "queued"
    assert data["endpoint_id"] == ep["id"]


@pytest.mark.asyncio
async def test_submit_event_to_missing_endpoint(client: AsyncClient):
    resp = await client.post(
        f"/api/v1/events/{uuid.uuid4()}",
        json={"event_type": "test.event", "payload": {}},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_idempotency_duplicate_key_returns_200(client: AsyncClient):
    """Submitting the same idempotency key twice returns the original event (HTTP 200)."""
    ep = await create_endpoint(client)
    idem_key = f"order-{uuid.uuid4()}"

    first = await client.post(
        f"/api/v1/events/{ep['id']}",
        json={"event_type": "order.created", "payload": {"n": 1}, "idempotency_key": idem_key},
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    second = await client.post(
        f"/api/v1/events/{ep['id']}",
        json={"event_type": "order.created", "payload": {"n": 2}, "idempotency_key": idem_key},
    )
    assert second.status_code == 200
    # Must be the same event, not a new one
    assert second.json()["id"] == first_id
    # Payload must be from the original, not the duplicate submission
    assert second.json()["payload"]["n"] == 1


@pytest.mark.asyncio
async def test_idempotency_different_endpoints_are_independent(client: AsyncClient):
    """Same idempotency key on different endpoints is allowed."""
    ep1 = await create_endpoint(client, url="https://ep1.example.com/hook")
    ep2 = await create_endpoint(client, url="https://ep2.example.com/hook")
    idem_key = f"shared-key-{uuid.uuid4()}"

    r1 = await client.post(
        f"/api/v1/events/{ep1['id']}",
        json={"event_type": "test.event", "payload": {}, "idempotency_key": idem_key},
    )
    r2 = await client.post(
        f"/api/v1/events/{ep2['id']}",
        json={"event_type": "test.event", "payload": {}, "idempotency_key": idem_key},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


@pytest.mark.asyncio
async def test_list_events_for_endpoint(client: AsyncClient):
    ep = await create_endpoint(client, url="https://list-test.example.com/hook")
    for _ in range(3):
        await submit_event(client, ep["id"])

    resp = await client.get(f"/api/v1/events/{ep['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 3
    assert len(body["items"]) >= 3


@pytest.mark.asyncio
async def test_list_events_status_filter(client: AsyncClient):
    ep = await create_endpoint(client, url="https://filter-test.example.com/hook")
    await submit_event(client, ep["id"])

    resp_queued = await client.get(f"/api/v1/events/{ep['id']}?status=queued")
    assert resp_queued.status_code == 200
    assert all(e["status"] == "queued" for e in resp_queued.json()["items"])

    resp_delivered = await client.get(f"/api/v1/events/{ep['id']}?status=delivered")
    assert resp_delivered.status_code == 200
    assert resp_delivered.json()["total"] == 0


@pytest.mark.asyncio
async def test_get_event_detail(client: AsyncClient):
    ep = await create_endpoint(client, url="https://detail-test.example.com/hook")
    event = await submit_event(client, ep["id"])

    resp = await client.get(f"/api/v1/events/detail/{event['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == event["id"]


@pytest.mark.asyncio
async def test_replay_non_failed_event_returns_422(client: AsyncClient):
    """Replaying a queued/delivered event must be rejected."""
    ep = await create_endpoint(client, url="https://replay-test.example.com/hook")
    event = await submit_event(client, ep["id"])

    assert event["status"] == "queued"
    resp = await client.post(f"/api/v1/events/detail/{event['id']}/replay")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_event_invalid_type_rejected(client: AsyncClient):
    ep = await create_endpoint(client)
    resp = await client.post(
        f"/api/v1/events/{ep['id']}",
        json={"event_type": "bad type with spaces!", "payload": {}},
    )
    assert resp.status_code == 422
