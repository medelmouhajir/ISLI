"""Recover orphaned tasks from their latest checkpoint."""

import structlog
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Task, Agent
from isli_core.checkpoint import CheckpointManager
from isli_core.config import get_settings
from isli_core.event_manager import EventManager
from isli_core.routers.tasks import TaskOut
from isli_core.fallback import FallbackManager
from isli_core.dynamic_config import get_setting

logger = structlog.get_logger()

DEFAULT_HEARTBEAT_STALE_MINUTES = 10


class CheckpointRecoveryWorker:
    """Poll for stalled tasks and recover them from checkpoints."""

    @staticmethod
    async def run_once(session: AsyncSession, stale_minutes: int = DEFAULT_HEARTBEAT_STALE_MINUTES) -> list[dict[str, Any]]:
        """Find doing tasks with stale heartbeats or expired leases and recover or fail them."""
        settings = get_settings()
        now = datetime.now(timezone.utc)
        heartbeat_cutoff = now - timedelta(minutes=stale_minutes)
        lease_minutes = await get_setting(session, "task_lease_minutes", scope="general", default=settings.task_lease_minutes)
        max_retries = await get_setting(session, "default_max_retries", scope="general", default=3)
        
        # 1. Tasks with stale heartbeats
        stale_stmt = select(Task, Agent).join(Agent, Task.agent_id == Agent.id).where(
            Task.status == "doing",
            Agent.heartbeat_at < heartbeat_cutoff,
            Agent.deleted_at.is_(None),
            Task.deleted_at.is_(None),
        )
        
        # 2. Tasks with expired leases (Anti-Zombie)
        lease_expired_stmt = select(Task, Agent).join(Agent, Task.agent_id == Agent.id).where(
            Task.status == "doing",
            Task.updated_at < (now - timedelta(minutes=lease_minutes)) if lease_minutes > 0 else False,
            Agent.deleted_at.is_(None),
            Task.deleted_at.is_(None),
        )

        # 3. Tasks assigned to deleted agents
        deleted_agent_stmt = select(Task, Agent).join(Agent, Task.agent_id == Agent.id).where(
            Task.status == "doing",
            Agent.deleted_at.is_not(None),
            Task.deleted_at.is_(None),
        )
        
        # Combine results (duplicates handled by dict)
        rows_map = {}
        for stmt in [stale_stmt, lease_expired_stmt, deleted_agent_stmt]:
            result = await session.execute(stmt)
            for task, agent in result.all():
                rows_map[task.id] = (task, agent)

        recovered: list[dict[str, Any]] = []

        # Mark stale agents as offline and trigger fallback reassignment
        stale_agent_ids = {agent.id for _, (task, agent) in rows_map.items() if agent.deleted_at is None}
        for agent_id in stale_agent_ids:
            agent = next(agent for _, (task, agent) in rows_map.items() if agent.id == agent_id)
            if agent.status != "offline":
                agent.status = "offline"
                await session.flush()
                logger.warning("checkpoint.agent_offline", agent_id=agent_id)
                await EventManager.emit("agent:offline", {
                    "agent_id": agent_id,
                    "status": "offline",
                    "heartbeat_at": agent.heartbeat_at.isoformat() if agent.heartbeat_at else None,
                })
            await FallbackManager.reassign_tasks(session, agent_id)

        for task_id, (task, agent) in rows_map.items():
            # 0. Handle Deleted Agent (E-Stop/Reassign)
            if agent.deleted_at is not None:
                logger.warning("checkpoint.agent_deleted", task_id=task.id, agent_id=agent.id)
                old_status = task.status
                if task.session_id:
                    task.status = "failed"
                    task.blocked_reason = "Agent was deleted during task execution. Persona context lost."
                else:
                    task.status = "inbox"
                    task.agent_id = None
                    task.blocked_reason = "Agent was deleted; task returned to inbox for reassignment."
                
                task.updated_at = now
                await session.flush()
                await EventManager.emit("task:moved", {
                    "task_id": task.id,
                    "from": old_status,
                    "to": task.status,
                    "task": TaskOut.model_validate(task).model_dump(mode="json")
                })
                continue

            # 1. Apply Hard Retry E-Stop
            if task.retry_count >= max_retries:
                logger.error("checkpoint.e_stop", task_id=task.id, retries=task.retry_count, max_retries=max_retries)
                task.status = "failed"
                task.blocked_reason = f"Max retries ({max_retries}) exceeded. Poison Pill detected."
                task.updated_at = now
                await session.flush()

                await EventManager.emit("task:moved", {
                    "task_id": task.id,
                    "from": "doing",
                    "to": "failed",
                    "task": TaskOut.model_validate(task).model_dump(mode="json")
                })
                await EventManager.emit("system:alert", {
                    "severity": "critical",
                    "message": f"Task {task.id} E-Stopped after {max_retries} retries (Poison Pill).",
                    "task_id": task.id,
                    "agent_id": task.agent_id,
                    "category": "agent_crash",
                })
                continue

            cp = await CheckpointManager.load_latest(session, task.id)
            turn_number = cp.turn_number if cp else 0

            task.status = "inbox"
            task.blocked_reason = f"Recovered from checkpoint turn {turn_number}"
            task.retry_count = task.retry_count + 1
            task.updated_at = now
            await session.flush()

            if cp:
                cp.recovered_at = now
                cp.recovery_turn_number = turn_number
                await session.flush()

            logger.warning(
                "checkpoint.recovered",
                task_id=task.id,
                agent_id=agent.id,
                turn_number=turn_number,
            )
            
            await EventManager.emit("task:moved", {
                "task_id": task.id,
                "from": "doing",
                "to": "inbox",
                "task": TaskOut.model_validate(task).model_dump(mode="json")
            })
            
            recovered.append({
                "task_id": task.id,
                "agent_id": agent.id,
                "turn_number": turn_number,
                "previous_status": "doing",
            })

        return recovered
