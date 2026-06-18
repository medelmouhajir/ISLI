import asyncio
import json
import os
import re
import shutil
import subprocess
import time as _time
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
import structlog
import yaml
from packaging.version import Version as SemVer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from isli_core.config import get_settings
from isli_core.db import get_db_session_manual
from isli_core.event_manager import EventManager
from isli_core.models import SkillRegistry, SkillRun
from isli_core.redis_client import get_redis
from isli_core.auth import create_internal_token

logger = structlog.get_logger()


# ── Manifest Schema ─────────────────────────────────────────────────────────

class SkillToolManifest(BaseModel):
    name: str
    description: str
    endpoint: str
    method: str = "POST"
    parameters: dict[str, Any] = Field(default_factory=dict)
    returns: dict[str, Any] = Field(default_factory=dict)
    secret_fields: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not v.replace("_", "").isalnum() or v[0].isdigit():
            raise ValueError("Tool name must be snake_case alphanumeric and not start with a digit")
        return v


class SkillManifest(BaseModel):
    isli_version: str = "2.0"
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "unknown"
    category: str = "custom"
    runtime: dict[str, Any] = Field(default_factory=dict)
    auth: dict[str, Any] = Field(default_factory=dict)
    tools: list[SkillToolManifest] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not v.replace("-", "").isalnum():
            raise ValueError("Skill id must be kebab-case alphanumeric")
        return v

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: str) -> str:
        allowed = {
            "web", "content", "workspace", "communication",
            "memory", "kanban", "engineering", "audio",
            "database", "git", "system", "custom",
        }
        if v not in allowed:
            raise ValueError(f"Category must be one of {allowed}")
        return v


# ── Legacy DynamicSkillManager (file-system based exec skills) ────────────────

class DynamicSkillManager:
    def __init__(self):
        settings = get_settings()
        self.base_path = settings.installed_skills_path
        self._skills: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, Any] = {}

        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path, exist_ok=True)

        self.refresh_registry()

    def refresh_registry(self):
        new_skills = {}
        if not os.path.exists(self.base_path):
            return

        for skill_id in os.listdir(self.base_path):
            skill_dir = os.path.join(self.base_path, skill_id)
            if not os.path.isdir(skill_dir):
                continue

            manifest_path = os.path.join(skill_dir, "skill.json")
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r") as f:
                        meta = json.load(f)
                        new_skills[skill_id] = meta
                except Exception as e:
                    logger.error("skill_manager.load_manifest_failed", skill_id=skill_id, error=str(e))
            else:
                new_skills[skill_id] = {
                    "name": skill_id,
                    "description": "Installed via Skills Store",
                    "type": "dynamic",
                    "category": "custom",
                }

        self._skills = new_skills
        logger.info("skill_manager.registry_refreshed", count=len(self._skills))

    def get_skill_metadata(self) -> dict[str, dict[str, Any]]:
        return self._skills

    def get_handler(self, skill_id: str):
        if skill_id in self._handlers:
            return self._handlers[skill_id]

        skill_dir = os.path.join(self.base_path, skill_id)
        main_py = os.path.join(skill_dir, "main.py")

        if not os.path.exists(main_py):
            return None

        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"dynamic_skill_{skill_id}", main_py)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._handlers[skill_id] = module
            return module
        except Exception as e:
            logger.error("skill_manager.load_handler_failed", skill_id=skill_id, error=str(e))
            return None


# ── SkillContainerManager (DB-backed external skill lifecycle) ──────────────

class SkillContainerManager:
    """Manages external skills backed by DB registry + Docker containers."""

    def __init__(self):
        settings = get_settings()
        self.base_path = settings.installed_skills_path
        self._docker: Any = None
        self._use_docker = os.path.exists("/var/run/docker.sock")
        if self._use_docker:
            try:
                import docker as docker_lib
                self._docker = docker_lib.from_env()
                logger.info("scm.docker_mode_enabled")
            except Exception as exc:
                logger.warning("scm.docker_unavailable", error=str(exc))
                self._use_docker = False
        self._git_locks: dict[str, asyncio.Lock] = {}

    # ── Git Operations (threaded, never block event loop) ──────────────────

    def _git_lock(self, skill_id: str) -> asyncio.Lock:
        if skill_id not in self._git_locks:
            self._git_locks[skill_id] = asyncio.Lock()
        return self._git_locks[skill_id]

    @staticmethod
    async def _git_cmd(skill_id: str, *args: str, cwd: str | None = None, timeout: float = 30.0) -> str:
        """Run a git command in a thread with timeout. Never blocks the event loop."""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"git command timed out after {timeout}s for skill {skill_id}")
        if proc.returncode != 0:
            raise RuntimeError(f"git failed for skill {skill_id}: {stderr.decode().strip()}")
        return stdout.decode().strip()

    @staticmethod
    async def _acquire_skill_lock(skill_id: str, ttl: int = 120) -> bool:
        """Acquire a Redis distributed lock for mutating operations on a skill."""
        redis = await get_redis()
        acquired = await redis.set(f"skill:update:{skill_id}", "1", nx=True, ex=ttl)
        return acquired is not None

    @staticmethod
    async def _release_skill_lock(skill_id: str) -> None:
        redis = await get_redis()
        await redis.delete(f"skill:update:{skill_id}")

    # ── Blue/Green Probe ───────────────────────────────────────────────────

    @staticmethod
    async def _probe_swap(skill_id: str, base_url: str, max_attempts: int = 12, interval: float = 2.5) -> dict[str, Any]:
        """Probe a container before declaring the swap safe.
        Total max time: 12 * 2.5 = 30 seconds.
        """
        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{base_url}/health")
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("skill_id", skill_id) != skill_id:
                        logger.warning("probe_swap.id_mismatch", skill_id=skill_id, attempt=attempt)
                        await asyncio.sleep(interval)
                        continue
                    return {"ok": True, "data": data}
            except Exception as exc:
                logger.info("probe_swap.retry", skill_id=skill_id, attempt=attempt, error=str(exc))
                await asyncio.sleep(interval)
        return {"ok": False, "error": f"Probe failed after {max_attempts} attempts"}

    # ── Changelog Parser ─────────────────────────────────────────────────────

    @staticmethod
    def _parse_changelog(skill_dir: str) -> list[dict[str, str]]:
        """Parse CHANGELOG.md for simple ## [version] - date headers."""
        for fname in ("CHANGELOG.md", "changelog.md"):
            path = os.path.join(skill_dir, fname)
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()
                    entries = []
                    for match in re.finditer(r"^##\s*\[(.+?)\]\s*-\s*(.+?)$", text, re.MULTILINE):
                        version = match.group(1).strip()
                        date = match.group(2).strip()
                        # Capture following paragraph as message
                        start = match.end()
                        end_match = re.search(r"^##\s*\[", text[start:], re.MULTILINE)
                        snippet = text[start:start + (end_match.start() if end_match else 400)]
                        message = " ".join(snippet.strip().splitlines()[:3])
                        entries.append({"version": version, "date": date, "message": message})
                    return entries[:20]
                except Exception:
                    pass
        return []

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _manifest_path(skill_dir: str) -> str:
        candidates = ["isli-skill.yaml", "skill.yaml", "manifest.yaml"]
        for c in candidates:
            p = os.path.join(skill_dir, c)
            if os.path.exists(p):
                return p
        return os.path.join(skill_dir, "isli-skill.yaml")

    @staticmethod
    def _load_manifest(skill_dir: str) -> SkillManifest:
        path = SkillContainerManager._manifest_path(skill_dir)
        with open(path, "r") as f:
            raw = yaml.safe_load(f)
        return SkillManifest.model_validate(raw)

    @staticmethod
    def _skill_dir(skill_id: str) -> str:
        settings = get_settings()
        return os.path.join(settings.installed_skills_path, skill_id)

    # ── DB helpers ─────────────────────────────────────────────────────────

    async def _get_skill(self, skill_id: str) -> SkillRegistry | None:
        async with get_db_session_manual() as db:
            result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
            return result.scalar_one_or_none()

    async def _get_active_skills(self) -> list[SkillRegistry]:
        async with get_db_session_manual() as db:
            result = await db.execute(
                select(SkillRegistry).where(SkillRegistry.status.in_(["active", "running"]))
            )
            return list(result.scalars().all())

    async def _get_all_skills(self) -> list[SkillRegistry]:
        async with get_db_session_manual() as db:
            result = await db.execute(select(SkillRegistry))
            return list(result.scalars().all())

    # ── Registry Builders (used by proxy router) ───────────────────────────

    async def get_registry(self) -> dict[str, str]:
        """Return {skill_id: base_url} for all active external skills."""
        skills = await self._get_active_skills()
        return {s.id: s.base_url for s in skills}

    async def get_metadata(self) -> dict[str, dict[str, Any]]:
        """Return {skill_id: meta} for all registered skills (active or not)."""
        skills = await self._get_all_skills()
        out: dict[str, dict[str, Any]] = {}
        for s in skills:
            out[s.id] = {
                "name": s.name,
                "description": s.description or "",
                "type": "external",
                "category": s.category,
                "version": s.version,
                "author": s.author,
                "status": s.status,
                "last_probe_status": s.last_probe_status,
                "last_probe_result": s.last_probe_result,
                "last_probe_at": s.last_probe_at.isoformat() if s.last_probe_at else None,
                "tools": s.manifest.get("tools", []) if s.manifest else [],
                "source_url": s.source_url,
                "source_ref": s.source_ref,
                "installed_commit_sha": s.installed_commit_sha,
                "latest_commit_sha": s.latest_commit_sha,
                "latest_version": s.latest_version,
                "update_policy": s.update_policy,
                "previous_version": s.previous_version,
                "previous_commit_sha": s.previous_commit_sha,
                "previous_image_tag": s.previous_image_tag,
                "changelog": s.changelog or [],
                "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
            }
        return out

    async def get_skill_manifest(self, skill_id: str) -> dict[str, Any] | None:
        skill = await self._get_skill(skill_id)
        if not skill:
            return None
        return skill.manifest or {}

    # ── Install ────────────────────────────────────────────────────────────

    async def install_from_git(self, skill_id: str, git_url: str, installed_by: str | None = None) -> SkillRegistry:
        """Clone repo, validate manifest, insert into DB. Does NOT start container."""
        skill_dir = self._skill_dir(skill_id)

        # 1. Clean up old dir
        if os.path.exists(skill_dir):
            shutil.rmtree(skill_dir, ignore_errors=True)

        # 2. Clone (threaded with timeout)
        logger.info("scm.install_cloning", skill_id=skill_id, url=git_url)
        async with self._git_lock(skill_id):
            await self._git_cmd(skill_id, "clone", git_url, skill_dir, timeout=60.0)
            commit_sha = await self._git_cmd(skill_id, "rev-parse", "HEAD", cwd=skill_dir, timeout=10.0)

        # 3. Validate manifest
        manifest = self._load_manifest(skill_dir)
        if manifest.id != skill_id:
            raise ValueError(f"Manifest id '{manifest.id}' does not match requested skill_id '{skill_id}'")

        # 4. Build base_url from manifest
        port = manifest.runtime.get("port", 8500)
        if self._use_docker:
            base_url = f"http://skill-{skill_id}:{port}"
        else:
            # Native dev: assign ephemeral port on enable
            base_url = f"http://localhost:{port}"

        # 5. Upsert DB row
        async with get_db_session_manual() as db:
            result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
            existing = result.scalar_one_or_none()

            if existing:
                existing.name = manifest.name
                existing.description = manifest.description
                existing.version = manifest.version
                existing.author = manifest.author
                existing.category = manifest.category
                existing.manifest = manifest.model_dump()
                existing.base_url = base_url
                existing.status = "pending"
                existing.installed_by = installed_by or existing.installed_by
                existing.source_url = git_url
                existing.source_ref = "main"
                existing.installed_commit_sha = commit_sha
                existing.previous_version = None
                existing.previous_commit_sha = None
                existing.previous_image_tag = None
            else:
                skill = SkillRegistry(
                    id=skill_id,
                    name=manifest.name,
                    description=manifest.description,
                    version=manifest.version,
                    author=manifest.author,
                    category=manifest.category,
                    manifest=manifest.model_dump(),
                    base_url=base_url,
                    status="pending",
                    installed_by=installed_by,
                    source_url=git_url,
                    source_ref="main",
                    installed_commit_sha=commit_sha,
                )
                db.add(skill)
            await db.commit()

        logger.info("scm.install_success", skill_id=skill_id, version=manifest.version, commit=commit_sha)
        return existing or skill  # type: ignore[return-value]

    # ── Enable / Build / Run ───────────────────────────────────────────────

    async def enable(self, skill_id: str) -> None:
        """Build and start the skill container."""
        skill_dir = self._skill_dir(skill_id)
        if not os.path.exists(skill_dir):
            raise ValueError(f"Skill directory '{skill_dir}' missing")

        manifest = self._load_manifest(skill_dir)
        port = manifest.runtime.get("port", 8500)

        # Native dev: assign ephemeral port
        host_port: int | None = None
        if not self._use_docker:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", 0))
                host_port = s.getsockname()[1]
            async with get_db_session_manual() as db:
                result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                skill = result.scalar_one_or_none()
                if not skill:
                    raise ValueError(f"Skill '{skill_id}' not found")
                skill.base_url = f"http://localhost:{host_port}"
                skill.status = "active"
                await db.commit()
            logger.info("scm.native_enabled", skill_id=skill_id, port=host_port)
            return

        # Docker mode
        image_tag = f"isli/skill-{skill_id}:{manifest.version or 'latest'}"
        container_name = f"skill-{skill_id}"

        # Stop existing
        await self.disable(skill_id)

        # Build
        logger.info("scm.building", skill_id=skill_id, image=image_tag)
        async with get_db_session_manual() as db:
            result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
            skill = result.scalar_one_or_none()
            if skill:
                skill.last_probe_status = "building"
            await db.commit()
        try:
            await asyncio.to_thread(
                self._docker.images.build,
                path=skill_dir,
                tag=image_tag,
                rm=True,
                forcerm=True,
            )
        except Exception as exc:
            logger.error("scm.build_failed", skill_id=skill_id, error=str(exc))
            async with get_db_session_manual() as db:
                result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                skill = result.scalar_one_or_none()
                if skill:
                    skill.status = "error"
                    skill.last_probe_status = "error"
                    skill.last_probe_result = {"error": str(exc)}
                    skill.last_probe_at = datetime.now(timezone.utc)
                await db.commit()
            raise RuntimeError(f"Docker build failed for skill {skill_id}: {exc}") from exc

        # Run
        try:
            container = await asyncio.to_thread(
                self._docker.containers.run,
                image_tag,
                name=container_name,
                network=get_settings().skill_network,
                detach=True,
                ports={f"{port}/tcp": None} if not self._use_docker else {},
                environment={
                    "PORT": str(port),
                    "JWT_SECRET": get_settings().jwt_secret,
                    "LOG_LEVEL": "info",
                },
                labels={"isli.skill.id": skill_id, "isli.managed": "true"},
                restart_policy={"Name": "on-failure", "MaximumRetryCount": 3},
            )
            logger.info("scm.running", skill_id=skill_id, container=container.short_id)

            async with get_db_session_manual() as db:
                result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                skill = result.scalar_one_or_none()
                if skill:
                    run = SkillRun(
                        skill_id=skill_id,
                        container_id=container.id,
                        container_name=container_name,
                        status="running",
                        started_at=datetime.now(timezone.utc),
                    )
                    db.add(run)
                    skill.status = "active"
                    skill.last_probe_status = "healthy"
                    skill.last_probe_result = {"container_id": container.id, "container_name": container_name}
                    skill.last_probe_at = datetime.now(timezone.utc)
                await db.commit()
        except Exception as exc:
            logger.error("scm.run_failed", skill_id=skill_id, error=str(exc))
            async with get_db_session_manual() as db:
                result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                skill = result.scalar_one_or_none()
                if skill:
                    skill.status = "error"
                    skill.last_probe_status = "error"
                    skill.last_probe_result = {"error": str(exc)}
                    skill.last_probe_at = datetime.now(timezone.utc)
                await db.commit()
            raise RuntimeError(f"Docker run failed for skill {skill_id}: {exc}") from exc

    # ── Disable / Stop ───────────────────────────────────────────────────────

    async def disable(self, skill_id: str) -> None:
        """Stop the skill container and mark inactive."""
        if not self._use_docker:
            async with get_db_session_manual() as db:
                result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                skill = result.scalar_one_or_none()
                if skill:
                    skill.status = "disabled"
                    await db.commit()
            return

        container_name = f"skill-{skill_id}"
        try:
            containers = await asyncio.to_thread(
                self._docker.containers.list,
                all=True,
                filters={"name": container_name},
            )
            for c in containers:
                c_name = c.name.lstrip("/")
                if c.labels.get("isli.skill.id") == skill_id or c_name == container_name:
                    logger.info("scm.stopping", skill_id=skill_id, container=c.short_id)
                    await asyncio.to_thread(c.stop, timeout=10)
                    await asyncio.to_thread(c.remove, force=True)
        except Exception as exc:
            logger.warning("scm.disable_stop_warning", skill_id=skill_id, error=str(exc))

        async with get_db_session_manual() as db:
            result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
            skill = result.scalar_one_or_none()
            if skill:
                skill.status = "disabled"

            result2 = await db.execute(
                select(SkillRun).where(SkillRun.skill_id == skill_id, SkillRun.status.in_(["running", "pending"]))
            )
            for run in result2.scalars().all():
                run.status = "stopped"
                run.stopped_at = datetime.now(timezone.utc)
            await db.commit()

    # ── Uninstall ──────────────────────────────────────────────────────────

    async def uninstall(self, skill_id: str) -> None:
        await self.disable(skill_id)

        skill_dir = self._skill_dir(skill_id)
        if os.path.exists(skill_dir):
            shutil.rmtree(skill_dir, ignore_errors=True)

        # Remove image
        if self._use_docker:
            try:
                image_tag = f"isli/skill-{skill_id}"
                images = await asyncio.to_thread(self._docker.images.list, filters={"reference": image_tag})
                for img in images:
                    await asyncio.to_thread(self._docker.images.remove, img.id, force=True)
            except Exception as exc:
                logger.warning("scm.uninstall_image_warning", skill_id=skill_id, error=str(exc))

        async with get_db_session_manual() as db:
            result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
            skill = result.scalar_one_or_none()
            if skill:
                await db.delete(skill)
                await db.commit()
        logger.info("scm.uninstalled", skill_id=skill_id)

    # ── Health Probe ───────────────────────────────────────────────────────

    async def probe(self, skill_id: str) -> dict[str, Any]:
        """Health-check a running skill via its /health endpoint."""
        async with get_db_session_manual() as db:
            result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
            skill = result.scalar_one_or_none()
        if not skill:
            return {"ok": False, "error": "not_found"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{skill.base_url}/health")
                resp.raise_for_status()
                data = resp.json()
                async with get_db_session_manual() as db:
                    result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                    skill = result.scalar_one_or_none()
                    if skill:
                        skill.last_probe_status = "healthy"
                        skill.last_probe_result = data
                        skill.last_probe_at = datetime.now(timezone.utc)
                    await db.commit()
                return {"ok": True, "data": data}
        except Exception as exc:
            async with get_db_session_manual() as db:
                result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                skill = result.scalar_one_or_none()
                if skill:
                    skill.last_probe_status = "unhealthy"
                    skill.last_probe_result = {"error": str(exc)}
                    skill.last_probe_at = datetime.now(timezone.utc)
                await db.commit()
            return {"ok": False, "error": str(exc)}

    # ── Versioning: Check Update ─────────────────────────────────────────────

    async def check_update(self, skill_id: str) -> dict[str, Any]:
        """Check remote for a newer version. Returns update metadata dict."""
        skill = await self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill '{skill_id}' not found")
        if not skill.source_url:
            raise ValueError(f"Skill '{skill_id}' has no source_url")

        source_ref = skill.source_ref or "main"
        async with self._git_lock(skill_id):
            try:
                remote_out = await self._git_cmd(
                    skill_id, "ls-remote", skill.source_url, source_ref, timeout=10.0
                )
            except RuntimeError as exc:
                logger.warning("scm.check_update_ls_remote_failed", skill_id=skill_id, error=str(exc))
                raise RuntimeError(f"Failed to check remote: {exc}") from exc

            parts = remote_out.split()
            if not parts:
                raise RuntimeError(f"git ls-remote returned no output for {source_ref}")
            latest_commit = parts[0]

            if skill.installed_commit_sha == latest_commit:
                # No change — just update last_checked_at
                async with get_db_session_manual() as db:
                    result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                    row = result.scalar_one_or_none()
                    if row:
                        row.last_checked_at = datetime.now(timezone.utc)
                    await db.commit()
                return {
                    "has_update": False,
                    "current_version": skill.version,
                    "latest_version": skill.latest_version,
                    "current_commit": skill.installed_commit_sha,
                    "latest_commit": latest_commit,
                    "changelog": [],
                    "update_policy": skill.update_policy,
                    "last_checked_at": datetime.now(timezone.utc).isoformat(),
                }

            # Shallow clone to temp dir to read manifest + changelog
            tmp_dir = os.path.join(self.base_path, f".{skill_id}-tmp")
            try:
                if os.path.exists(tmp_dir):
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                await self._git_cmd(
                    skill_id, "clone", "--depth", "1", "--branch", source_ref,
                    skill.source_url, tmp_dir, timeout=30.0
                )
                manifest = self._load_manifest(tmp_dir)
                changelog = self._parse_changelog(tmp_dir)
            finally:
                if os.path.exists(tmp_dir):
                    shutil.rmtree(tmp_dir, ignore_errors=True)

            async with get_db_session_manual() as db:
                result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                row = result.scalar_one_or_none()
                if row:
                    row.latest_commit_sha = latest_commit
                    row.latest_version = manifest.version
                    row.changelog = changelog
                    row.last_checked_at = datetime.now(timezone.utc)
                await db.commit()

            return {
                "has_update": True,
                "current_version": skill.version,
                "latest_version": manifest.version,
                "current_commit": skill.installed_commit_sha,
                "latest_commit": latest_commit,
                "changelog": changelog,
                "update_policy": skill.update_policy,
                "last_checked_at": datetime.now(timezone.utc).isoformat(),
            }

    # ── Versioning: Update ───────────────────────────────────────────────────

    async def update(self, skill_id: str, target_version: str | None = None, force: bool = False) -> SkillRegistry:
        """Pull new source, build new image, blue/green swap containers."""
        if not await self._acquire_skill_lock(skill_id, ttl=120):
            raise RuntimeError("Update already in progress for this skill")

        try:
            skill = await self._get_skill(skill_id)
            if not skill:
                raise ValueError(f"Skill '{skill_id}' not found")
            if skill.update_policy == "pinned" and not force:
                raise RuntimeError("Skill update policy is 'pinned'. Use force=True to override.")

            source_ref = skill.source_ref or "main"
            skill_dir = self._skill_dir(skill_id)

            # Resolve target ref
            target_ref = source_ref
            if target_version:
                target_ref = target_version if target_version.startswith("v") else f"v{target_version}"

            # Save rollback state
            prev_version = skill.version
            prev_commit = skill.installed_commit_sha
            prev_image = f"isli/skill-{skill_id}:{skill.version or 'latest'}"

            # Pull / checkout new source under git lock
            async with self._git_lock(skill_id):
                if os.path.exists(os.path.join(skill_dir, ".git")):
                    await self._git_cmd(
                        skill_id, "fetch", "origin", target_ref, cwd=skill_dir, timeout=30.0
                    )
                    await self._git_cmd(skill_id, "checkout", target_ref, cwd=skill_dir, timeout=30.0)
                    # For branch refs, checkout alone leaves the local branch stale.
                    # Hard-reset to the fetched remote tip so the source actually advances.
                    is_tag = target_ref.startswith("v") or target_ref.startswith("refs/tags/")
                    if not is_tag:
                        await self._git_cmd(
                            skill_id, "reset", "--hard", f"origin/{target_ref}",
                            cwd=skill_dir, timeout=30.0,
                        )
                else:
                    if os.path.exists(skill_dir):
                        shutil.rmtree(skill_dir, ignore_errors=True)
                    await self._git_cmd(
                        skill_id, "clone", "--branch", target_ref, "--single-branch",
                        skill.source_url, skill_dir, timeout=60.0
                    )
                new_commit = await self._git_cmd(skill_id, "rev-parse", "HEAD", cwd=skill_dir, timeout=10.0)

            manifest = self._load_manifest(skill_dir)
            if manifest.id != skill_id:
                raise ValueError(f"Manifest id '{manifest.id}' does not match skill_id '{skill_id}'")
            new_version = manifest.version or "latest"

            # Native dev: just update DB, no container swap
            if not self._use_docker:
                async with get_db_session_manual() as db:
                    result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                    row = result.scalar_one_or_none()
                    if row:
                        row.previous_version = prev_version
                        row.previous_commit_sha = prev_commit
                        row.previous_image_tag = prev_image
                        row.version = new_version
                        row.installed_commit_sha = new_commit
                        row.status = "active"
                        row.last_probe_status = "healthy"
                    await db.commit()
                await EventManager.emit("skill:updated", {
                    "skill_id": skill_id, "version": new_version, "status": "active"
                })
                return row  # type: ignore[return-value]

            # Docker mode: blue/green swap
            new_image_tag = f"isli/skill-{skill_id}:{new_version}"
            old_container_name = f"skill-{skill_id}"
            next_container_name = f"skill-{skill_id}-next"
            port = manifest.runtime.get("port", 8500)

            # Tag old image for rollback before we potentially overwrite the tag
            if prev_version:
                rollback_tag = f"isli/skill-{skill_id}:rollback-{_time.time():.0f}"
                try:
                    await asyncio.to_thread(
                        self._docker.images.get, prev_image
                    )
                    # Image exists — tag it
                    img = await asyncio.to_thread(self._docker.images.get, prev_image)
                    await asyncio.to_thread(img.tag, rollback_tag)
                    logger.info("scm.tagged_rollback_image", skill_id=skill_id, tag=rollback_tag)
                except Exception:
                    pass
            else:
                rollback_tag = None

            # Stop existing to free the name
            await self.disable(skill_id)

            # Build new image
            logger.info("scm.update_building", skill_id=skill_id, image=new_image_tag)
            try:
                await asyncio.to_thread(
                    self._docker.images.build,
                    path=skill_dir,
                    tag=new_image_tag,
                    rm=True,
                    forcerm=True,
                )
            except Exception as exc:
                logger.error("scm.update_build_failed", skill_id=skill_id, error=str(exc))
                # Attempt to restart old container
                try:
                    await self.enable(skill_id)
                except Exception:
                    pass
                raise RuntimeError(f"Docker build failed for skill {skill_id}: {exc}") from exc

            # Run next container on the shared skill network
            try:
                next_container = await asyncio.to_thread(
                    self._docker.containers.run,
                    new_image_tag,
                    name=next_container_name,
                    network=get_settings().skill_network,
                    detach=True,
                    environment={
                        "PORT": str(port),
                        "JWT_SECRET": get_settings().jwt_secret,
                        "LOG_LEVEL": "info",
                    },
                    labels={"isli.skill.id": skill_id, "isli.managed": "true"},
                    restart_policy={"Name": "on-failure", "MaximumRetryCount": 3},
                )
                # Probe via the container's Docker DNS name on the skill network.
                # localhost does not work because Core itself runs in a container.
                next_base_url = f"http://{next_container_name}:{port}"
            except Exception as exc:
                logger.error("scm.update_run_failed", skill_id=skill_id, error=str(exc))
                try:
                    await self.enable(skill_id)
                except Exception:
                    pass
                raise RuntimeError(f"Docker run failed for skill {skill_id}: {exc}") from exc

            # Probe next container
            probe_result = await self._probe_swap(skill_id, next_base_url)
            if not probe_result["ok"]:
                logger.error("scm.update_probe_failed", skill_id=skill_id, error=probe_result["error"])
                # Stop next container, restart old
                try:
                    await asyncio.to_thread(next_container.stop, timeout=10)
                    await asyncio.to_thread(next_container.remove, force=True)
                except Exception:
                    pass
                try:
                    await self.enable(skill_id)
                except Exception:
                    pass
                async with get_db_session_manual() as db:
                    result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                    row = result.scalar_one_or_none()
                    if row:
                        row.status = "error"
                        row.last_probe_status = "error"
                    await db.commit()
                raise RuntimeError(f"Probe failed for updated skill {skill_id}: {probe_result['error']}")

            # Swap succeeded: stop old container (already disabled), rename next
            logger.info("scm.update_swap_succeeded", skill_id=skill_id, new_version=new_version)
            try:
                await asyncio.to_thread(next_container.rename, old_container_name)
            except Exception as exc:
                logger.warning("scm.rename_warning", skill_id=skill_id, error=str(exc))

            # Persist SkillRun and update DB
            async with get_db_session_manual() as db:
                result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                row = result.scalar_one_or_none()
                if row:
                    row.previous_version = prev_version
                    row.previous_commit_sha = prev_commit
                    row.previous_image_tag = rollback_tag or prev_image
                    row.version = new_version
                    row.installed_commit_sha = new_commit
                    row.status = "active"
                    row.last_probe_status = "healthy"
                    row.last_probe_result = probe_result["data"]
                    row.last_probe_at = datetime.now(timezone.utc)

                run = SkillRun(
                    skill_id=skill_id,
                    container_id=next_container.id,
                    container_name=old_container_name,
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
                db.add(run)
                await db.commit()

            await EventManager.emit("skill:updated", {
                "skill_id": skill_id, "version": new_version, "status": "active"
            })
            return row  # type: ignore[return-value]
        finally:
            await self._release_skill_lock(skill_id)

    # ── Versioning: Rollback ───────────────────────────────────────────────

    async def rollback(self, skill_id: str) -> SkillRegistry:
        """Rollback to the previous version."""
        if not await self._acquire_skill_lock(skill_id, ttl=120):
            raise RuntimeError("Rollback already in progress for this skill")

        try:
            skill = await self._get_skill(skill_id)
            if not skill:
                raise ValueError(f"Skill '{skill_id}' not found")
            if not skill.previous_commit_sha:
                raise ValueError(f"Skill '{skill_id}' has no previous version to rollback to")

            prev_version = skill.previous_version
            prev_commit = skill.previous_commit_sha
            prev_image = skill.previous_image_tag
            skill_dir = self._skill_dir(skill_id)

            # Checkout previous commit under git lock
            async with self._git_lock(skill_id):
                await self._git_cmd(skill_id, "checkout", prev_commit, cwd=skill_dir, timeout=30.0)
                current_commit = await self._git_cmd(skill_id, "rev-parse", "HEAD", cwd=skill_dir, timeout=10.0)
                if current_commit != prev_commit:
                    raise RuntimeError(f"Rollback checkout failed: expected {prev_commit}, got {current_commit}")

            manifest = self._load_manifest(skill_dir)
            if manifest.id != skill_id:
                raise ValueError(f"Manifest id '{manifest.id}' does not match skill_id '{skill_id}'")

            if not self._use_docker:
                async with get_db_session_manual() as db:
                    result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                    row = result.scalar_one_or_none()
                    if row:
                        row.version = prev_version
                        row.installed_commit_sha = prev_commit
                        row.previous_version = None
                        row.previous_commit_sha = None
                        row.previous_image_tag = None
                        row.status = "active"
                    await db.commit()
                await EventManager.emit("skill:updated", {
                    "skill_id": skill_id, "version": prev_version, "status": "active"
                })
                return row  # type: ignore[return-value]

            # Docker rollback
            port = manifest.runtime.get("port", 8500)
            old_container_name = f"skill-{skill_id}"
            next_container_name = f"skill-{skill_id}-next"

            await self.disable(skill_id)

            # Try to run previous image on the shared skill network
            try:
                next_container = await asyncio.to_thread(
                    self._docker.containers.run,
                    prev_image or f"isli/skill-{skill_id}:{prev_version or 'latest'}",
                    name=next_container_name,
                    network=get_settings().skill_network,
                    detach=True,
                    environment={
                        "PORT": str(port),
                        "JWT_SECRET": get_settings().jwt_secret,
                        "LOG_LEVEL": "info",
                    },
                    labels={"isli.skill.id": skill_id, "isli.managed": "true"},
                    restart_policy={"Name": "on-failure", "MaximumRetryCount": 3},
                )
                # Probe via the container's Docker DNS name on the skill network.
                next_base_url = f"http://{next_container_name}:{port}"
            except Exception as exc:
                raise RuntimeError(f"Docker run failed during rollback for skill {skill_id}: {exc}") from exc

            probe_result = await self._probe_swap(skill_id, next_base_url)
            if not probe_result["ok"]:
                try:
                    await asyncio.to_thread(next_container.stop, timeout=10)
                    await asyncio.to_thread(next_container.remove, force=True)
                except Exception:
                    pass
                raise RuntimeError(f"Probe failed during rollback for skill {skill_id}: {probe_result['error']}")

            try:
                await asyncio.to_thread(next_container.rename, old_container_name)
            except Exception as exc:
                logger.warning("scm.rollback_rename_warning", skill_id=skill_id, error=str(exc))

            async with get_db_session_manual() as db:
                result = await db.execute(select(SkillRegistry).where(SkillRegistry.id == skill_id))
                row = result.scalar_one_or_none()
                if row:
                    row.version = prev_version
                    row.installed_commit_sha = prev_commit
                    row.previous_version = None
                    row.previous_commit_sha = None
                    row.previous_image_tag = None
                    row.status = "active"
                    row.last_probe_status = "healthy"
                    row.last_probe_result = probe_result["data"]
                    row.last_probe_at = datetime.now(timezone.utc)

                run = SkillRun(
                    skill_id=skill_id,
                    container_id=next_container.id,
                    container_name=old_container_name,
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
                db.add(run)
                await db.commit()

            await EventManager.emit("skill:updated", {
                "skill_id": skill_id, "version": prev_version, "status": "active"
            })
            return row  # type: ignore[return-value]
        finally:
            await self._release_skill_lock(skill_id)

    # ── Cleanup Old Images ───────────────────────────────────────────────────

    async def cleanup_old_images(self, skill_id: str, keep_last: int = 2) -> None:
        """Prune old Docker images for this skill, keeping active + last N + rollback."""
        if not self._use_docker:
            return
        skill = await self._get_skill(skill_id)
        if not skill:
            return
        active_tag = f"isli/skill-{skill_id}:{skill.version or 'latest'}"
        rollback_tag = skill.previous_image_tag
        prefix = f"isli/skill-{skill_id}:"
        try:
            images = await asyncio.to_thread(self._docker.images.list, filters={"reference": prefix})
            sorted_images = sorted(images, key=lambda img: img.attrs.get("Created", ""), reverse=True)
            protected = {active_tag}
            if rollback_tag:
                protected.add(rollback_tag)
            for img in sorted_images[keep_last:]:
                tags = img.tags or []
                if any(t in protected for t in tags):
                    continue
                for t in tags:
                    if t.startswith(prefix):
                        await asyncio.to_thread(self._docker.images.remove, img.id, force=True)
                        logger.info("scm.pruned_image", skill_id=skill_id, image=t)
                        break
        except Exception as exc:
            logger.warning("scm.cleanup_images_warning", skill_id=skill_id, error=str(exc))


# ── Singleton façade that merges both managers ──────────────────────────────

class _UnifiedSkillManager:
    """Exposes legacy DynamicSkillManager API while adding DB-backed external skills."""

    def __init__(self):
        self._dynamic = DynamicSkillManager()
        self._container = SkillContainerManager()

    # Legacy passthroughs
    def refresh_registry(self) -> None:
        self._dynamic.refresh_registry()

    def get_handler(self, skill_id: str):
        return self._dynamic.get_handler(skill_id)

    def get_skill_metadata(self) -> dict[str, dict[str, Any]]:
        """Merge legacy filesystem skills + DB container skills."""
        meta = dict(self._dynamic.get_skill_metadata())
        # Add DB skills in the background (fire-and-forget sync via asyncio if needed,
        # but this method is sync so we return stale cached metadata from last async call.
        # In practice, the list_skills endpoint is async and calls get_metadata() async.)
        return meta

    async def get_all_metadata(self) -> dict[str, dict[str, Any]]:
        meta = dict(self._dynamic.get_skill_metadata())
        db_meta = await self._container.get_metadata()
        meta.update(db_meta)
        return meta

    async def get_registry(self) -> dict[str, str]:
        return await self._container.get_registry()

    # Container lifecycle passthroughs
    async def install_from_git(self, skill_id: str, git_url: str, installed_by: str | None = None) -> SkillRegistry:
        return await self._container.install_from_git(skill_id, git_url, installed_by)

    async def enable(self, skill_id: str) -> None:
        await self._container.enable(skill_id)

    async def disable(self, skill_id: str) -> None:
        await self._container.disable(skill_id)

    async def uninstall(self, skill_id: str) -> None:
        await self._container.uninstall(skill_id)

    async def get_skill_manifest(self, skill_id: str) -> dict[str, Any] | None:
        return await self._container.get_skill_manifest(skill_id)

    async def probe(self, skill_id: str) -> dict[str, Any]:
        return await self._container.probe(skill_id)

    async def check_update(self, skill_id: str) -> dict[str, Any]:
        return await self._container.check_update(skill_id)

    async def update(self, skill_id: str, target_version: str | None = None, force: bool = False) -> SkillRegistry:
        return await self._container.update(skill_id, target_version, force)

    async def rollback(self, skill_id: str) -> SkillRegistry:
        return await self._container.rollback(skill_id)

    async def cleanup_old_images(self, skill_id: str, keep_last: int = 2) -> None:
        return await self._container.cleanup_old_images(skill_id, keep_last)


skill_manager = _UnifiedSkillManager()
