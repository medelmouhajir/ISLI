"""API tests for isli-skills endpoints."""

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


class TestSkillsAPI:
    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "isli-skills"

    @pytest.mark.asyncio
    async def test_live(self, client: AsyncClient):
        resp = await client.get("/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"

    @pytest.mark.asyncio
    async def test_ready(self, client: AsyncClient):
        resp = await client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "isli-skills"
        assert "skills_registered" in data

    @pytest.mark.asyncio
    async def test_list_skills_empty(self, client: AsyncClient):
        resp = await client.get("/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["skills"] == []

    @pytest.mark.asyncio
    async def test_register_skill_legacy_gone(self, client: AsyncClient):
        resp = await client.post("/skills", json={
            "name": "web-fetch",
            "endpoint": "http://localhost:8100",
            "health_endpoint": "http://localhost:8100/health",
            "description": "Fetch web pages",
        })
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_update_skill_legacy_gone(self, client: AsyncClient):
        resp = await client.post("/update", json={"name": "web-fetch"})
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_test_skill_legacy_gone(self, client: AsyncClient):
        resp = await client.post("/test", json={"code": "print(1)", "payload": {}})
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_skill_health(self, client: AsyncClient):
        from isli_skills.main import SKILL_REGISTRY
        SKILL_REGISTRY["web-fetch"] = {
            "name": "web-fetch",
            "endpoint": "http://localhost:8100",
            "type": "external",
        }
        resp = await client.get("/skills/web-fetch/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["skill"] == "web-fetch"

    @pytest.mark.asyncio
    async def test_skill_health_404(self, client: AsyncClient):
        resp = await client.get("/skills/nonexistent/health")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invoke_skill(self, client: AsyncClient):
        from isli_skills.main import SKILL_REGISTRY
        SKILL_REGISTRY["web-fetch"] = {
            "name": "web-fetch",
            "endpoint": "http://localhost:8100",
            "type": "external",
        }
        resp = await client.post("/skills/web-fetch/invoke", json={
            "action": "fetch",
            "payload": {"url": "https://example.com"},
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["skill"] == "web-fetch"
        assert data["action"] == "fetch"

    @pytest.mark.asyncio
    async def test_invoke_skill_404(self, client: AsyncClient):
        resp = await client.post("/skills/nonexistent/invoke", json={
            "action": "fetch",
            "payload": {},
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_fetch(self, client: AsyncClient, monkeypatch):
        # Avoid a hard Playwright browser dependency in unit tests.
        async_mock = AsyncMock(return_value={"url": "https://example.com", "mocked": True})
        monkeypatch.setattr("isli_skills.main.browse_url", async_mock)
        resp = await client.post("/fetch", json={
            "url": "https://example.com",
            "agent_id": "test-agent"
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://example.com"
