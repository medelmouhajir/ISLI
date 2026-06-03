import json
import os
import subprocess
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from isli_workspace.main import app
from isli_workspace.config import settings


class TestPipAPI:
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

    def _target_path(self, base: str, agent_id: str) -> str:
        return os.path.join(base, "agents", agent_id, ".pip-packages")

    def test_install_success(self, client: TestClient, temp_workspace: str):
        stdout = "Successfully installed requests-2.31.0 pandas-2.0.0\n"
        with patch(
            "isli_workspace.package_ops.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=stdout,
                stderr="",
            ),
        ):
            resp = client.post("/pip/install", json={
                "agent_id": "agent-a",
                "packages": ["requests", "pandas==2.0.0"],
            })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "installed"
        assert "requests" in data["packages"]
        assert "requests-2.31.0" in data["installed"]
        assert "pandas-2.0.0" in data["installed"]
        target = self._target_path(temp_workspace, "agent-a")
        assert data["target"] == target

    def test_install_with_upgrade(self, client: TestClient, temp_workspace: str):
        with patch(
            "isli_workspace.package_ops.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="Successfully installed requests-2.31.0\n",
                stderr="",
            ),
        ) as mock_run:
            resp = client.post("/pip/install", json={
                "agent_id": "agent-b",
                "packages": ["requests"],
                "upgrade": True,
            })
        assert resp.status_code == 200
        cmd = mock_run.call_args[0][0]
        assert "--upgrade" in cmd

    def test_install_blocks_forbidden_flag(self, client: TestClient):
        resp = client.post("/pip/install", json={
            "agent_id": "agent-c",
            "packages": ["requests", "--index-url", "https://evil.com"],
        })
        assert resp.status_code == 400
        assert "index-url" in resp.json()["detail"].lower()

    def test_install_blocks_requirement_flag(self, client: TestClient):
        resp = client.post("/pip/install", json={
            "agent_id": "agent-d",
            "packages": ["-r", "requirements.txt"],
        })
        assert resp.status_code == 400

    def test_install_blocks_file_url(self, client: TestClient):
        resp = client.post("/pip/install", json={
            "agent_id": "agent-e",
            "packages": ["file:///etc/passwd"],
        })
        assert resp.status_code == 400
        assert "file://" in resp.json()["detail"].lower()

    def test_install_blocks_empty_packages(self, client: TestClient):
        resp = client.post("/pip/install", json={
            "agent_id": "agent-f",
            "packages": [],
        })
        assert resp.status_code == 400

    def test_install_timeout(self, client: TestClient):
        with patch(
            "isli_workspace.package_ops.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pip", timeout=120),
        ):
            resp = client.post("/pip/install", json={
                "agent_id": "agent-g",
                "packages": ["pandas"],
            })
        assert resp.status_code == 408
        assert "timed out" in resp.json()["detail"].lower()

    def test_install_failure(self, client: TestClient):
        with patch(
            "isli_workspace.package_ops.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stdout="",
                stderr="Could not find a version that satisfies the requirement fake-pkg-xyz",
            ),
        ):
            resp = client.post("/pip/install", json={
                "agent_id": "agent-h",
                "packages": ["fake-pkg-xyz"],
            })
        assert resp.status_code == 500
        assert "fake-pkg-xyz" in resp.json()["detail"]

    def test_list_empty(self, client: TestClient, temp_workspace: str):
        resp = client.post("/pip/list", json={
            "agent_id": "agent-i",
        })
        assert resp.status_code == 200
        assert resp.json()["packages"] == []

    def test_list_with_packages(self, client: TestClient, temp_workspace: str):
        target = self._target_path(temp_workspace, "agent-j")
        os.makedirs(target, exist_ok=True)
        # Pretend a package is installed by creating the directory
        os.makedirs(os.path.join(target, "requests-2.31.0.dist-info"), exist_ok=True)

        stdout = json.dumps([
            {"name": "requests", "version": "2.31.0"},
            {"name": "pandas", "version": "2.0.0"},
        ])
        with patch(
            "isli_workspace.package_ops.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=stdout,
                stderr="",
            ),
        ):
            resp = client.post("/pip/list", json={
                "agent_id": "agent-j",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["packages"]) == 2
        assert data["packages"][0]["name"] == "requests"

    def test_sandbox_blocks_traversal(self, client: TestClient):
        resp = client.post("/pip/install", json={
            "agent_id": "agent-k",
            "scope": "agent",
            "scope_id": "../../../etc",
            "packages": ["requests"],
        })
        assert resp.status_code == 403
