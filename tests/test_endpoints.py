"""Tests for endpoint CRUD routes."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_endpoint(client: AsyncClient):
    resp = await client.post(
        "/api/v1/endpoints",
        json={"url": "https://hooks.example.com/receive", "description": "Test hook"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["url"] == "https://hooks.example.com/receive"
    assert data["is_active"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_create_endpoint_invalid_url(client: AsyncClient):
    resp = await client.post("/api/v1/endpoints", json={"url": "not-a-url"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_endpoints(client: AsyncClient):
    # Create two endpoints
    for i in range(2):
        await client.post(
            "/api/v1/endpoints",
            json={"url": f"https://example.com/hook{i}"},
        )
    resp = await client.get("/api/v1/endpoints")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.asyncio
async def test_get_endpoint(client: AsyncClient):
    create = await client.post(
        "/api/v1/endpoints", json={"url": "https://example.com/get-test"}
    )
    ep_id = create.json()["id"]

    resp = await client.get(f"/api/v1/endpoints/{ep_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == ep_id


@pytest.mark.asyncio
async def test_get_endpoint_not_found(client: AsyncClient):
    import uuid
    resp = await client.get(f"/api/v1/endpoints/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_endpoint(client: AsyncClient):
    create = await client.post(
        "/api/v1/endpoints", json={"url": "https://example.com/update-test"}
    )
    ep_id = create.json()["id"]

    resp = await client.patch(f"/api/v1/endpoints/{ep_id}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_delete_endpoint(client: AsyncClient):
    create = await client.post(
        "/api/v1/endpoints", json={"url": "https://example.com/delete-test"}
    )
    ep_id = create.json()["id"]

    resp = await client.delete(f"/api/v1/endpoints/{ep_id}")
    assert resp.status_code == 204

    # Should be gone
    resp = await client.get(f"/api/v1/endpoints/{ep_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_to_disabled_endpoint(client: AsyncClient):
    create = await client.post(
        "/api/v1/endpoints", json={"url": "https://example.com/disabled"}
    )
    ep_id = create.json()["id"]
    await client.patch(f"/api/v1/endpoints/{ep_id}", json={"is_active": False})

    resp = await client.post(
        f"/api/v1/events/{ep_id}",
        json={"event_type": "test.event", "payload": {}},
    )
    assert resp.status_code == 422
