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
