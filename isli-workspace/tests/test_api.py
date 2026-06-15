import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from isli_workspace.main import app
from isli_workspace.config import settings


class TestWorkspaceAPI:
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

    def test_write_and_read(self, client: TestClient):
        resp = client.post("/write", json={"agent_id": "agent-a", "path": "notes.txt", "content": "hello world"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "written"

        resp = client.post("/read", json={"agent_id": "agent-a", "path": "notes.txt"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "hello world"
        assert data["encoding"] == "utf-8"

    def test_list_files(self, client: TestClient):
        client.post("/write", json={"agent_id": "agent-b", "path": "a.txt", "content": "a"})
        client.post("/write", json={"agent_id": "agent-b", "path": "subdir/b.txt", "content": "b"})

        resp = client.post("/list", json={"agent_id": "agent-b", "path": ""})
        assert resp.status_code == 200
        data = resp.json()
        names = [e["name"] for e in data["entries"]]
        assert "a.txt" in names
        assert "subdir" in names

        resp = client.post("/list", json={"agent_id": "agent-b", "path": "subdir"})
        assert resp.status_code == 200
        data = resp.json()
        names = [e["name"] for e in data["entries"]]
        assert "b.txt" in names

    def test_delete_file(self, client: TestClient):
        client.post("/write", json={"agent_id": "agent-c", "path": "delete_me.txt", "content": "bye"})
        resp = client.post("/delete", json={"agent_id": "agent-c", "path": "delete_me.txt"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        resp = client.post("/read", json={"agent_id": "agent-c", "path": "delete_me.txt"})
        assert resp.status_code == 404

    def test_read_missing(self, client: TestClient):
        resp = client.post("/read", json={"agent_id": "agent-d", "path": "nope.txt"})
        assert resp.status_code == 404

    def test_delete_missing(self, client: TestClient):
        resp = client.post("/delete", json={"agent_id": "agent-e", "path": "nope.txt"})
        assert resp.status_code == 404

    def test_list_missing(self, client: TestClient):
        resp = client.post("/list", json={"agent_id": "agent-f", "path": "nope"})
        assert resp.status_code == 404

    def test_health(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_ready(self, client: TestClient):
        resp = client.get("/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"


class TestSharedWorkspaceAPI:
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

    def _write(self, client: TestClient, workspace_id: str, path: str, content: str):
        return client.post(
            "/write",
            json={
                "agent_id": "agent-a",
                "scope": "shared",
                "scope_id": workspace_id,
                "path": path,
                "content": content,
            },
        )

    def test_shared_move_within_workspace(self, client: TestClient):
        ws = "ws-1"
        self._write(client, ws, "old_name.txt", "content")
        resp = client.post(
            "/shared/move",
            json={
                "agent_id": "agent-a",
                "source_workspace_id": ws,
                "source_path": "old_name.txt",
                "target_path": "new_name.txt",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "moved"
        assert data["target_path"] == "new_name.txt"

        # Source gone, target exists
        assert client.post("/read", json={"agent_id": "agent-a", "scope": "shared", "scope_id": ws, "path": "old_name.txt"}).status_code == 404
        read_resp = client.post("/read", json={"agent_id": "agent-a", "scope": "shared", "scope_id": ws, "path": "new_name.txt"})
        assert read_resp.status_code == 200
        assert read_resp.json()["content"] == "content"

    def test_shared_move_between_workspaces(self, client: TestClient):
        src = "ws-src"
        dst = "ws-dst"
        self._write(client, src, "file.txt", "moved across")
        resp = client.post(
            "/shared/move",
            json={
                "agent_id": "agent-a",
                "source_workspace_id": src,
                "source_path": "file.txt",
                "target_workspace_id": dst,
                "target_path": "incoming/file.txt",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["target_workspace_id"] == dst
        read_resp = client.post(
            "/read",
            json={"agent_id": "agent-a", "scope": "shared", "scope_id": dst, "path": "incoming/file.txt"},
        )
        assert read_resp.status_code == 200
        assert read_resp.json()["content"] == "moved across"

    def test_shared_move_same_path_error(self, client: TestClient):
        ws = "ws-same"
        self._write(client, ws, "x.txt", "x")
        resp = client.post(
            "/shared/move",
            json={
                "agent_id": "agent-a",
                "source_workspace_id": ws,
                "source_path": "x.txt",
                "target_path": "x.txt",
            },
        )
        assert resp.status_code == 400

    def test_shared_search_by_name(self, client: TestClient):
        ws = "ws-search"
        self._write(client, ws, "alpha.txt", "abc")
        self._write(client, ws, "beta.txt", "def")
        resp = client.post(
            "/shared/search",
            json={"agent_id": "agent-a", "workspace_id": ws, "query": "alpha", "search_names": True, "search_content": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        names = [m["name"] for m in data["matches"]]
        assert "alpha.txt" in names
        assert "beta.txt" not in names

    def test_shared_search_by_content(self, client: TestClient):
        ws = "ws-search-content"
        self._write(client, ws, "one.txt", "the quick brown fox")
        self._write(client, ws, "two.txt", "lazy dog")
        resp = client.post(
            "/shared/search",
            json={"agent_id": "agent-a", "workspace_id": ws, "query": "brown", "search_names": False, "search_content": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        names = [m["name"] for m in data["matches"]]
        assert "one.txt" in names
        assert "two.txt" not in names
        assert any("brown" in (m.get("snippet") or "") for m in data["matches"])

    def test_shared_search_respects_max_results(self, client: TestClient):
        ws = "ws-limit"
        for i in range(5):
            self._write(client, ws, f"file{i}.txt", str(i))
        resp = client.post(
            "/shared/search",
            json={"agent_id": "agent-a", "workspace_id": ws, "query": "file", "search_names": True, "max_results": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["matches"]) == 2
        assert data["truncated"] is True
