"""API tests for /v1/system endpoints."""

import pytest
from httpx import AsyncClient


class TestSystemAPI:
    @pytest.mark.asyncio
    async def test_cost_dashboard(self, client: AsyncClient):
        resp = await client.get("/v1/system/cost/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_agents" in data
        assert "total_tasks" in data
        assert "total_cost_usd" in data

    @pytest.mark.asyncio
    async def test_compliance_consents(self, client: AsyncClient):
        resp = await client.post("/v1/system/compliance/consents", json={
            "user_id": "user-1",
            "channel": "telegram",
            "purpose": "marketing",
            "granted": True,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["user_id"] == "user-1"
        assert data["granted"] is True

        list_resp = await client.get("/v1/system/compliance/consents/user-1")
        assert list_resp.status_code == 200
        consents = list_resp.json()
        assert len(consents) >= 1

    @pytest.mark.asyncio
    async def test_audit_logs(self, client: AsyncClient):
        resp = await client.get("/v1/system/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
