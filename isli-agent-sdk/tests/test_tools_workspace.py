import pytest
import respx
from httpx import Response

from isli_agent import AgentConfig, AgentRunner
from isli_agent.tools.workspace import (
    file_read,
    file_write,
    file_list,
    file_delete,
    shared_file_read,
    shared_file_write,
    shared_file_list,
    shared_file_delete,
    shared_file_move,
    shared_workspace_info,
    shared_workspace_search,
    shared_promote_file_workspace,
    WorkspaceNotFoundError,
    WorkspacePathError,
    WorkspaceQuotaError,
    WorkspacePermissionError,
)
from isli_agent.client import CoreClient


@pytest.fixture
def core_client():
    return CoreClient("http://localhost:8000", admin_key="test-admin-key")


class TestFileRead:
    @respx.mock
    async def test_returns_parsed_json(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/file-read/read").mock(
            return_value=Response(200, json={"content": "hello", "size_bytes": 5, "encoding": "utf-8"})
        )
        result = await file_read("agent-1", "notes.txt", core_client)
        assert result["content"] == "hello"
        assert result["size_bytes"] == 5
        assert route.called
        body = route.calls.last.request.content.decode()
        assert '"agent_id":"agent-1"' in body
        assert '"path":"notes.txt"' in body

    @respx.mock
    async def test_raises_not_found_on_404(self, core_client):
        respx.post("http://localhost:8000/v1/skills/file-read/read").mock(
            return_value=Response(404, json={"detail": "File not found"})
        )
        with pytest.raises(WorkspaceNotFoundError):
            await file_read("agent-1", "missing.txt", core_client)

    @respx.mock
    async def test_raises_path_error_on_403(self, core_client):
        respx.post("http://localhost:8000/v1/skills/file-read/read").mock(
            return_value=Response(403, json={"detail": "Path traversal blocked"})
        )
        with pytest.raises(WorkspacePathError):
            await file_read("agent-1", "../../../etc/passwd", core_client)


class TestFileWrite:
    @respx.mock
    async def test_sends_correct_payload(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/file-write/write").mock(
            return_value=Response(200, json={"status": "written", "size_bytes": 11})
        )
        result = await file_write("agent-1", "notes.txt", "hello world", core_client)
        assert result["status"] == "written"
        assert route.called
        body = route.calls.last.request.content.decode()
        assert '"path":"notes.txt"' in body
        assert '"content":"hello world"' in body

    @respx.mock
    async def test_raises_quota_error_on_413(self, core_client):
        respx.post("http://localhost:8000/v1/skills/file-write/write").mock(
            return_value=Response(413, json={"detail": "Quota exceeded"})
        )
        with pytest.raises(WorkspaceQuotaError):
            await file_write("agent-1", "huge.bin", "x" * 20_000_000, core_client)


class TestFileList:
    @respx.mock
    async def test_returns_entries(self, core_client):
        respx.post("http://localhost:8000/v1/skills/file-list/list").mock(
            return_value=Response(200, json={
                "entries": [
                    {"name": "notes.txt", "type": "file", "size_bytes": 5},
                    {"name": "data", "type": "directory", "size_bytes": 0},
                ]
            })
        )
        result = await file_list("agent-1", "", core_client)
        assert len(result["entries"]) == 2
        assert result["entries"][0]["name"] == "notes.txt"

    @respx.mock
    async def test_handles_empty_directory(self, core_client):
        respx.post("http://localhost:8000/v1/skills/file-list/list").mock(
            return_value=Response(200, json={"entries": []})
        )
        result = await file_list("agent-1", "empty_dir", core_client)
        assert result["entries"] == []


class TestFileDelete:
    @respx.mock
    async def test_returns_deleted_path(self, core_client):
        respx.post("http://localhost:8000/v1/skills/file-delete/delete").mock(
            return_value=Response(200, json={"status": "deleted", "path": "notes.txt", "size_bytes": 5})
        )
        result = await file_delete("agent-1", "notes.txt", core_client)
        assert result["status"] == "deleted"
        assert result["path"] == "notes.txt"

    @respx.mock
    async def test_raises_not_found_on_404(self, core_client):
        respx.post("http://localhost:8000/v1/skills/file-delete/delete").mock(
            return_value=Response(404, json={"detail": "File not found"})
        )
        with pytest.raises(WorkspaceNotFoundError):
            await file_delete("agent-1", "missing.txt", core_client)

    @respx.mock
    async def test_raises_permission_error_on_directory_delete(self, core_client):
        respx.post("http://localhost:8000/v1/skills/file-delete/delete").mock(
            return_value=Response(403, json={"detail": "Cannot delete directory"})
        )
        with pytest.raises(WorkspacePermissionError):
            await file_delete("agent-1", "data_dir", core_client)

    @respx.mock
    async def test_raises_path_error_on_403(self, core_client):
        respx.post("http://localhost:8000/v1/skills/file-delete/delete").mock(
            return_value=Response(403, json={"detail": "Path traversal blocked"})
        )
        with pytest.raises(WorkspacePathError):
            await file_delete("agent-1", "../../../etc/passwd", core_client)


class TestAgentRunnerWorkspaceTools:
    def test_registers_workspace_tools(self):
        config = AgentConfig(
            id="test-agent",
            name="Test Agent",
            model_provider="ollama",
            model_id="qwen2.5:7b",
        )
        runner = AgentRunner(config, "http://localhost:8000")
        runner.add_workspace_tools()
        assert len(runner.tools) == 7
        assert len(runner.tool_definitions) == 7
        names = {d["function"]["name"] for d in runner.tool_definitions}
        assert names == {
            "file_read", "file_write", "file_list", "file_delete",
            "describe_workspace_file", "search_workspace_file", "read_workspace_file",
        }

    async def test_auto_register_file_search_and_describe(self):
        """file-search and file-describe from Core must resolve to the SDK workspace tools."""
        config = AgentConfig(
            id="test-agent",
            name="Test Agent",
            model_provider="ollama",
            model_id="qwen2.5:7b",
            skills=["file-search", "file-describe"],
        )
        runner = AgentRunner(config, "http://localhost:8000")
        await runner._auto_register_tools_from_skills()
        names = {d["function"]["name"] for d in runner.tool_definitions}
        assert "search_workspace_file" in names
        assert "describe_workspace_file" in names
        skill_tags = {d.get("x_isli_skill") for d in runner.tool_definitions}
        assert "file-search" in skill_tags
        assert "file-describe" in skill_tags


class TestAgentRunnerChannelTools:
    def test_registers_send_message_tool(self):
        config = AgentConfig(
            id="test-agent",
            name="Test Agent",
            model_provider="ollama",
            model_id="qwen2.5:7b",
        )
        runner = AgentRunner(config, "http://localhost:8000")
        runner.add_channel_tools()
        assert len(runner.tools) == 1
        assert len(runner.tool_definitions) == 1
        assert runner.tool_definitions[0]["function"]["name"] == "send_message"


class TestSharedWorkspaceTools:
    @respx.mock
    async def test_shared_file_read(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/shared-file-read/read").mock(
            return_value=Response(200, json={"content": "shared", "size_bytes": 6, "encoding": "utf-8"})
        )
        result = await shared_file_read("agent-1", "ws-1", "notes.txt", core_client)
        assert result["content"] == "shared"
        assert route.called
        body = route.calls.last.request.content.decode()
        assert '"scope":"shared"' in body
        assert '"scope_id":"ws-1"' in body

    @respx.mock
    async def test_shared_file_write(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/shared-file-write/write").mock(
            return_value=Response(200, json={"status": "written", "size_bytes": 5})
        )
        result = await shared_file_write("agent-1", "ws-1", "notes.txt", "hello", core_client)
        assert result["status"] == "written"
        body = route.calls.last.request.content.decode()
        assert '"scope":"shared"' in body

    @respx.mock
    async def test_shared_file_list(self, core_client):
        respx.post("http://localhost:8000/v1/skills/shared-file-list/list").mock(
            return_value=Response(200, json={"entries": [{"name": "a.txt", "type": "file"}]})
        )
        result = await shared_file_list("agent-1", "ws-1", "", core_client)
        assert result["entries"][0]["name"] == "a.txt"

    @respx.mock
    async def test_shared_file_delete(self, core_client):
        respx.post("http://localhost:8000/v1/skills/shared-file-delete/delete").mock(
            return_value=Response(200, json={"status": "deleted", "path": "notes.txt"})
        )
        result = await shared_file_delete("agent-1", "ws-1", "notes.txt", core_client)
        assert result["status"] == "deleted"

    @respx.mock
    async def test_shared_file_delete_raises_on_directory(self, core_client):
        respx.post("http://localhost:8000/v1/skills/shared-file-delete/delete").mock(
            return_value=Response(403, json={"detail": "Cannot delete directory"})
        )
        with pytest.raises(WorkspacePermissionError):
            await shared_file_delete("agent-1", "ws-1", "data", core_client)

    @respx.mock
    async def test_shared_file_move(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/shared-file-move/move").mock(
            return_value=Response(200, json={"status": "moved", "target_path": "b.txt", "target_workspace_id": "ws-1"})
        )
        result = await shared_file_move("agent-1", "ws-1", "a.txt", "b.txt", core_client)
        assert result["status"] == "moved"
        body = route.calls.last.request.content.decode()
        assert '"source_workspace_id":"ws-1"' in body

    @respx.mock
    async def test_shared_workspace_info(self, core_client):
        respx.post("http://localhost:8000/v1/skills/shared-workspace-info/info").mock(
            return_value=Response(200, json={"workspace_id": "ws-1", "name": "Project X", "members": ["agent-1"]})
        )
        result = await shared_workspace_info("agent-1", "ws-1", core_client)
        assert result["name"] == "Project X"

    @respx.mock
    async def test_shared_workspace_search(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/shared-workspace-search/search").mock(
            return_value=Response(200, json={"matches": [{"name": "foo.txt"}], "total": 1, "truncated": False})
        )
        result = await shared_workspace_search("agent-1", "ws-1", "foo", core_client, search_names=True, search_content=True)
        assert result["total"] == 1
        body = route.calls.last.request.content.decode()
        assert '"search_content":true' in body

    @respx.mock
    async def test_shared_promote_file_workspace(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/shared-promote-file-workspace/promote").mock(
            return_value=Response(200, json={"status": "ok", "workspace_id": "ws-1", "target_path": "shared.txt"})
        )
        result = await shared_promote_file_workspace("agent-1", "ws-1", "local.txt", "shared.txt", core_client)
        assert result["status"] == "ok"
        body = route.calls.last.request.content.decode()
        assert '"source_path":"local.txt"' in body


class TestAgentRunnerSharedWorkspaceTools:
    def test_registers_shared_workspace_tools(self):
        config = AgentConfig(
            id="test-agent",
            name="Test Agent",
            model_provider="ollama",
            model_id="qwen2.5:7b",
        )
        runner = AgentRunner(config, "http://localhost:8000")
        runner.add_shared_workspace_tools()
        assert len(runner.tools) == 8
        names = {d["function"]["name"] for d in runner.tool_definitions}
        expected = {
            "shared_file_read", "shared_file_write", "shared_file_list", "shared_file_delete",
            "shared_file_move", "shared_workspace_info", "shared_workspace_search",
            "shared_promote_file_workspace",
        }
        assert names == expected
