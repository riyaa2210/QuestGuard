"""Shared pytest fixtures for QueueGuard tests.

Uses an in-memory SQLite database (via aiosqlite) for speed.
SQS calls are mocked with moto or monkeypatching so no real AWS is needed.
"""

import asyncio
import json
import uuid
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models.base import Base

# ── In-memory SQLite async engine ─────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
_TestSessionLocal = async_sessionmaker(_engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Use a single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with _TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with DB and SQS overridden."""

    async def _override_get_db():
        yield db

    # Stub SQS producer so tests don't need real AWS
    mock_producer = MagicMock()
    mock_producer.enqueue_event.return_value = str(uuid.uuid4())

    app.dependency_overrides[get_db] = _override_get_db

    with patch("app.services.sqs_producer.get_producer", return_value=mock_producer):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def create_endpoint(client: AsyncClient, **kwargs) -> dict:
    payload = {"url": "https://example.com/hook", **kwargs}
    resp = await client.post("/api/v1/endpoints", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def submit_event(client: AsyncClient, endpoint_id: str, **kwargs) -> dict:
    payload = {"event_type": "test.event", "payload": {"k": "v"}, **kwargs}
    resp = await client.post(f"/api/v1/events/{endpoint_id}", json=payload)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()
