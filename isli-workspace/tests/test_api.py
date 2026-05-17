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
        return TestClient(app)

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
