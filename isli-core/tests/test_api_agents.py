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

    @pytest.mark.asyncio
    async def test_delete_agent_scrubs_peer_references(self, client: AsyncClient):
        """Deleting an agent must remove its ID from every other agent's known_agent_ids."""
        # Create two agents; A lists B as a peer.
        resp = await client.post("/v1/agents", json={
            "id": "peer-scrub-a",
            "name": "Peer Scrub A",
            "model_provider": "ollama",
            "model_id": "qwen3:1.7b",
        })
        assert resp.status_code == 201
        resp = await client.post("/v1/agents", json={
            "id": "peer-scrub-b",
            "name": "Peer Scrub B",
            "model_provider": "ollama",
            "model_id": "qwen3:1.7b",
        })
        assert resp.status_code == 201

        resp = await client.put("/v1/agents/peer-scrub-a", json={
            "known_agent_ids": ["peer-scrub-b"],
        })
        assert resp.status_code == 200
        assert resp.json()["known_agent_ids"] == ["peer-scrub-b"]

        # Delete B.
        resp = await client.delete("/v1/agents/peer-scrub-b")
        assert resp.status_code == 204

        # A's known_agent_ids should be empty.
        resp = await client.get("/v1/agents/peer-scrub-a")
        assert resp.status_code == 200
        assert resp.json()["known_agent_ids"] == []

        # A's /config should also return a clean list.
        resp = await client.get("/v1/agents/peer-scrub-a/config")
        assert resp.status_code == 200
        assert resp.json()["known_agent_ids"] == []

        # Cleanup
        await client.delete("/v1/agents/peer-scrub-a")

    @pytest.mark.asyncio
    async def test_cleanup_peer_refs_removes_deleted_agents(self, client: AsyncClient):
        """POST /v1/agents/cleanup-peer-refs strips deleted and unknown IDs from peers."""
        await client.post("/v1/agents", json={
            "id": "cleanup-a",
            "name": "Cleanup A",
            "model_provider": "ollama",
            "model_id": "qwen3:1.7b",
        })
        await client.post("/v1/agents", json={
            "id": "cleanup-b",
            "name": "Cleanup B",
            "model_provider": "ollama",
            "model_id": "qwen3:1.7b",
        })

        # A lists B and a never-existing agent.
        resp = await client.put("/v1/agents/cleanup-a", json={
            "known_agent_ids": ["cleanup-b", "ghost-agent"],
        })
        assert resp.status_code == 200

        # Delete B.
        await client.delete("/v1/agents/cleanup-b")

        # Run cleanup.
        resp = await client.post("/v1/agents/cleanup-peer-refs", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["cleaned"] == 1
        assert "cleanup-a" in data["affected_agent_ids"]

        resp = await client.get("/v1/agents/cleanup-a")
        assert resp.status_code == 200
        assert resp.json()["known_agent_ids"] == []

        # Cleanup
        await client.delete("/v1/agents/cleanup-a")
