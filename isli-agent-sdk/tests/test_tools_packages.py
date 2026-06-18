import pytest
import respx
from httpx import Response

from isli_agent import AgentConfig, AgentRunner
from isli_agent.tools.packages import (
    pip_install,
    pip_list,
    PackageInstallError,
    PackageInvalidError,
    PackageTimeoutError,
)
from isli_agent.client import CoreClient


@pytest.fixture
def core_client():
    return CoreClient("http://localhost:8000", admin_key="test-admin-key")


class TestPipInstall:
    @respx.mock
    async def test_success(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/pip-install/install").mock(
            return_value=Response(200, json={
                "status": "installed",
                "packages": ["requests"],
                "target": "/workspaces/agents/agent-1/.pip-packages",
                "installed": ["requests-2.31.0"],
                "warnings": [],
            })
        )
        result = await pip_install("agent-1", ["requests"], core_client)
        assert result["status"] == "installed"
        assert "requests-2.31.0" in result["installed"]
        assert route.called
        body = route.calls.last.request.content.decode()
        assert '"packages":["requests"]' in body

    @respx.mock
    async def test_upgrade(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/pip-install/install").mock(
            return_value=Response(200, json={"status": "installed", "packages": ["pandas"]})
        )
        await pip_install("agent-1", ["pandas"], core_client, upgrade=True)
        body = route.calls.last.request.content.decode()
        assert '"upgrade":true' in body

    @respx.mock
    async def test_invalid_packages(self, core_client):
        respx.post("http://localhost:8000/v1/skills/pip-install/install").mock(
            return_value=Response(400, json={"detail": "Forbidden pip flag '--index-url'"})
        )
        with pytest.raises(PackageInvalidError):
            await pip_install("agent-1", ["requests", "--index-url", "https://evil.com"], core_client)

    @respx.mock
    async def test_timeout(self, core_client):
        respx.post("http://localhost:8000/v1/skills/pip-install/install").mock(
            return_value=Response(408, json={"detail": "pip install timed out after 120s"})
        )
        with pytest.raises(PackageTimeoutError):
            await pip_install("agent-1", ["pandas"], core_client)

    @respx.mock
    async def test_install_failure(self, core_client):
        respx.post("http://localhost:8000/v1/skills/pip-install/install").mock(
            return_value=Response(500, json={"detail": "pip install failed: no such package"})
        )
        with pytest.raises(PackageInstallError):
            await pip_install("agent-1", ["fake-pkg-xyz"], core_client)


class TestPipList:
    @respx.mock
    async def test_success(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/pip-list/list").mock(
            return_value=Response(200, json={
                "status": "ok",
                "packages": [
                    {"name": "requests", "version": "2.31.0"},
                    {"name": "pandas", "version": "2.0.0"},
                ],
            })
        )
        result = await pip_list("agent-1", core_client)
        assert len(result["packages"]) == 2
        assert result["packages"][0]["name"] == "requests"
        assert route.called

    @respx.mock
    async def test_empty(self, core_client):
        respx.post("http://localhost:8000/v1/skills/pip-list/list").mock(
            return_value=Response(200, json={"status": "ok", "packages": []})
        )
        result = await pip_list("agent-1", core_client)
        assert result["packages"] == []


class TestAgentRunnerPipTools:
    async def test_auto_register_from_skills(self):
        config = AgentConfig(
            id="test-agent",
            name="Test Agent",
            model_provider="ollama",
            model_id="qwen2.5:7b",
            skills=[
                "pip-install",
                "pip-list",
            ],
        )
        runner = AgentRunner(config, "http://localhost:8000")
        await runner._auto_register_tools_from_skills()
        names = {d["function"]["name"] for d in runner.tool_definitions}
        assert "pip_install" in names
        assert "pip_list" in names
