"""API tests for isli-keeper endpoints."""

import pytest
from httpx import AsyncClient


class TestKeeperAPI:
    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "isli-keeper"

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
        # Ollama may not be running, so ready could be degraded
        assert data["service"] == "isli-keeper"
        assert "ollama" in data
        assert "fallback_configured" in data

    @pytest.mark.asyncio
    async def test_heartbeat(self, client: AsyncClient):
        resp = await client.post("/heartbeat", json={
            "agent_id": "agent-1",
            "status": "online",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["agent_id"] == "agent-1"
        assert data["validated"] is True

    @pytest.mark.asyncio
    async def test_heartbeat_anomaly(self, client: AsyncClient):
        resp = await client.post("/heartbeat", json={
            "agent_id": "agent-1",
            "status": "online",
            "anomaly": "high_latency",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_embed_without_ollama(self, client: AsyncClient):
        # Without Ollama running, this should return 503
        resp = await client.post("/embed", json={"input": "hello world"})
        # We accept either 200 (if Ollama happens to be running) or 503
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_generate_without_ollama(self, client: AsyncClient):
        resp = await client.post("/generate", json={"prompt": "say hi"})
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_summarize_without_ollama(self, client: AsyncClient):
        resp = await client.post("/summarize", json={"text": "hello world", "max_length": 10})
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_models_without_ollama(self, client: AsyncClient):
        resp = await client.get("/models")
        assert resp.status_code in (200, 503)
