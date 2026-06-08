import asyncio
import contextlib
import json
import os
import sys
import threading
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import Request

logger = structlog.get_logger()


async def _update_agent_status(agent_id: str, status: str, reason: str | None = None) -> None:
    """Persist agent process exit status to the database."""
    from sqlalchemy import update

    from isli_core.db import get_db_session_manual
    from isli_core.models import Agent

    try:
        async with get_db_session_manual() as db:
            await db.execute(
                update(Agent)
                .where(Agent.id == agent_id, Agent.deleted_at.is_(None))
                .values(status=status, status_reason=reason)
            )
            await db.commit()
            logger.info("pm.agent_status_updated", agent_id=agent_id, status=status, reason=reason)
    except Exception as exc:
        logger.error("pm.agent_status_update_failed", agent_id=agent_id, error=str(exc))


class AgentProcessManager:
    def __init__(self, sdk_path: str, core_url: str):
        self.sdk_path = sdk_path
        self.core_url = core_url
        self._use_docker = self._detect_docker()
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._containers: dict[str, str] = {}  # agent_id -> container_id
        self._crash_counts: dict[str, int] = {}
        self._docker: Any = None

        if self._use_docker:
            try:
                import docker
                self._docker = docker.from_env()
                logger.info("pm.docker_mode_enabled")
            except Exception as exc:
                logger.warning("pm.docker_unavailable", error=str(exc))
                self._use_docker = False

    def _detect_docker(self) -> bool:
        return os.path.exists("/var/run/docker.sock")

    # ── Public API ────────────────────────────────────────────────────

    async def spawn(self, agent_id: str) -> None:
        if self._use_docker:
            await self._spawn_docker(agent_id)
        else:
            await self._spawn_subprocess(agent_id)

    async def terminate(self, agent_id: str) -> None:
        if self._use_docker:
            await self._terminate_docker(agent_id)
        else:
            await self._terminate_subprocess(agent_id)

    def is_running(self, agent_id: str) -> bool:
        if self._use_docker:
            return agent_id in self._containers
        proc = self._processes.get(agent_id)
        return proc is not None and proc.returncode is None

    def get_status(self, agent_id: str) -> dict:
        status = {
            "running": self.is_running(agent_id),
            "crash_count": self._crash_counts.get(agent_id, 0),
            "pid": None,
            "container": None,
        }
        if self._use_docker:
            status["container"] = self._containers.get(agent_id)
        else:
            proc = self._processes.get(agent_id)
            if proc and proc.returncode is None:
                status["pid"] = proc.pid
        return status

    async def reconcile(self) -> None:
        """Sync internal state with running Docker containers on startup."""
        if not self._use_docker or self._docker is None:
            return

        try:
            containers = await asyncio.to_thread(
                self._docker.containers.list,
                filters={"label": "isli.service=agent-runner"},
            )
            for container in containers:
                agent_id = container.labels.get("isli.agent_id")
                if not agent_id or agent_id in self._containers:
                    continue
                if container.status == "running":
                    self._containers[agent_id] = container.id
                    logger.info("pm.reconcile.found", agent_id=agent_id, container=container.name)
                    asyncio.create_task(self._watch_docker(agent_id, container.name))
        except Exception as exc:
            logger.warning("pm.reconcile.failed", error=str(exc))

    # ── Agent env resolution ────────────────────────────────────────────

    async def _resolve_agent_env(self, agent_id: str) -> dict[str, str]:
        """Query DB to resolve agent-specific API keys and base URLs.

        Maps the provider to the LiteLLM env-var name so the SDK doesn't
        need to know every provider's convention.
        """
        from sqlalchemy import select
        from isli_core.db import get_db_session_manual
        from isli_core.models import Agent, LlmProvider

        resolved: dict[str, str] = {}
        try:
            async with get_db_session_manual() as db:
                agent_result = await db.execute(
                    select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None))
                )
                agent = agent_result.scalar_one_or_none()
                if not agent:
                    logger.warning("pm.resolve_env.agent_not_found", agent_id=agent_id)
                    return resolved

                provider_name = agent.model_provider
                if not provider_name:
                    return resolved

                api_key = agent.api_key
                api_base = None
                if not api_key:
                    provider_result = await db.execute(
                        select(LlmProvider).where(LlmProvider.provider == provider_name)
                    )
                    provider = provider_result.scalar_one_or_none()
                    if provider:
                        api_key = provider.api_key
                        api_base = provider.api_base

                # Map provider to LiteLLM env-var names
                provider_env_map = {
                    "ollama": "OLLAMA_API_KEY",
                    "openai": "OPENAI_API_KEY",
                    "anthropic": "ANTHROPIC_API_KEY",
                    "google": "GEMINI_API_KEY",
                    "deepseek": "DEEPSEEK_API_KEY",
                    "azure": "AZURE_API_KEY",
                    "vertex": "VERTEXAI_API_KEY",
                    "vertex_ai": "VERTEXAI_API_KEY",
                }
                env_key = provider_env_map.get(provider_name.lower())
                if env_key and api_key:
                    resolved[env_key] = api_key

                # Also inject api_base if we resolved one
                base_env_map = {
                    "ollama": "OLLAMA_API_BASE",
                    "openai": "OPENAI_API_BASE",
                    "anthropic": "ANTHROPIC_API_BASE",
                    "google": "GEMINI_API_BASE",
                    "deepseek": "DEEPSEEK_API_BASE",
                    "azure": "AZURE_API_BASE",
                    "vertex": "VERTEXAI_LOCATION",
                    "vertex_ai": "VERTEXAI_LOCATION",
                }
                base_env = base_env_map.get(provider_name.lower())
                if base_env and api_base:
                    resolved[base_env] = api_base

                # Inject PII mesh config per agent
                agent_config = agent.config or {}
                resolved["PII_MESH_ENABLED"] = str(agent_config.get("pii_mesh_enabled", False)).lower()
                resolved["PII_USE_SLM"] = str(agent_config.get("pii_use_slm", True)).lower()
                resolved["KEEPER_URL"] = get_settings().keeper_url

                logger.info(
                    "pm.resolve_env.done",
                    agent_id=agent_id,
                    provider=provider_name,
                    key_injected=bool(api_key),
                    base_injected=bool(api_base),
                    pii_mesh=resolved.get("PII_MESH_ENABLED"),
                )
        except Exception as exc:
            logger.warning("pm.resolve_env.failed", agent_id=agent_id, error=str(exc))
        return resolved

    # ── Docker backend ──────────────────────────────────────────────────

    async def _spawn_docker(self, agent_id: str) -> None:
        if self._docker is None:
            raise RuntimeError("Docker client not initialized")

        container_name = f"isli-agent-{agent_id}"

        # Defensively remove any stale container with the same name, then
        # poll until Docker actually frees the name. If the old container
        # is stuck in "Removal In Progress" we get a 409 on create.
        try:
            old = await asyncio.to_thread(self._docker.containers.get, container_name)
            await asyncio.to_thread(old.remove, force=True)
            logger.warning("pm.spawn.removed_stale", agent_id=agent_id, container=container_name)
        except Exception:
            pass  # Container does not exist

        for _ in range(20):
            try:
                await asyncio.to_thread(self._docker.containers.get, container_name)
                await asyncio.sleep(0.5)
            except Exception:
                break
        else:
            logger.warning(
                "pm.spawn.stale_container_still_present",
                agent_id=agent_id,
                container=container_name,
            )

        from isli_core.config import get_settings, IS_DEV
        settings = get_settings()

        agent_env = await self._resolve_agent_env(agent_id)

        env = {
            "AGENT_ID": agent_id,
            "CORE_API_URL": self.core_url,
            "ADMIN_API_KEY": settings.admin_api_key or "",
            "REDIS_URL": settings.redis_url or "redis://redis:6379/0",
            "OLLAMA_API_BASE": os.getenv("OLLAMA_API_BASE", "https://ollama.com"),
            "OLLAMA_API_KEY": os.getenv("OLLAMA_API_KEY", ""),
            "MODEL_PROVIDER": os.getenv("MODEL_PROVIDER", "ollama"),
            "MODEL_ID": os.getenv("MODEL_ID", "qwen2.5:7b"),
        }
        # Agent-specific resolved keys override generic env fallbacks
        env.update(agent_env)

        logger.info(
            "pm.spawn.docker",
            agent_id=agent_id,
            image=settings.agent_runner_image,
            container=container_name,
        )

        volumes = {}
        if IS_DEV and settings.agent_sdk_host_path:
            # In development, mount the host SDK source directly into the agent
            # container so code changes are picked up without rebuilding the image.
            # The Dockerfile already sets PYTHONPATH=/app/src and installs the
            # package as editable, so the mount overlays the live source.
            volumes[settings.agent_sdk_host_path] = {"bind": "/app/src", "mode": "ro"}
            logger.info("pm.spawn.live_sdk_enabled", path=settings.agent_sdk_host_path)

        # Convert high-level volumes dict to low-level API bind mounts.
        # docker-py's containers.run() does this internally, but the low-level
        # create_container requires explicit volumes + host_config.Binds.
        container_volumes: list[str] = []
        volume_binds: list[str] = []
        for host_path, mount_cfg in volumes.items():
            bind_path = mount_cfg.get("bind")
            mode = mount_cfg.get("mode", "rw")
            container_volumes.append(bind_path)
            volume_binds.append(f"{host_path}:{bind_path}:{mode}")

        # Use the low-level API so we can pass stop_timeout (docker-py's
        # high-level containers.run() does not expose it in v7.1.0).
        resp = await asyncio.to_thread(
            self._docker.api.create_container,
            image=settings.agent_runner_image,
            name=container_name,
            environment=env,
            volumes=container_volumes or None,
            labels={"isli.agent_id": agent_id, "isli.service": "agent-runner"},
            stop_timeout=30,
            host_config={
                "NetworkMode": settings.agent_network,
                "Binds": volume_binds or None,
            },
        )
        container_id = resp["Id"]
        await asyncio.to_thread(self._docker.api.start, container_id)
        self._containers[agent_id] = container_id
        asyncio.create_task(self._watch_docker(agent_id, container_name))

    async def _terminate_docker(self, agent_id: str) -> None:
        container_name = f"isli-agent-{agent_id}"
        container_id = self._containers.pop(agent_id, None)
        if container_id:
            try:
                container = await asyncio.to_thread(self._docker.containers.get, container_id)
                if container.status == "running":
                    logger.info(
                        "pm.terminate.stopping", agent_id=agent_id, container=container_name
                    )
                    await asyncio.to_thread(container.stop, timeout=10)
            except Exception as exc:
                logger.warning("pm.terminate.docker_error", agent_id=agent_id, error=str(exc))

    async def rebuild_image(self) -> None:
        """Rebuild the agent-runner Docker image from the configured build context.

        Uses a tar stream (fileobj + custom_context) to bypass the container-side
        path check, sending the build context directly to the Docker daemon over
        the mounted socket. This is necessary because Core runs inside a container
        and the host build-context path does not exist inside Core's filesystem.

        Raises on failure so the caller can update status.
        """
        if self._docker is None:
            raise RuntimeError("Docker client not initialized")

        from isli_core.config import get_settings

        settings = get_settings()
        build_context = settings.agent_runner_build_context or "/opt/isli/isli-agent-sdk"

        # Fallback: if the configured path doesn't exist inside the container,
        # try the standard mount point from docker-compose.override.yml
        if not os.path.isdir(build_context):
            fallback = "/opt/isli/isli-agent-sdk"
            if os.path.isdir(fallback):
                build_context = fallback
            else:
                raise RuntimeError(
                    f"agent_runner_build_context directory not found: {build_context}"
                )

        logger.info(
            "pm.rebuild.start",
            context=build_context,
            image=settings.agent_runner_image,
        )

        def _build():
            import io
            import tarfile

            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                tar.add(build_context, arcname=".")
            buf.seek(0)

            image, logs = self._docker.images.build(
                fileobj=buf,
                custom_context=True,
                encoding="gzip",
                dockerfile="Dockerfile",
                tag=settings.agent_runner_image,
                rm=True,
            )
            for log in logs:
                stream = log.get("stream", "").strip()
                if stream:
                    logger.info("pm.rebuild.log", log=stream)
            return image

        try:
            image = await asyncio.to_thread(_build)
            logger.info("pm.rebuild.done", image_id=image.id)
        except Exception as exc:
            logger.error("pm.rebuild.failed", error=str(exc))
            raise

    async def _watch_docker(self, agent_id: str, container_name: str):
        log_task = None
        try:
            container = await asyncio.to_thread(self._docker.containers.get, container_name)
            # Start log streaming FIRST (non-blocking background task)
            log_task = asyncio.create_task(self._stream_docker_logs(agent_id, container))

            result = await asyncio.to_thread(container.wait)
            returncode = result.get("StatusCode", -1)
            logger.info("pm.container_exited", agent_id=agent_id, returncode=returncode)

            if returncode != 0:
                self._crash_counts[agent_id] = self._crash_counts.get(agent_id, 0) + 1
                logger.error(
                    "pm.container_crashed",
                    agent_id=agent_id,
                    returncode=returncode,
                    crash_count=self._crash_counts[agent_id],
                )
                await _update_agent_status(agent_id, "crashed", f"exited {returncode}")
                from isli_core.event_manager import EventManager
                await EventManager.emit("system:alert", {
                    "severity": "critical",
                    "message": f"Agent {agent_id} container crashed (exit {returncode}).",
                    "agent_id": agent_id,
                    "category": "agent_crash",
                })
            else:
                await _update_agent_status(agent_id, "stopped", f"exited {returncode}")
        except Exception as exc:
            logger.info("pm.container_removed_or_error", agent_id=agent_id, error=str(exc))
            await _update_agent_status(agent_id, "crashed", str(exc))
            from isli_core.event_manager import EventManager
            await EventManager.emit("system:alert", {
                "severity": "critical",
                "message": f"Agent {agent_id} container exception: {exc}",
                "agent_id": agent_id,
                "category": "agent_crash",
            })
        finally:
            self._containers.pop(agent_id, None)
            if log_task is not None:
                log_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await log_task
            # Always remove the container after exit (we no longer use auto_remove)
            try:
                container = await asyncio.to_thread(self._docker.containers.get, container_name)
                await asyncio.to_thread(container.remove, force=True)
            except Exception:
                pass

    async def _stream_docker_logs(self, agent_id: str, container):
        """Stream Docker container stdout/stderr to Redis log channels.

        Runs the blocking Docker log generator in a dedicated thread
        and passes lines back via an asyncio.Queue so the event loop
        is never blocked.
        """
        from isli_core.redis_client import get_redis

        channel = f"agent:{agent_id}:logs"
        history_key = f"agent:{agent_id}:logs:history"
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        cancelled = threading.Event()

        def _read_logs():
            try:
                for raw_line in container.logs(
                    stream=True, follow=True, stdout=True, stderr=True
                ):
                    if cancelled.is_set():
                        break
                    queue.put_nowait(raw_line)
            except Exception:
                pass
            finally:
                queue.put_nowait(None)

        reader = threading.Thread(target=_read_logs, daemon=True)
        reader.start()

        try:
            redis = await get_redis()
            while True:
                raw_line = await queue.get()
                if raw_line is None:
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    payload = {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "level": "info",
                        "event": "agent.log",
                        "agent_id": agent_id,
                        "output": line,
                    }
                json_log = json.dumps(payload)
                await redis.publish(channel, json_log)
                await redis.rpush(history_key, json_log)
                await redis.ltrim(history_key, -1000, -1)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except Exception as exc:
            logger.error("pm.docker_log_stream_error", agent_id=agent_id, error=str(exc))
        finally:
            cancelled.set()
            reader.join(timeout=2.0)

    # ── Subprocess backend ────────────────────────────────────────────

    async def _spawn_subprocess(self, agent_id: str) -> None:
        if agent_id in self._processes:
            proc = self._processes[agent_id]
            if proc.returncode is None:
                logger.warning(
                    "pm.spawn.already_running", agent_id=agent_id, pid=proc.pid
                )
                return

        script_path = os.path.join(self.sdk_path, "examples", "start_agent.py")
        if not os.path.exists(script_path):
            logger.error("pm.spawn.script_not_found", path=script_path)
            raise FileNotFoundError(f"Agent startup script not found at {script_path}")

        logger.info("pm.spawn.starting", agent_id=agent_id, script=script_path)

        agent_env = await self._resolve_agent_env(agent_id)
        subprocess_env = {**os.environ, "CORE_API_URL": self.core_url}
        subprocess_env.update(agent_env)

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            script_path,
            agent_id,
            env=subprocess_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._processes[agent_id] = proc

        asyncio.create_task(self._watch(agent_id, proc))
        asyncio.create_task(self._log_output(agent_id, proc))

    async def _terminate_subprocess(self, agent_id: str) -> None:
        proc = self._processes.pop(agent_id, None)
        if proc and proc.returncode is None:
            logger.info("pm.terminate.sending_sigterm", agent_id=agent_id, pid=proc.pid)
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except TimeoutError:
                logger.warning("pm.terminate.timeout_killing", agent_id=agent_id, pid=proc.pid)
                proc.kill()
                await proc.wait()

    async def _watch(self, agent_id: str, proc: asyncio.subprocess.Process):
        returncode = await proc.wait()
        logger.info("pm.process_exited", agent_id=agent_id, returncode=returncode)

        if returncode != 0 and agent_id in self._processes:
            self._crash_counts[agent_id] = self._crash_counts.get(agent_id, 0) + 1
            logger.error(
                "pm.process_crashed",
                agent_id=agent_id,
                returncode=returncode,
                crash_count=self._crash_counts[agent_id],
            )
            await _update_agent_status(agent_id, "crashed", f"exited {returncode}")
            from isli_core.event_manager import EventManager
            await EventManager.emit("system:alert", {
                "severity": "critical",
                "message": f"Agent {agent_id} process crashed (exit {returncode}).",
                "agent_id": agent_id,
                "category": "agent_crash",
            })
        else:
            await _update_agent_status(agent_id, "stopped", f"exited {returncode}")

    async def _log_output(self, agent_id: str, proc: asyncio.subprocess.Process):
        if proc.stdout:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                logger.info("agent.log", agent_id=agent_id, output=line.decode().strip())


def get_pm(request: Request) -> AgentProcessManager:
    return request.app.state.process_manager
