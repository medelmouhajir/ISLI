"""Tests for secrets SDK tools."""

import pytest
import respx
from httpx import Response

from isli_agent.client import CoreClient
from isli_agent.tools.secrets import get_secret, SecretNotFoundError, SecretAccessError


@respx.mock
@pytest.mark.asyncio
async def test_get_secret_success():
    route = respx.post("http://test-core/v1/skills/get-secret/get").mock(
        return_value=Response(200, json={"status": "ok", "name": "api_key", "value": "sk-test123"})
    )
    client = CoreClient(base_url="http://test-core", admin_key="admin-key")
    client.token = "agent-jwt-token"
    result = await get_secret("agent-1", "api_key", client)
    assert result == "sk-test123"
    assert route.called
    body = route.calls.last.request.content.decode()
    assert '"agent_id":"agent-1"' in body
    assert '"name":"api_key"' in body


@respx.mock
@pytest.mark.asyncio
async def test_get_secret_not_found():
    respx.post("http://test-core/v1/skills/get-secret/get").mock(
        return_value=Response(404, json={"detail": "Secret 'missing' not found"})
    )
    client = CoreClient(base_url="http://test-core", admin_key="admin-key")
    client.token = "agent-jwt-token"
    with pytest.raises(SecretNotFoundError):
        await get_secret("agent-1", "missing", client)


@respx.mock
@pytest.mark.asyncio
async def test_get_secret_access_denied():
    respx.post("http://test-core/v1/skills/get-secret/get").mock(
        return_value=Response(403, json={"detail": "Access denied"})
    )
    client = CoreClient(base_url="http://test-core", admin_key="admin-key")
    client.token = "agent-jwt-token"
    with pytest.raises(SecretAccessError):
        await get_secret("agent-1", "forbidden", client)
