"""Build per-task transparency reports linking checkpoints, costs, and audit trail."""

import structlog
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import CheckPoint, CostLedger, AuditLog, Task
from isli_core.cost.dashboard import CostDashboard

logger = structlog.get_logger()


class TransparencyService:
    """Return a detailed report of which model was used, why, and what it cost."""

    @staticmethod
    async def build_report(session: AsyncSession, task_id: str) -> dict[str, Any] | None:
        task_result = await session.execute(
            select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
        )
        task = task_result.scalar_one_or_none()
        if task is None:
            return None

        # Turn-level attribution from checkpoints + cost ledger
        turns: list[dict[str, Any]] = []
        cp_result = await session.execute(
            select(CheckPoint).where(CheckPoint.task_id == task_id).order_by(CheckPoint.turn_number.asc())
        )
        checkpoints = list(cp_result.scalars().all())

        for cp in checkpoints:
            cost_result = await session.execute(
                select(CostLedger).where(
                    CostLedger.task_id == task_id,
                    CostLedger.created_at >= cp.created_at,
                ).order_by(CostLedger.created_at.asc()).limit(1)
            )
            cost = cost_result.scalar_one_or_none()
            turns.append({
                "turn_number": cp.turn_number,
                "checkpoint_id": cp.id,
                "input_tokens": cost.input_tokens if cost else 0,
                "output_tokens": cost.output_tokens if cost else 0,
                "cost_usd": round(cost.cost_usd, 6) if cost else 0.0,
                "model_id": cost.model_id if cost else None,
                "tier": cost.tier if cost else "unknown",
            })

        # Total cost
        total_cost = 0.0
        if task.agent_id:
            summary = await CostDashboard.agent_summary(session, task.agent_id, days=30)
            total_cost = summary["cost_usd"]

        # Recent audit entries for this task
        audit_result = await session.execute(
            select(AuditLog).where(
                AuditLog.target_id == task_id,
            ).order_by(AuditLog.created_at.desc()).limit(10)
        )
        audit_entries = [
            {
                "action": a.action,
                "actor_id": a.actor_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "chain_hash": a.chain_hash,
            }
            for a in audit_result.scalars().all()
        ]

        return {
            "task_id": task_id,
            "agent_id": task.agent_id,
            "model_id": task.agent_id,  # Placeholder; resolved from agent config in full impl
            "selection_reason": None,
            "total_cost_usd": round(total_cost, 4),
            "turns": turns,
            "audit_entries": audit_entries,
        }
