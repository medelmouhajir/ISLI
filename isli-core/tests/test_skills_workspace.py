"""Tests for workspace skill proxy integration in isli-core."""

import os
from pathlib import Path

import pytest
from httpx import AsyncClient

from isli_core.config import get_settings


class TestSkillsWorkspaceProxy:
    @pytest.fixture(autouse=True)
    def temp_workspace(self, monkeypatch, tmp_path):
        ws = tmp_path / "workspaces"
        ws.mkdir()
        monkeypatch.setattr(get_settings(), "workspace_base_path", str(ws))
        yield str(ws)

    @pytest.mark.asyncio
    async def test_file_write_skill_registered(self, client: AsyncClient):
        # The skill registry in isli-core must contain file-write
        resp = await client.post("/v1/skills/file-write/write", json={
            "agent_id": "test-agent",
            "path": "notes.txt",
            "content": "hello from skill",
        })
        # We expect this to either succeed (if workspace is reachable)
        # or return 503/404 if workspace is not running in test env.
        # The important thing is it doesn't return 404 "Skill not found".
        assert resp.status_code != 404
        detail = resp.json() if resp.status_code != 204 else {}
        if resp.status_code == 404:
            assert "not found" not in str(detail).lower()

    @pytest.mark.asyncio
    async def test_file_read_skill_registered(self, client: AsyncClient):
        resp = await client.post("/v1/skills/file-read/read", json={
            "agent_id": "test-agent",
            "path": "notes.txt",
        })
        assert resp.status_code != 404

    @pytest.mark.asyncio
    async def test_send_message_skill_registered(self, client: AsyncClient):
        resp = await client.post("/v1/skills/send-message/send", json={
            "agent_id": "test-agent",
            "channel": "telegram",
            "channel_user_id": "12345",
            "text": "hello",
        })
        # 404 "Agent not found" is acceptable here — it proves the inline handler
        # was reached (the skill is registered). We only want to reject a 404
        # that says the skill itself is unregistered.
        if resp.status_code == 404:
            detail = resp.json().get("detail", "")
            assert "skill 'send-message' not registered" not in detail.lower()
            assert "action 'send' not found" not in detail.lower()

    @pytest.mark.asyncio
    async def test_shared_file_read_skill_registered(self, client: AsyncClient):
        resp = await client.post("/v1/skills/shared-file-read/read", json={
            "agent_id": "test-agent",
            "workspace_id": "ws-1",
            "path": "notes.txt",
        })
        assert resp.status_code != 404
        if resp.status_code == 404:
            detail = resp.json().get("detail", "")
            assert "skill 'shared-file-read' not registered" not in detail.lower()

    @pytest.mark.asyncio
    async def test_shared_file_write_skill_registered(self, client: AsyncClient):
        resp = await client.post("/v1/skills/shared-file-write/write", json={
            "agent_id": "test-agent",
            "workspace_id": "ws-1",
            "path": "notes.txt",
            "content": "hello",
        })
        assert resp.status_code != 404

    @pytest.mark.asyncio
    async def test_shared_file_list_skill_registered(self, client: AsyncClient):
        resp = await client.post("/v1/skills/shared-file-list/list", json={
            "agent_id": "test-agent",
            "workspace_id": "ws-1",
            "path": "",
        })
        assert resp.status_code != 404

    @pytest.mark.asyncio
    async def test_shared_file_delete_skill_registered(self, client: AsyncClient):
        resp = await client.post("/v1/skills/shared-file-delete/delete", json={
            "agent_id": "test-agent",
            "workspace_id": "ws-1",
            "path": "notes.txt",
        })
        assert resp.status_code != 404

    @pytest.mark.asyncio
    async def test_shared_file_move_skill_registered(self, client: AsyncClient):
        resp = await client.post("/v1/skills/shared-file-move/move", json={
            "agent_id": "test-agent",
            "source_workspace_id": "ws-1",
            "source_path": "a.txt",
            "target_path": "b.txt",
        })
        assert resp.status_code != 404

    @pytest.mark.asyncio
    async def test_shared_workspace_search_skill_registered(self, client: AsyncClient):
        resp = await client.post("/v1/skills/shared-workspace-search/search", json={
            "agent_id": "test-agent",
            "workspace_id": "ws-1",
            "query": "foo",
        })
        assert resp.status_code != 404

    @pytest.mark.asyncio
    async def test_shared_promote_file_workspace_skill_registered(self, client: AsyncClient):
        resp = await client.post("/v1/skills/shared-promote-file-workspace/promote", json={
            "agent_id": "test-agent",
            "workspace_id": "ws-1",
            "source_path": "local.txt",
            "target_path": "shared.txt",
        })
        # Expect 404 "Shared workspace not found" because ws-1 does not exist in the
        # test DB — this proves the inline handler was reached.
        if resp.status_code == 404:
            detail = resp.json().get("detail", "")
            assert "skill 'shared-promote-file-workspace' not registered" not in detail.lower()

    @pytest.mark.asyncio
    async def test_shared_workspace_info_skill_registered(self, client: AsyncClient):
        resp = await client.post("/v1/skills/shared-workspace-info/info", json={
            "agent_id": "test-agent",
            "workspace_id": "ws-1",
        })
        if resp.status_code == 404:
            detail = resp.json().get("detail", "")
            assert "skill 'shared-workspace-info' not registered" not in detail.lower()
