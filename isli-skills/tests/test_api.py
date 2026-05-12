"""API tests for isli-skills endpoints."""

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
    async def test_register_skill(self, client: AsyncClient):
        resp = await client.post("/skills", json={
            "name": "web-fetch",
            "endpoint": "http://localhost:8100",
            "health_endpoint": "http://localhost:8100/health",
            "description": "Fetch web pages",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "registered"
        assert data["skill"]["name"] == "web-fetch"

    @pytest.mark.asyncio
    async def test_register_skill_duplicate(self, client: AsyncClient):
        resp = await client.post("/skills", json={
            "name": "web-fetch",
            "endpoint": "http://localhost:8100",
        })
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_skill_health(self, client: AsyncClient):
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
        resp = await client.post("/skills/web-fetch/invoke", json={
            "action": "fetch",
            "payload": {"url": "https://example.com"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["skill"] == "web-fetch"
        assert data["action"] == "fetch"

    @pytest.mark.asyncio
    async def test_invoke_skill_404(self, client: AsyncClient):
        resp = await client.post("/skills/nonexistent/invoke", json={
            "action": "fetch",
            "payload": {},
        })
        assert resp.status_code == 404
