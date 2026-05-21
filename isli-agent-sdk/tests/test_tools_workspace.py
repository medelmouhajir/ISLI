import pytest
import respx
from httpx import Response

from isli_agent import AgentConfig, AgentRunner
from isli_agent.tools.workspace import (
    file_read,
    file_write,
    file_list,
    file_delete,
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
        assert route.calls.last.request.content == b'{"agent_id":"agent-1","path":"notes.txt"}'

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
    def test_registers_four_tools(self):
        config = AgentConfig(
            id="test-agent",
            name="Test Agent",
            model_provider="ollama",
            model_id="qwen2.5:7b",
        )
        runner = AgentRunner(config, "http://localhost:8000")
        runner.add_workspace_tools()
        assert len(runner.tools) == 4
        assert len(runner.tool_definitions) == 4
        names = {d["function"]["name"] for d in runner.tool_definitions}
        assert names == {"file_read", "file_write", "file_list", "file_delete"}


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
