import structlog
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import CheckPoint

logger = structlog.get_logger()


class CheckpointManager:
    """Serialize agent turn state to PostgreSQL before each tool call."""

    @staticmethod
    async def save(
        session: AsyncSession,
        task_id: str,
        turn_number: int,
        messages: list[dict[str, Any]],
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> CheckPoint:
        cp = CheckPoint(
            task_id=task_id,
            turn_number=turn_number,
            messages=messages,
            tool_calls=tool_calls,
        )
        session.add(cp)
        await session.flush()
        logger.info("checkpoint.saved", task_id=task_id, turn_number=turn_number)
        return cp

    @staticmethod
    async def load_latest(session: AsyncSession, task_id: str) -> CheckPoint | None:
        from sqlalchemy import select

        result = await session.execute(
            select(CheckPoint)
            .where(CheckPoint.task_id == task_id)
            .order_by(CheckPoint.turn_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def load_all(session: AsyncSession, task_id: str) -> list[CheckPoint]:
        from sqlalchemy import select

        result = await session.execute(
            select(CheckPoint)
            .where(CheckPoint.task_id == task_id)
            .order_by(CheckPoint.turn_number.asc())
        )
        return list(result.scalars().all())
