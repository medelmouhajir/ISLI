import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Task

logger = structlog.get_logger()

MAX_RETRY_COUNT = 3
FAILED_STATUS = "failed"


class DeadLetterQueue:
    """Failed tasks land in a 'failed' status with retry count. Human can retry."""

    @staticmethod
    async def fail_task(
        session: AsyncSession, task_id: str, reason: str, max_retry_count: int | None = None
    ) -> Task | None:
        if max_retry_count is None:
            max_retry_count = MAX_RETRY_COUNT
        result = await session.execute(
            select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
        )
        task = result.scalar_one_or_none()
        if task is None:
            return None

        task.retry_count += 1
        if task.retry_count >= max_retry_count:
            task.status = FAILED_STATUS
            task.blocked_reason = reason
            logger.warning("dlq.max_retries_reached", task_id=task_id, reason=reason, max_retry_count=max_retry_count)
        else:
            task.status = "inbox"
            task.blocked_reason = f"Attempt {task.retry_count} failed: {reason}"
            logger.info("dlq.retried", task_id=task_id, retry_count=task.retry_count)

        await session.flush()
        return task

    @staticmethod
    async def human_retry(session: AsyncSession, task_id: str) -> Task | None:
        result = await session.execute(
            select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
        )
        task = result.scalar_one_or_none()
        if task is None or task.status != FAILED_STATUS:
            return None
        task.status = "inbox"
        task.retry_count = 0
        task.blocked_reason = None
        await session.flush()
        logger.info("dlq.human_retry", task_id=task_id)
        return task

    @staticmethod
    async def list_failed(session: AsyncSession, limit: int = 50) -> list[Task]:
        result = await session.execute(
            select(Task)
            .where(Task.status == FAILED_STATUS, Task.deleted_at.is_(None))
            .order_by(Task.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
