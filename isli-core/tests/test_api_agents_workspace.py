import os
from pathlib import Path

import pytest
from httpx import AsyncClient

from isli_core.config import get_settings


class TestAgentWorkspaceLifecycle:
    @pytest.fixture(autouse=True)
    def temp_workspace(self, monkeypatch, tmp_path):
        ws = tmp_path / "workspaces"
        ws.mkdir()
        monkeypatch.setattr(get_settings(), "workspace_base_path", str(ws))
        yield str(ws)

    @pytest.mark.asyncio
    async def test_workspace_created_on_agent_creation(self, client: AsyncClient, temp_workspace):
        resp = await client.post("/v1/agents", json={"name": "TestBot", "id": "test-agent-1"})
        assert resp.status_code == 201
        ws_path = Path(temp_workspace) / "test-agent-1"
        assert ws_path.is_dir()

    @pytest.mark.asyncio
    async def test_workspace_archived_on_agent_deletion(self, client: AsyncClient, temp_workspace):
        await client.post("/v1/agents", json={"name": "DeleteBot", "id": "test-agent-2"})
        ws_path = Path(temp_workspace) / "test-agent-2"
        assert ws_path.is_dir()

        resp = await client.delete("/v1/agents/test-agent-2")
        assert resp.status_code == 204
        assert not ws_path.exists()
        archives = list(Path(temp_workspace).glob("test-agent-2.deleted.*"))
        assert len(archives) == 1
        assert archives[0].is_dir()
