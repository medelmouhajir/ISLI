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
        lease_minutes = settings.task_lease_minutes
        
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
        
        # Combine results (duplicates handled by dict)
        rows_map = {}
        for stmt in [stale_stmt, lease_expired_stmt]:
            result = await session.execute(stmt)
            for task, agent in result.all():
                rows_map[task.id] = (task, agent)

        recovered: list[dict[str, Any]] = []

        for task_id, (task, agent) in rows_map.items():
            # Apply Hard Retry E-Stop
            if task.retry_count >= 3:
                logger.error("checkpoint.e_stop", task_id=task.id, retries=task.retry_count)
                task.status = "failed"
                task.blocked_reason = f"Max retries (3) exceeded. Poison Pill detected."
                task.updated_at = now
                await session.flush()
                
                await EventManager.emit("task:moved", {
                    "task_id": task.id,
                    "from": "doing",
                    "to": "failed",
                    "task": TaskOut.model_validate(task).model_dump(mode="json")
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
