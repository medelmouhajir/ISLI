import os
import time
from pathlib import Path
from typing import Any

import docker
from docker.errors import DockerException, APIError
import structlog
from fastapi import HTTPException

from .config import get_settings

logger = structlog.get_logger()

def sanitize_working_dir(working_dir: str | None) -> str:
    """Sanitize working directory to prevent path traversal."""
    if not working_dir or working_dir == ".":
        return "."
    
    # Block absolute paths and parent directory traversal
    if working_dir.startswith("/") or ".." in working_dir or "\\" in working_dir:
        raise ValueError(f"Invalid working directory: {working_dir}")
    
    return working_dir

async def run_sandboxed_command(
    agent_id: str,
    command: str,
    timeout: int | None = None,
    working_dir: str | None = None,
) -> dict[str, Any]:
    """Execute a command in an ephemeral, highly restricted Docker container."""
    settings = get_settings()
    
    timeout = timeout or settings.shell_exec_timeout_default
    timeout = min(timeout, settings.shell_exec_timeout_max)
    
    try:
        working_dir = sanitize_working_dir(working_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Construct paths
    # The workspace volume is mounted at settings.workspace_base_path in the HOST/SKILLS service
    # Inside the sandbox container, we mount the same volume at /workspace
    container_workspace_root = "/workspace"
    container_working_dir = f"{container_workspace_root}/agents/{agent_id}/{working_dir}".rstrip("/")

    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.error("shell_exec.docker_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail=f"Sandbox engine unavailable: {exc}")

    start_time = time.perf_counter()
    container = None
    try:
        logger.info("shell_exec.starting", agent_id=agent_id, command=command[:100])
        
        # CPU limits calculation
        cpu_period = 100000
        cpu_quota = int(cpu_period * settings.shell_exec_cpu_limit)

        # We assume the volume name is 'workspace_data' as per docker-compose.yml
        # Note: In some environments (like CI or local dev with project prefixes), 
        # the volume name might be prefixed. 
        # For ISLI, we assume standard volume naming or use environment variable if needed.
        volume_name = os.getenv("WORKSPACE_VOLUME_NAME", "workspace_data")

        container = client.containers.run(
            image=settings.shell_exec_image,
            command=["/bin/sh", "-c", command],
            working_dir=container_working_dir,
            volumes={volume_name: {'bind': container_workspace_root, 'mode': 'rw'}},
            network_mode='none',
            mem_limit=settings.shell_exec_mem_limit,
            cpu_period=cpu_period,
            cpu_quota=cpu_quota,
            read_only=True,
            cap_drop=['ALL'],
            security_opt=['no-new-privileges:true'],
            user='1000:1000',
            detach=True,
        )

        try:
            # Wait for container to exit with timeout
            result = container.wait(timeout=timeout)
            exit_code = result.get("StatusCode", -1)
            timed_out = False
        except Exception:
            # Handle timeout (docker library raises Exception or specific timeout error)
            try:
                container.kill()
            except Exception:
                pass
            exit_code = -1
            timed_out = True

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        # Harvest logs
        logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
        
        # Truncate logs if they exceed limits
        if len(logs) > settings.shell_exec_output_limit:
            logs = logs[:settings.shell_exec_output_limit] + "\n[Output truncated...]"

        response = {
            "stdout": logs,
            "stderr": "",
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "timed_out": timed_out,
        }
        
        if timed_out:
            response["error"] = f"Command timed out after {timeout} seconds"
            
        return response

    except APIError as exc:
        logger.error("shell_exec.docker_api_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Sandbox execution error: {exc}")
    finally:
        if container:
            try:
                container.remove(force=True)
            except Exception:
                pass
