import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock
from isli_keeper.main import app
from isli_keeper.auth import require_internal_auth

app.dependency_overrides[require_internal_auth] = lambda: {"sub": "test-agent"}

@pytest.mark.asyncio
async def test_context_inject_recent_fallback(client: AsyncClient):
    """Test that context/inject falls back to recent memories if no task description is provided."""
    with patch("isli_keeper.main.get_recent_memories", new_callable=AsyncMock) as mock_recent:
        mock_recent.return_value = ["recent fact"]
        
        resp = await client.post("/context/inject", json={
            "agent_id": "agent-1"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "recent fact" in data["context_summary"]
        mock_recent.assert_called_once_with("agent-1")

@pytest.mark.asyncio
async def test_context_inject_semantic_search(client: AsyncClient):
    """Test that context/inject uses semantic search when task description is provided."""
    with patch("isli_keeper.main.OllamaClient") as mock_ollama, \
         patch("isli_keeper.main.get_relevant_memories", new_callable=AsyncMock) as mock_relevant:
        
        mock_relevant.return_value = ["semantic fact"]
        mock_session = AsyncMock()
        mock_ollama.return_value.session.return_value.__aenter__.return_value = mock_session
        mock_session.embed.return_value = [0.1] * 768
        
        resp = await client.post("/context/inject", json={
            "agent_id": "agent-1",
            "task_description": "test task"
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert "semantic fact" in data["context_summary"]
        mock_relevant.assert_called_once()
        mock_session.embed.assert_called_once()

@pytest.mark.asyncio
async def test_context_inject_semantic_fallback(client: AsyncClient):
    """Test that context/inject falls back to recent memories if semantic search fails."""
    with patch("isli_keeper.main.OllamaClient") as mock_ollama, \
         patch("isli_keeper.main.get_recent_memories", new_callable=AsyncMock) as mock_recent:
        
        mock_session = AsyncMock()
        mock_ollama.return_value.session.return_value.__aenter__.return_value = mock_session
        mock_session.embed.side_effect = Exception("Ollama error")
        mock_recent.return_value = ["fallback fact"]
        
        resp = await client.post("/context/inject", json={
            "agent_id": "agent-1",
            "task_description": "test task"
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert "fallback fact" in data["context_summary"]
        mock_recent.assert_called_once()
