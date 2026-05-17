import pytest
from fastapi.testclient import TestClient
from isli_core.main import app
from isli_core.auth import create_internal_token
from unittest.mock import patch, MagicMock, AsyncMock

client = TestClient(app)

@pytest.fixture
def agent_1_token():
    return create_internal_token("agent_1", ["memory:write", "memory:read"])

@pytest.fixture
def agent_2_token():
    return create_internal_token("agent_2", ["memory:write", "memory:read"])

@patch("isli_core.routers.memory.chroma")
def test_save_memory_scoped(mock_chroma, agent_1_token):
    mock_chroma.save_fact = AsyncMock()
    
    response = client.post(
        "/v1/memory/save",
        json={"content": "test fact", "metadata": {"key": "value"}},
        headers={"Authorization": f"Bearer {agent_1_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["collection"] == "agent:agent_1"
    assert data["status"] == "saved"
    
    # Verify chroma was called with correct collection
    mock_chroma.save_fact.assert_called_once()
    args, kwargs = mock_chroma.save_fact.call_args
    assert kwargs["collection_name"] == "agent:agent_1"

@patch("isli_core.routers.memory.chroma")
def test_search_memory_scoped_success(mock_chroma, agent_1_token):
    mock_chroma.search_facts = AsyncMock(return_value={"ids": [], "documents": []})
    
    response = client.get(
        "/v1/memory/search?collection=agent:agent_1",
        headers={"Authorization": f"Bearer {agent_1_token}"}
    )
    assert response.status_code == 200
    
    mock_chroma.search_facts.assert_called_once()
    args, kwargs = mock_chroma.search_facts.call_args
    assert kwargs["collection_name"] == "agent:agent_1"

@patch("isli_core.routers.memory.chroma")
def test_search_memory_scoped_denied(mock_chroma, agent_1_token):
    response = client.get(
        "/v1/memory/search?collection=agent:agent_2",
        headers={"Authorization": f"Bearer {agent_1_token}"}
    )
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]
    
    # Verify chroma was NOT called
    mock_chroma.search_facts.assert_not_called()

@patch("isli_core.routers.memory.chroma")
def test_search_memory_global_success(mock_chroma, agent_1_token):
    mock_chroma.search_facts = AsyncMock(return_value={"ids": [], "documents": []})
    
    response = client.get(
        "/v1/memory/search?collection=global",
        headers={"Authorization": f"Bearer {agent_1_token}"}
    )
    assert response.status_code == 200
    
    mock_chroma.search_facts.assert_called_once()
    args, kwargs = mock_chroma.search_facts.call_args
    assert kwargs["collection_name"] == "global"
