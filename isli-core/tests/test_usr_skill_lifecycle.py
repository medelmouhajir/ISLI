"""Tests for the Workspace-to-USR skill lifecycle (test-skill, register-skill, update-skill)."""

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from isli_core.auth import create_internal_token
from isli_core.config import get_settings
from isli_core.main import app
from isli_core.models import SkillRegistry
from isli_core.services.skill_manager import SkillContainerManager, skill_manager

AGENT_ID = "usr-test-agent"
OTHER_AGENT_ID = "usr-other-agent"


class _FakeContainer:
    def __init__(self, name: str, cid: str = "abc123"):
        self.name = name
        self.id = cid
        self.short_id = cid[:6]
        self._running = True

    def stop(self, timeout: int = 10) -> None:
        self._running = False

    def remove(self, force: bool = False) -> None:
        pass

    def rename(self, new_name: str) -> None:
        self.name = new_name


class _FakeDockerImages:
    def build(self, path: str, tag: str, rm: bool, forcerm: bool, nocache: bool = False) -> tuple:
        return (None, [])


class _FakeDockerContainers:
    def run(self, image: str, name: str, network: str, detach: bool, **kwargs) -> _FakeContainer:
        return _FakeContainer(name)

    def list(self, all: bool = False, filters: dict | None = None) -> list[_FakeContainer]:
        return []


class _FakeDocker:
    images = _FakeDockerImages()
    containers = _FakeDockerContainers()


def _agent_token(agent_id: str = AGENT_ID) -> str:
    return create_internal_token(agent_id, scopes=["skill:proxy"], expires_minutes=5)


def _make_manifest(skill_id: str, version: str = "1.0.0") -> dict[str, Any]:
    return {
        "isli_version": "2.0",
        "id": skill_id,
        "name": skill_id.replace("-", " ").title(),
        "description": f"Test skill {skill_id}",
        "version": version,
        "author": AGENT_ID,
        "category": "custom",
        "runtime": {"port": 8500},
        "auth": {},
        "tools": [],
    }


def _write_skill_dir(
    base: Path,
    skill_id: str,
    version: str = "1.0.0",
    extra: dict[str, str] | None = None,
) -> Path:
    skill_dir = base / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    manifest = _make_manifest(skill_id, version)
    (skill_dir / "isli-skill.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    (skill_dir / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "COPY . /app\n"
        "WORKDIR /app\n"
        'CMD ["python", "-m", "http.server", "8500"]\n',
        encoding="utf-8",
    )
    (skill_dir / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/health')\n"
        "def health():\n"
        "    return {'status': 'ok'}\n",
        encoding="utf-8",
    )
    if extra:
        for name, content in extra.items():
            (skill_dir / name).write_text(content, encoding="utf-8")
    return skill_dir


def _enable_fake_docker(monkeypatch) -> None:
    """Force Docker mode with in-memory fakes so blue/green paths are exercised."""
    monkeypatch.setattr(skill_manager._container, "_use_docker", True)
    monkeypatch.setattr(skill_manager._container, "_docker", _FakeDocker())


@pytest.fixture
async def usr_env(tmp_path, monkeypatch):
    """Provide an isolated workspace + installed-skills directory and a fresh client."""
    settings = get_settings()
    workspaces = tmp_path / "workspaces"
    installed = tmp_path / "installed_skills"
    monkeypatch.setattr(settings, "workspace_base_path", str(workspaces))
    monkeypatch.setattr(settings, "installed_skills_path", str(installed))
    # Recreate the container manager so it picks up the patched installed_skills_path.
    skill_manager._container = SkillContainerManager()
    # Force native (non-Docker) mode for deterministic unit tests unless explicitly overridden.
    skill_manager._container._use_docker = False
    # Ensure the app has the process manager stub used by other endpoints.
    app.state.process_manager = type(
        "_PM", (), {
            "spawn": staticmethod(lambda *a, **k: None),
            "terminate": staticmethod(lambda *a, **k: None),
            "is_running": staticmethod(lambda *a: False),
        }
    )()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {_agent_token()}"},
    ) as client:
        yield client

    # Clean up DB rows created by these tests.
    from isli_core.db import async_session
    async with async_session() as db:
        result = await db.execute(select(SkillRegistry).where(SkillRegistry.id.like("usr-%")))
        for row in result.scalars().all():
            await db.delete(row)
        await db.commit()


@pytest.fixture
def agent_workspace(usr_env, tmp_path):
    """Return the agent's workspace root path."""
    return Path(get_settings().workspace_base_path) / "agents" / AGENT_ID


class TestUSRSkillLifecycle:
    @pytest.mark.asyncio
    async def test_test_skill_valid_manifest(self, usr_env: AsyncClient, agent_workspace: Path):
        skill_id = "usr-test-skill"
        _write_skill_dir(agent_workspace, skill_id)

        resp = await usr_env.post("/v1/skills/test-skill/test", json={
            "workspace_path": f"skills/{skill_id}",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["skill_id"] == skill_id
        assert data["manifest_valid"] is True

    @pytest.mark.asyncio
    async def test_test_skill_invalid_manifest(self, usr_env: AsyncClient, agent_workspace: Path):
        skill_dir = agent_workspace / "skills" / "usr-bad-manifest"
        skill_dir.mkdir(parents=True)
        (skill_dir / "isli-skill.yaml").write_text("not: valid: :: yaml", encoding="utf-8")

        resp = await usr_env.post("/v1/skills/test-skill/test", json={
            "workspace_path": "skills/usr-bad-manifest",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_register_skill_happy_path(self, usr_env: AsyncClient, agent_workspace: Path):
        skill_id = "usr-register-skill"
        _write_skill_dir(agent_workspace, skill_id)

        resp = await usr_env.post("/v1/skills/register-skill/register", json={
            "workspace_path": f"skills/{skill_id}",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["skill_id"] == skill_id

        installed_dir = Path(get_settings().installed_skills_path) / skill_id
        assert (installed_dir / "isli-skill.yaml").exists()
        assert (installed_dir / ".git").is_dir()

        from isli_core.db import async_session
        async with async_session() as db:
            result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
            skill = result.scalar_one()
            assert skill.status == "active"
            assert skill.owner_agent_id == AGENT_ID
            assert skill.installed_commit_sha is not None

    @pytest.mark.asyncio
    async def test_register_skill_path_traversal_rejected(
        self, usr_env: AsyncClient, agent_workspace: Path
    ):
        resp = await usr_env.post("/v1/skills/register-skill/register", json={
            "workspace_path": "../../etc/passwd",
        })
        assert resp.status_code == 400
        assert "traversal" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_register_skill_ownership_collision(
        self, usr_env: AsyncClient, agent_workspace: Path
    ):
        skill_id = "usr-collision-skill"
        _write_skill_dir(agent_workspace, skill_id)

        resp = await usr_env.post("/v1/skills/register-skill/register", json={
            "workspace_path": f"skills/{skill_id}",
        })
        assert resp.status_code == 200

        # Another agent tries to register the same skill_id.
        other_token = create_internal_token(
            OTHER_AGENT_ID, scopes=["skill:proxy"], expires_minutes=5
        )
        other_client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        # Need a workspace directory for the other agent to copy from.
        other_workspace = Path(get_settings().workspace_base_path) / "agents" / OTHER_AGENT_ID
        _write_skill_dir(other_workspace, skill_id)

        resp2 = await other_client.post("/v1/skills/register-skill/register", json={
            "workspace_path": f"skills/{skill_id}",
        })
        await other_client.aclose()
        assert resp2.status_code == 403
        assert "owned by" in resp2.text.lower()

    @pytest.mark.asyncio
    async def test_update_skill_clean_sync_removes_stale_files(
        self, usr_env: AsyncClient, agent_workspace: Path
    ):
        skill_id = "usr-update-sync-skill"
        _write_skill_dir(agent_workspace, skill_id, extra={"stale.txt": "old"})

        resp = await usr_env.post("/v1/skills/register-skill/register", json={
            "workspace_path": f"skills/{skill_id}",
        })
        assert resp.status_code == 200

        # Rewrite skill directory without stale.txt.
        skill_dir = agent_workspace / "skills" / skill_id
        (skill_dir / "stale.txt").unlink()
        (skill_dir / "isli-skill.yaml").write_text(
            yaml.safe_dump(_make_manifest(skill_id, version="2.0.0")),
            encoding="utf-8",
        )

        resp = await usr_env.post("/v1/skills/update-skill/update", json={
            "workspace_path": f"skills/{skill_id}",
        })
        if resp.status_code != 200:
            print("UPDATE RESPONSE:", resp.status_code, resp.text)
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "2.0.0"

        installed_dir = Path(get_settings().installed_skills_path) / skill_id
        assert not (installed_dir / "stale.txt").exists()

    @pytest.mark.asyncio
    async def test_register_skill_git_history_preserved_on_retry(
        self, usr_env: AsyncClient, agent_workspace: Path
    ):
        skill_id = "usr-git-history-skill"
        _write_skill_dir(agent_workspace, skill_id)

        resp = await usr_env.post("/v1/skills/register-skill/register", json={
            "workspace_path": f"skills/{skill_id}",
        })
        assert resp.status_code == 200

        installed_dir = Path(get_settings().installed_skills_path) / skill_id
        first_commit = subprocess.check_output(
            ["git", "-C", str(installed_dir), "rev-parse", "HEAD"],
            text=True,
        ).strip()

        # Update the workspace and register again (same skill_id, should reuse .git).
        skill_dir = agent_workspace / "skills" / skill_id
        (skill_dir / "isli-skill.yaml").write_text(
            yaml.safe_dump(_make_manifest(skill_id, version="2.0.0")),
            encoding="utf-8",
        )
        resp = await usr_env.post("/v1/skills/register-skill/register", json={
            "workspace_path": f"skills/{skill_id}",
        })
        assert resp.status_code == 200

        log = subprocess.check_output(
            ["git", "-C", str(installed_dir), "log", "--oneline"],
            text=True,
        ).strip()
        assert len(log.splitlines()) >= 2
        assert first_commit[:7] in log

    @pytest.mark.asyncio
    async def test_update_skill_probe_failure_keeps_old_active(
        self,
        usr_env: AsyncClient,
        agent_workspace: Path,
        monkeypatch,
    ):
        skill_id = "usr-update-rollback-skill"
        _write_skill_dir(agent_workspace, skill_id, version="1.0.0")

        resp = await usr_env.post("/v1/skills/register-skill/register", json={
            "workspace_path": f"skills/{skill_id}",
        })
        assert resp.status_code == 200

        # Update workspace to v2.
        skill_dir = agent_workspace / "skills" / skill_id
        (skill_dir / "isli-skill.yaml").write_text(
            yaml.safe_dump(_make_manifest(skill_id, version="2.0.0")),
            encoding="utf-8",
        )

        # Force Docker mode with fakes so the blue/green branch runs.
        _enable_fake_docker(monkeypatch)

        # Force the probe to fail so the update rolls back.
        async def _failing_probe(skill_id_param: str, base_url: str):
            return {"ok": False, "error": "injected probe failure"}

        monkeypatch.setattr(skill_manager._container, "_probe_swap", _failing_probe)

        resp = await usr_env.post("/v1/skills/update-skill/update", json={
            "workspace_path": f"skills/{skill_id}",
        })
        assert resp.status_code == 502

        from isli_core.db import async_session
        async with async_session() as db:
            result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
            skill = result.scalar_one()
            assert skill.status == "active"
            assert skill.version == "1.0.0"

        installed_dir = Path(get_settings().installed_skills_path) / skill_id
        current_commit = subprocess.check_output(
            ["git", "-C", str(installed_dir), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        # The git repo should still be at the original commit (v1.0.0).
        first_commit = subprocess.check_output(
            ["git", "-C", str(installed_dir), "rev-list", "--max-parents=0", "HEAD"],
            text=True,
        ).strip()
        assert current_commit == first_commit
