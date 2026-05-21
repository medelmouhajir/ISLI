import asyncio
import structlog
from datetime import datetime, timezone
from sqlalchemy import select
from isli_core import db
from isli_core.models import Task
from isli_core.event_manager import EventManager

logger = structlog.get_logger()

SCHEDULER_INTERVAL = 10.0  # Poll every 10 seconds


class SchedulerWorker:
    """Background job that wakes up tasks when their scheduled time arrives.

    Transitions tasks from 'pending' to 'pending_context' (if agent assigned)
    or 'inbox' (if no agent).
    """

    @staticmethod
    async def run_once():
        if db.async_session is None:
            return

        async with db.async_session() as session:
            now = datetime.now(timezone.utc)

            # Find tasks that are 'pending' and their scheduled time has passed
            stmt = select(Task).where(
                Task.status == "pending",
                Task.scheduled_at <= now,
                Task.deleted_at.is_(None),
            ).with_for_update(skip_locked=True).limit(50)

            result = await session.execute(stmt)
            tasks = result.scalars().all()

            for task in tasks:
                old_status = task.status
                new_status = "pending_context" if task.agent_id else "inbox"
                
                logger.info(
                    "scheduler.activating_task",
                    task_id=task.id,
                    scheduled_at=task.scheduled_at,
                    new_status=new_status,
                )

                task.status = new_status
                task.updated_at = now
                await session.commit()

                # Notify UI via WebSocket
                from isli_core.routers.tasks import TaskOut
                await EventManager.emit(
                    "task:updated",
                    {
                        "task_id": task.id,
                        "changes": {
                            "status": new_status,
                        },
                        "task": TaskOut.model_validate(task).model_dump(mode="json"),
                    },
                )
                logger.info("scheduler.success", task_id=task.id)

    @staticmethod
    async def loop():
        logger.info("scheduler.loop_started", interval=SCHEDULER_INTERVAL)
        while True:
            try:
                await SchedulerWorker.run_once()
            except Exception as exc:
                logger.error("scheduler.error", error=str(exc))
            await asyncio.sleep(SCHEDULER_INTERVAL)
