"""Recover orphaned tasks from their latest checkpoint."""

import structlog
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Task, Agent
from isli_core.checkpoint import CheckpointManager

logger = structlog.get_logger()

DEFAULT_HEARTBEAT_STALE_MINUTES = 10


class CheckpointRecoveryWorker:
    """Poll for stalled tasks and recover them from checkpoints."""

    @staticmethod
    async def run_once(session: AsyncSession, stale_minutes: int = DEFAULT_HEARTBEAT_STALE_MINUTES) -> list[dict[str, Any]]:
        """Find doing tasks with stale heartbeats and reset to inbox from latest checkpoint."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
        result = await session.execute(
            select(Task, Agent)
            .join(Agent, Task.agent_id == Agent.id)
            .where(
                Task.status == "doing",
                Agent.heartbeat_at < cutoff,
                Agent.deleted_at.is_(None),
                Task.deleted_at.is_(None),
            )
        )
        rows = list(result.all())
        recovered: list[dict[str, Any]] = []

        for task, agent in rows:
            cp = await CheckpointManager.load_latest(session, task.id)
            turn_number = cp.turn_number if cp else 0

            task.status = "inbox"
            task.blocked_reason = f"Recovered from checkpoint turn {turn_number}"
            task.retry_count = task.retry_count + 1
            await session.flush()

            if cp:
                cp.recovered_at = datetime.now(timezone.utc)
                cp.recovery_turn_number = turn_number
                await session.flush()

            logger.warning(
                "checkpoint.recovered",
                task_id=task.id,
                agent_id=agent.id,
                turn_number=turn_number,
                stale_minutes=stale_minutes,
            )
            recovered.append({
                "task_id": task.id,
                "agent_id": agent.id,
                "turn_number": turn_number,
                "previous_status": "doing",
            })

        return recovered
