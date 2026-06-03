import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from git import Repo

from isli_workspace.main import app
from isli_workspace.config import settings


class TestGitAPI:
    @pytest.fixture(autouse=True)
    def temp_workspace(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setattr(settings, "workspace_base_path", tmp)
            yield tmp

    @pytest.fixture
    def client(self):
        client = TestClient(app)
        client.headers.update({"X-Internal-Auth": "test-token"})
        return client

    def _make_repo(self, base: str, agent_id: str, path: str = "repo") -> Repo:
        repo_path = os.path.join(base, "agents", agent_id, path)
        os.makedirs(repo_path, exist_ok=True)
        repo = Repo.init(repo_path)
        # Create an initial commit so HEAD exists
        with open(os.path.join(repo_path, "README.md"), "w") as f:
            f.write("# init\n")
        repo.index.add(["README.md"])
        repo.index.commit("init")
        return repo

    def test_clone_success(self, client: TestClient, temp_workspace: str):
        # Create a bare repo to clone from
        bare_path = os.path.join(temp_workspace, "bare_repo.git")
        bare = Repo.init(bare_path, bare=True)
        # Seed the bare repo via a temp clone
        tmp_clone = os.path.join(temp_workspace, "tmp_clone")
        tmp = Repo.clone_from(bare_path, tmp_clone)
        with open(os.path.join(tmp_clone, "file.txt"), "w") as f:
            f.write("hello\n")
        tmp.index.add(["file.txt"])
        tmp.index.commit("first")
        tmp.remote("origin").push("master")
        tmp.close()
        bare.close()

        resp = client.post("/git/clone", json={
            "agent_id": "agent-a",
            "path": "cloned",
            "url": bare_path,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "cloned"
        assert data["path"] == "cloned"

    def test_clone_blocks_file_scheme(self, client: TestClient):
        resp = client.post("/git/clone", json={
            "agent_id": "agent-b",
            "path": "cloned",
            "url": "file:///etc/passwd",
        })
        assert resp.status_code == 400
        assert "file" in resp.json()["detail"].lower()

    def test_clone_blocks_local_path(self, client: TestClient):
        resp = client.post("/git/clone", json={
            "agent_id": "agent-c",
            "path": "cloned",
            "url": "/etc/passwd",
        })
        assert resp.status_code == 400

    def test_clone_into_existing_nonempty_dir(self, client: TestClient, temp_workspace: str):
        existing = os.path.join(temp_workspace, "agents", "agent-d", "existing")
        os.makedirs(existing, exist_ok=True)
        with open(os.path.join(existing, "file.txt"), "w") as f:
            f.write("x")
        resp = client.post("/git/clone", json={
            "agent_id": "agent-d",
            "path": "existing",
            "url": "https://github.com/octocat/Hello-World.git",
        })
        assert resp.status_code == 400

    def test_status(self, client: TestClient, temp_workspace: str):
        self._make_repo(temp_workspace, "agent-e", "repo")
        resp = client.post("/git/status", json={
            "agent_id": "agent-e",
            "path": "repo",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_dirty"] is False
        assert data["branch"] == "master"

    def test_status_not_a_repo(self, client: TestClient, temp_workspace: str):
        os.makedirs(os.path.join(temp_workspace, "agents", "agent-f", "nope"), exist_ok=True)
        resp = client.post("/git/status", json={
            "agent_id": "agent-f",
            "path": "nope",
        })
        assert resp.status_code == 404

    def test_commit(self, client: TestClient, temp_workspace: str):
        repo = self._make_repo(temp_workspace, "agent-g", "repo")
        with open(os.path.join(repo.working_dir, "new.txt"), "w") as f:
            f.write("new content\n")
        repo.close()

        resp = client.post("/git/commit", json={
            "agent_id": "agent-g",
            "path": "repo",
            "message": "add new file",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "committed"
        assert "commit_hash" in data

    def test_commit_no_changes(self, client: TestClient, temp_workspace: str):
        self._make_repo(temp_workspace, "agent-h", "repo")
        resp = client.post("/git/commit", json={
            "agent_id": "agent-h",
            "path": "repo",
            "message": "nothing",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_changes"

    def test_push_and_pull(self, client: TestClient, temp_workspace: str):
        # Set up a bare remote
        bare_path = os.path.join(temp_workspace, "remote.git")
        bare = Repo.init(bare_path, bare=True)

        # Create local repo cloned from bare
        local_path = os.path.join(temp_workspace, "agents", "agent-i", "repo")
        os.makedirs(local_path, exist_ok=True)
        local = Repo.clone_from(bare_path, local_path)
        with open(os.path.join(local.working_dir, "a.txt"), "w") as f:
            f.write("a\n")
        local.index.add(["a.txt"])
        local.index.commit("add a")
        local.close()
        bare.close()

        resp = client.post("/git/push", json={
            "agent_id": "agent-i",
            "path": "repo",
            "remote": "origin",
            "branch": "master",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "pushed"

        # Second clone to pull into
        local2_path = os.path.join(temp_workspace, "agents", "agent-j", "repo2")
        os.makedirs(os.path.dirname(local2_path), exist_ok=True)
        local2 = Repo.clone_from(bare_path, local2_path)
        local2.close()

        resp = client.post("/git/pull", json={
            "agent_id": "agent-j",
            "path": "repo2",
            "remote": "origin",
            "branch": "master",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "pulled"

    def test_branch_list(self, client: TestClient, temp_workspace: str):
        repo = self._make_repo(temp_workspace, "agent-k", "repo")
        repo.create_head("feature")
        repo.close()

        resp = client.post("/git/branch/list", json={
            "agent_id": "agent-k",
            "path": "repo",
        })
        assert resp.status_code == 200
        data = resp.json()
        names = {b["name"] for b in data["branches"]}
        assert "master" in names
        assert "feature" in names

    def test_branch_create(self, client: TestClient, temp_workspace: str):
        repo = self._make_repo(temp_workspace, "agent-l", "repo")
        repo.close()

        resp = client.post("/git/branch/create", json={
            "agent_id": "agent-l",
            "path": "repo",
            "branch_name": "feature-x",
            "checkout": False,
        })
        assert resp.status_code == 200
        assert resp.json()["branch"] == "feature-x"

    def test_checkout(self, client: TestClient, temp_workspace: str):
        repo = self._make_repo(temp_workspace, "agent-m", "repo")
        repo.create_head("develop")
        repo.close()

        resp = client.post("/git/checkout", json={
            "agent_id": "agent-m",
            "path": "repo",
            "branch_name": "develop",
        })
        assert resp.status_code == 200
        assert resp.json()["branch"] == "develop"

    def test_log(self, client: TestClient, temp_workspace: str):
        repo = self._make_repo(temp_workspace, "agent-n", "repo")
        with open(os.path.join(repo.working_dir, "b.txt"), "w") as f:
            f.write("b\n")
        repo.index.add(["b.txt"])
        repo.index.commit("second")
        repo.close()

        resp = client.post("/git/log", json={
            "agent_id": "agent-n",
            "path": "repo",
            "max_count": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["commits"]) == 2
        assert data["commits"][0]["message"] == "second"

    def test_sandbox_blocks_traversal(self, client: TestClient, temp_workspace: str):
        resp = client.post("/git/status", json={
            "agent_id": "agent-o",
            "path": "../../../etc",
        })
        assert resp.status_code == 403
