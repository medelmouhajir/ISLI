"""Pytest fixtures for isli-skills integration tests."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from isli_skills.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Internal-Auth": "dev"},
    ) as ac:
        yield ac
