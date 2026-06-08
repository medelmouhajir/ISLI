import pytest
import httpx
from httpx import AsyncClient, Response
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from isli_keeper.main import app, _compress_activity_log, _generate_with_ollama
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


@pytest.mark.asyncio
async def test_heartbeat_validate_filters_benign_loop_hallucination(client: AsyncClient):
    """Benign 'looping with no forward progress' must be filtered to valid."""
    app.dependency_overrides[require_internal_auth] = mock_require_internal_auth
    try:
        fake_response = {
            "response": '{"is_valid": false, "anomaly": "Agent is looping with no forward progress"}'
        }
        with patch("isli_keeper.main._generate_with_ollama", return_value=fake_response):
            resp = await client.post("/heartbeat/validate", json={
                "agent_id": "agent-1",
                "heartbeat_at": "2026-05-19T22:12:13Z"
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_valid"] is True
            assert data.get("anomaly") is None
    finally:
        del app.dependency_overrides[require_internal_auth]


@pytest.mark.asyncio
async def test_heartbeat_validate_trusts_real_infinite_loop(client: AsyncClient):
    """Real 'infinite loop' patterns must still be trusted."""
    app.dependency_overrides[require_internal_auth] = mock_require_internal_auth
    try:
        fake_response = {
            "response": '{"is_valid": false, "anomaly": "Agent stuck in infinite loop"}'
        }
        with patch("isli_keeper.main._generate_with_ollama", return_value=fake_response):
            resp = await client.post("/heartbeat/validate", json={
                "agent_id": "agent-1",
                "heartbeat_at": "2026-05-19T22:12:13Z"
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_valid"] is False
            assert "infinite loop" in (data.get("anomaly") or "").lower()
    finally:
        del app.dependency_overrides[require_internal_auth]


def test_compress_activity_log_returns_idle_message_for_stale_entries():
    """Entries older than 1 hour should produce the idle sentinel message."""
    now = datetime.now(timezone.utc)
    stale_entries = [
        (now - timedelta(hours=2), "Agent was awaiting user input."),
        (now - timedelta(hours=3), "Agent was awaiting user input."),
    ]
    result = _compress_activity_log(stale_entries)
    assert "Agent is idle" in result
    assert "no anomaly possible" in result


def test_compress_activity_log_includes_recent_entries():
    """Recent entries should be formatted normally."""
    now = datetime.now(timezone.utc)
    recent_entries = [
        (now - timedelta(minutes=5), "Processed task abc-123."),
        (now - timedelta(minutes=10), "Processed task abc-122."),
    ]
    result = _compress_activity_log(recent_entries)
    assert "Processed task abc-123" in result
    assert "Processed task abc-122" in result
