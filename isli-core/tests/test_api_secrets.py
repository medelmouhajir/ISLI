"""API tests for /v1/secrets endpoints and inline get-secret skill."""

import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def _patch_encryption_key(monkeypatch):
    """Ensure PII encryption key is set for secret vault tests."""
    import isli_core.compliance.encryption as enc_mod
    monkeypatch.setattr(enc_mod, "ENCRYPTION_KEY", "test-encryption-key-32-bytes!!")


class TestSecretsAPI:
    async def _ensure_agent(self, client: AsyncClient, agent_id: str):
        resp = await client.post("/v1/agents", json={
            "id": agent_id,
            "name": f"Agent {agent_id}",
            "model_provider": "ollama",
            "model_id": "qwen3:1.7b",
        })
        if resp.status_code == 409:
            # Agent already exists from a previous test run
            pass
        else:
            assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_secret(self, client: AsyncClient):
        await self._ensure_agent(client, "secret-agent")
        resp = await client.post("/v1/secrets", json={
            "agent_id": "secret-agent",
            "name": "test_key",
            "value": "super-secret-value",
            "description": "A test secret",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["name"] == "test_key"

    @pytest.mark.asyncio
    async def test_list_secrets(self, client: AsyncClient):
        await self._ensure_agent(client, "secret-agent")
        await client.post("/v1/secrets", json={
            "agent_id": "secret-agent",
            "name": "list_key",
            "value": "list-value",
            "description": "For listing",
        })
        resp = await client.get("/v1/secrets?agent_id=secret-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(s["name"] == "list_key" for s in data)
        # Values must never be exposed
        assert all("value" not in s for s in data)

    @pytest.mark.asyncio
    async def test_update_existing_secret(self, client: AsyncClient):
        await self._ensure_agent(client, "secret-agent")
        await client.post("/v1/secrets", json={
            "agent_id": "secret-agent",
            "name": "update_key",
            "value": "original",
        })
        resp = await client.post("/v1/secrets", json={
            "agent_id": "secret-agent",
            "name": "update_key",
            "value": "updated-value",
            "description": "Updated description",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_get_secret_value_via_skill_proxy(self, client: AsyncClient):
        await self._ensure_agent(client, "secret-agent")
        await client.post("/v1/secrets", json={
            "agent_id": "secret-agent",
            "name": "get_key",
            "value": "expected-value",
        })
        resp = await client.post("/v1/skills/get-secret/get", json={
            "agent_id": "secret-agent",
            "name": "get_key",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["name"] == "get_key"
        assert data["value"] == "expected-value"

    @pytest.mark.asyncio
    async def test_get_secret_not_found(self, client: AsyncClient):
        await self._ensure_agent(client, "secret-agent")
        resp = await client.post("/v1/skills/get-secret/get", json={
            "agent_id": "secret-agent",
            "name": "nonexistent",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_secret(self, client: AsyncClient):
        await self._ensure_agent(client, "secret-agent")
        await client.post("/v1/secrets", json={
            "agent_id": "secret-agent",
            "name": "del_key",
            "value": "to-delete",
        })
        resp = await client.delete("/v1/secrets/del_key?agent_id=secret-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_secret_not_found(self, client: AsyncClient):
        await self._ensure_agent(client, "secret-agent")
        resp = await client.delete("/v1/secrets/missing?agent_id=secret-agent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_agent_isolation(self, client: AsyncClient):
        await self._ensure_agent(client, "secret-agent")
        await self._ensure_agent(client, "other-agent")
        await client.post("/v1/secrets", json={
            "agent_id": "other-agent",
            "name": "other_key",
            "value": "other-value",
        })

        # First agent should not see other agent's secret
        resp = await client.post("/v1/skills/get-secret/get", json={
            "agent_id": "secret-agent",
            "name": "other_key",
        })
        assert resp.status_code == 404
