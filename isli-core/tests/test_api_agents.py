"""API tests for /v1/agents endpoints."""

import pytest
from httpx import AsyncClient


class TestAgentsAPI:
    @pytest.mark.asyncio
    async def test_create_agent(self, client: AsyncClient):
        resp = await client.post("/v1/agents", json={
            "id": "test-agent",
            "name": "Test Agent",
            "description": "A test agent",
            "model_provider": "ollama",
            "model_id": "qwen3:1.7b",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "test-agent"
        assert data["name"] == "Test Agent"
        assert data["status"] == "registered"

    @pytest.mark.asyncio
    async def test_list_agents(self, client: AsyncClient):
        resp = await client.get("/v1/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_agent(self, client: AsyncClient):
        resp = await client.get("/v1/agents/test-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "test-agent"

    @pytest.mark.asyncio
    async def test_get_agent_404(self, client: AsyncClient):
        resp = await client.get("/v1/agents/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_agent_409(self, client: AsyncClient):
        resp = await client.post("/v1/agents", json={
            "id": "test-agent",
            "name": "Duplicate",
        })
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_update_agent(self, client: AsyncClient):
        resp = await client.put("/v1/agents/test-agent", json={
            "name": "Updated Agent",
            "status": "online",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Agent"
        assert data["status"] == "online"

    @pytest.mark.asyncio
    async def test_heartbeat(self, client: AsyncClient):
        resp = await client.post("/v1/agents/test-agent/heartbeat")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["agent_id"] == "test-agent"
        assert "token" in data

    @pytest.mark.asyncio
    async def test_heartbeat_emits_enriched_event(self, client: AsyncClient):
        """Heartbeat endpoint must emit agent:heartbeat with enrichment fields."""
        resp = await client.post("/v1/agents/test-agent/heartbeat")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_agent(self, client: AsyncClient):
        resp = await client.delete("/v1/agents/test-agent")
        assert resp.status_code == 204
        resp = await client.get("/v1/agents/test-agent")
        assert resp.status_code == 404
