import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock
from isli_keeper.main import app
from isli_keeper.auth import require_internal_auth

app.dependency_overrides[require_internal_auth] = lambda: {"sub": "test-agent"}

@pytest.mark.asyncio
async def test_context_inject_no_task_no_fallback(client: AsyncClient):
    """Test that context/inject returns empty memories if no task description is provided (no more unconditional fallback)."""
    with patch("isli_keeper.main.get_recent_memories", new_callable=AsyncMock) as mock_recent:
        resp = await client.post("/context/inject", json={
            "agent_id": "agent-1"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "HISTORICAL MEMORIES" not in data["context_summary"]
        mock_recent.assert_not_called()

@pytest.mark.asyncio
async def test_context_inject_semantic_search(client: AsyncClient):
    """Test that context/inject uses semantic search with threshold when task description is provided."""
    with patch("isli_keeper.main.OllamaClient") as mock_ollama, \
         patch("isli_keeper.main.get_relevant_memories", new_callable=AsyncMock) as mock_relevant:
        
        mock_relevant.return_value = ["semantic fact"]
        mock_session = AsyncMock()
        mock_ollama.return_value.session.return_value.__aenter__.return_value = mock_session
        mock_session.embed.return_value = [0.1] * 768
        
        resp = await client.post("/context/inject", json={
            "agent_id": "agent-1",
            "task_description": "test task",
            "memory_similarity_threshold": 0.25
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert "semantic fact" in data["context_summary"]
        # Check that threshold was passed
        mock_relevant.assert_called_once_with("agent-1", [0.1]*768, threshold=0.25)
        mock_session.embed.assert_called_once()

@pytest.mark.asyncio
async def test_context_inject_semantic_fallback_capped(client: AsyncClient):
    """Test that context/inject falls back to recent memories capped at 3 if semantic search returns nothing or fails."""
    with patch("isli_keeper.main.OllamaClient") as mock_ollama, \
         patch("isli_keeper.main.get_recent_memories", new_callable=AsyncMock) as mock_recent, \
         patch("isli_keeper.main.get_relevant_memories", new_callable=AsyncMock) as mock_relevant:
        
        mock_session = AsyncMock()
        mock_ollama.return_value.session.return_value.__aenter__.return_value = mock_session
        mock_session.embed.return_value = [0.1] * 768
        
        # Case 1: Semantic search returns nothing above threshold
        mock_relevant.return_value = []
        mock_recent.return_value = ["fallback fact"]
        
        resp = await client.post("/context/inject", json={
            "agent_id": "agent-1",
            "task_description": "test task"
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert "fallback fact" in data["context_summary"]
        mock_recent.assert_called_with("agent-1", limit=3)
        
        # Case 2: Semantic search (embedding) fails
        mock_session.embed.side_effect = Exception("Ollama error")
        mock_recent.reset_mock()
        
        resp = await client.post("/context/inject", json={
            "agent_id": "agent-1",
            "task_description": "test task"
        })
        
        assert resp.status_code == 200
        assert "fallback fact" in resp.json()["context_summary"]
        mock_recent.assert_called_with("agent-1", limit=3)
