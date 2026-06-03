import pytest
import respx
from httpx import Response

from isli_agent import AgentConfig, AgentRunner
from isli_agent.tools.git import (
    git_clone,
    git_status,
    git_commit,
    git_push,
    git_pull,
    git_branch_list,
    git_branch_create,
    git_checkout,
    git_log,
    GitNotRepoError,
    GitAuthError,
    GitConflictError,
    GitRemoteError,
    GitInvalidOperationError,
)
from isli_agent.client import CoreClient


@pytest.fixture
def core_client():
    return CoreClient("http://localhost:8000", admin_key="test-admin-key")


class TestGitClone:
    @respx.mock
    async def test_success(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/git-clone/clone").mock(
            return_value=Response(200, json={"status": "ok", "path": "repo", "branch": "main"})
        )
        result = await git_clone("agent-1", "repo", "https://github.com/user/repo.git", core_client)
        assert result["path"] == "repo"
        assert route.called

    @respx.mock
    async def test_invalid_operation(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-clone/clone").mock(
            return_value=Response(400, json={"detail": "Target directory already exists"})
        )
        with pytest.raises(GitInvalidOperationError):
            await git_clone("agent-1", "repo", "https://github.com/user/repo.git", core_client)

    @respx.mock
    async def test_auth_error(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-clone/clone").mock(
            return_value=Response(403, json={"detail": "Authentication failed"})
        )
        with pytest.raises(GitAuthError):
            await git_clone("agent-1", "repo", "https://github.com/user/repo.git", core_client)

    @respx.mock
    async def test_remote_error(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-clone/clone").mock(
            return_value=Response(502, json={"detail": "Remote unreachable"})
        )
        with pytest.raises(GitRemoteError):
            await git_clone("agent-1", "repo", "https://github.com/user/repo.git", core_client)


class TestGitStatus:
    @respx.mock
    async def test_success(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/git-status/status").mock(
            return_value=Response(200, json={
                "status": "ok",
                "branch": "main",
                "modified": [],
                "staged": [],
                "untracked": [],
                "is_dirty": False,
            })
        )
        result = await git_status("agent-1", "repo", core_client)
        assert result["branch"] == "main"
        assert route.called

    @respx.mock
    async def test_not_a_repo(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-status/status").mock(
            return_value=Response(404, json={"detail": "Not a git repository"})
        )
        with pytest.raises(GitNotRepoError):
            await git_status("agent-1", "nope", core_client)


class TestGitCommit:
    @respx.mock
    async def test_success(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/git-commit/commit").mock(
            return_value=Response(200, json={
                "status": "committed",
                "commit_hash": "abc123",
                "message": "add feature",
            })
        )
        result = await git_commit("agent-1", "repo", "add feature", core_client)
        assert result["commit_hash"] == "abc123"
        body = route.calls.last.request.content.decode()
        assert '"message":"add feature"' in body

    @respx.mock
    async def test_with_files(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/git-commit/commit").mock(
            return_value=Response(200, json={"status": "committed", "commit_hash": "def456"})
        )
        await git_commit("agent-1", "repo", "fix bug", core_client, files=["src/main.py"])
        body = route.calls.last.request.content.decode()
        assert '"files":["src/main.py"]' in body

    @respx.mock
    async def test_not_a_repo(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-commit/commit").mock(
            return_value=Response(404, json={"detail": "Not a git repository"})
        )
        with pytest.raises(GitNotRepoError):
            await git_commit("agent-1", "nope", "msg", core_client)


class TestGitPush:
    @respx.mock
    async def test_success(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/git-push/push").mock(
            return_value=Response(200, json={"status": "pushed", "remote": "origin", "branch": "main"})
        )
        result = await git_push("agent-1", "repo", core_client)
        assert result["status"] == "pushed"
        body = route.calls.last.request.content.decode()
        assert '"remote":"origin"' in body

    @respx.mock
    async def test_auth_error(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-push/push").mock(
            return_value=Response(403, json={"detail": "Authentication failed"})
        )
        with pytest.raises(GitAuthError):
            await git_push("agent-1", "repo", core_client)

    @respx.mock
    async def test_remote_error(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-push/push").mock(
            return_value=Response(502, json={"detail": "Remote error"})
        )
        with pytest.raises(GitRemoteError):
            await git_push("agent-1", "repo", core_client)


class TestGitPull:
    @respx.mock
    async def test_success(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/git-pull/pull").mock(
            return_value=Response(200, json={"status": "pulled", "remote": "origin", "branch": "main"})
        )
        result = await git_pull("agent-1", "repo", core_client)
        assert result["status"] == "pulled"
        assert route.called

    @respx.mock
    async def test_conflict(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-pull/pull").mock(
            return_value=Response(409, json={"detail": "Merge conflict"})
        )
        with pytest.raises(GitConflictError):
            await git_pull("agent-1", "repo", core_client)

    @respx.mock
    async def test_not_a_repo(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-pull/pull").mock(
            return_value=Response(404, json={"detail": "Not a git repository"})
        )
        with pytest.raises(GitNotRepoError):
            await git_pull("agent-1", "nope", core_client)


class TestGitBranchList:
    @respx.mock
    async def test_success(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-branch-list/list").mock(
            return_value=Response(200, json={
                "branches": [
                    {"name": "main", "current": True},
                    {"name": "dev", "current": False},
                ],
                "current": "main",
            })
        )
        result = await git_branch_list("agent-1", "repo", core_client)
        assert len(result["branches"]) == 2
        assert result["current"] == "main"


class TestGitBranchCreate:
    @respx.mock
    async def test_success(self, core_client):
        route = respx.post("http://localhost:8000/v1/skills/git-branch-create/create").mock(
            return_value=Response(200, json={"status": "created", "branch": "feature-x", "checked_out": False})
        )
        result = await git_branch_create("agent-1", "repo", "feature-x", core_client)
        assert result["branch"] == "feature-x"
        body = route.calls.last.request.content.decode()
        assert '"checkout":false' in body


class TestGitCheckout:
    @respx.mock
    async def test_success(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-checkout/checkout").mock(
            return_value=Response(200, json={"status": "checked_out", "branch": "dev"})
        )
        result = await git_checkout("agent-1", "repo", "dev", core_client)
        assert result["branch"] == "dev"


class TestGitLog:
    @respx.mock
    async def test_success(self, core_client):
        respx.post("http://localhost:8000/v1/skills/git-log/log").mock(
            return_value=Response(200, json={
                "commits": [
                    {"hash": "abc123", "message": "first", "author": "A"},
                    {"hash": "def456", "message": "second", "author": "B"},
                ]
            })
        )
        result = await git_log("agent-1", "repo", core_client, max_count=5)
        assert len(result["commits"]) == 2


class TestAgentRunnerGitTools:
    def test_auto_register_from_skills(self):
        config = AgentConfig(
            id="test-agent",
            name="Test Agent",
            model_provider="ollama",
            model_id="qwen2.5:7b",
            skills=[
                "git-clone",
                "git-status",
                "git-commit",
                "git-push",
                "git-pull",
                "git-branch-list",
                "git-branch-create",
                "git-checkout",
                "git-log",
            ],
        )
        runner = AgentRunner(config, "http://localhost:8000")
        runner._auto_register_tools_from_skills()
        names = {d["function"]["name"] for d in runner.tool_definitions}
        expected = {
            "git_clone", "git_status", "git_commit", "git_push",
            "git_pull", "git_branch_list", "git_branch_create",
            "git_checkout", "git_log",
        }
        assert names == expected
