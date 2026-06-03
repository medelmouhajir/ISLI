"""Pytest fixtures for isli-core integration tests."""

import asyncio
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from isli_core.main import app
from isli_core.db import init_db, close_db
from isli_core.models import Base


# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def _setup_test_db():
    await init_db(TEST_DATABASE_URL)
    yield
    await close_db()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    from isli_core.db import async_session
    if async_session is None:
        raise RuntimeError("Database not initialized")
    async with async_session() as session:
        yield session


class _MockProcessManager:
    """Minimal mock for AgentProcessManager in API tests."""
    async def spawn(self, agent_id: str) -> None:
        pass
    async def terminate(self, agent_id: str) -> None:
        pass
    def get_status(self, agent_id: str) -> dict:
        return {"running": False}
    def is_running(self, agent_id: str) -> bool:
        return False
    async def reconcile(self) -> None:
        pass


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    headers = {"Authorization": "Bearer isli-admin-dev-key"}
    app.state.process_manager = _MockProcessManager()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
        yield ac
