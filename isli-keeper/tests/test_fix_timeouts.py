import pytest
import httpx
from httpx import AsyncClient, Response
from unittest.mock import patch, MagicMock
from isli_keeper.main import app
from isli_keeper.auth import require_internal_auth

# Mock auth dependency
async def mock_require_internal_auth():
    return {"sub": "system", "scopes": ["*"]}

@pytest.mark.asyncio
async def test_heartbeat_validate_timeout_fail_open(client: AsyncClient):
    app.dependency_overrides[require_internal_auth] = mock_require_internal_auth
    try:
        # Mock OllamaClient.generate to raise a timeout
        with patch("isli_keeper.ollama_client.OllamaClient.generate", side_effect=httpx.TimeoutException("Timeout")):
            resp = await client.post("/heartbeat/validate", json={
                "agent_id": "agent-1",
                "heartbeat_at": "2026-05-19T22:12:13Z"
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_valid"] is True
            assert "Validation failed, failing open" in data.get("note", "")
    finally:
        del app.dependency_overrides[require_internal_auth]

@pytest.mark.asyncio
async def test_heartbeat_validate_generic_error_fail_open(client: AsyncClient):
    app.dependency_overrides[require_internal_auth] = mock_require_internal_auth
    try:
        # Mock OllamaClient.generate to raise a generic error
        with patch("isli_keeper.ollama_client.OllamaClient.generate", side_effect=ValueError("Something went wrong")):
            resp = await client.post("/heartbeat/validate", json={
                "agent_id": "agent-1",
                "heartbeat_at": "2026-05-19T22:12:13Z"
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_valid"] is True
            assert "Validation failed, failing open" in data.get("note", "")
    finally:
        del app.dependency_overrides[require_internal_auth]
