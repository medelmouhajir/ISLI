"""Sum token usage across all child tasks; alert on threshold."""

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Task, CostLedger

logger = structlog.get_logger()


class RootTaskAccumulator:
    """Accumulate costs from a task and all its descendants."""

    @staticmethod
    async def get_descendants(session: AsyncSession, root_task_id: str) -> list[Task]:
        """BFS to collect all descendant tasks."""
        descendants: list[Task] = []
        queue = [root_task_id]
        visited = {root_task_id}

        while queue:
            current = queue.pop(0)
            result = await session.execute(
                select(Task).where(
                    Task.parent_task_id == current,
                    Task.deleted_at.is_(None),
                )
            )
            children = list(result.scalars().all())
            for child in children:
                if child.id not in visited:
                    visited.add(child.id)
                    descendants.append(child)
                    queue.append(child.id)

        return descendants

    @staticmethod
    async def total_cost(session: AsyncSession, root_task_id: str) -> dict:
        descendants = await RootTaskAccumulator.get_descendants(session, root_task_id)
        task_ids = [root_task_id] + [t.id for t in descendants]

        result = await session.execute(
            select(
                func.sum(CostLedger.input_tokens),
                func.sum(CostLedger.output_tokens),
                func.sum(CostLedger.reasoning_tokens),
                func.sum(CostLedger.cost_usd),
            ).where(CostLedger.task_id.in_(task_ids))
        )
        row = result.one_or_none()
        total = {
            "task_id": root_task_id,
            "total_tasks": len(task_ids),
            "input_tokens": int(row[0] or 0),
            "output_tokens": int(row[1] or 0),
            "reasoning_tokens": int(row[2] or 0),
            "total_cost_usd": float(row[3] or 0.0),
        }
        logger.info("accumulator.total", **total)
        return total

    @staticmethod
    async def check_budget(
        session: AsyncSession,
        root_task_id: str,
        budget_usd: float,
    ) -> bool:
        total = await RootTaskAccumulator.total_cost(session, root_task_id)
        exceeded = total["total_cost_usd"] > budget_usd
        if exceeded:
            logger.warning(
                "accumulator.budget_exceeded",
                root_task=root_task_id,
                spent=total["total_cost_usd"],
                budget=budget_usd,
            )
        return exceeded
