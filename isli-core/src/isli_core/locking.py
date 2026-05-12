from fastapi import HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Task


class StaleVersionError(HTTPException):
    def __init__(self):
        super().__init__(status_code=409, detail="Stale version: task was modified by another request")


async def acquire_task_lock(session: AsyncSession, task_id: str, expected_version: int) -> Task:
    result = await session.execute(
        select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.version != expected_version:
        raise StaleVersionError()
    return task


async def increment_task_version(session: AsyncSession, task_id: str, current_version: int) -> bool:
    result = await session.execute(
        update(Task)
        .where(Task.id == task_id, Task.version == current_version, Task.deleted_at.is_(None))
        .values(version=current_version + 1)
    )
    if result.rowcount == 0:
        raise StaleVersionError()
    return True
