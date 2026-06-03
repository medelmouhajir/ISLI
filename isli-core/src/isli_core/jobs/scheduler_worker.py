import asyncio
from datetime import datetime, timezone

import structlog
from croniter import croniter
from sqlalchemy import select

from isli_core import db
from isli_core.event_manager import EventManager
from isli_core.models import Task

logger = structlog.get_logger()

SCHEDULER_INTERVAL = 10.0  # Poll every 10 seconds


class SchedulerWorker:
    """Background job that wakes up tasks when their scheduled time arrives.

    For one-time tasks: Transitions from 'pending' to 'pending_context'/'inbox'.
    For recurring (cron) tasks: Clones the task and reschedules the parent.
    """

    @staticmethod
    async def run_once():
        if db.async_session is None:
            return

        async with db.async_session() as session:
            now = datetime.now(timezone.utc)

            # Find tasks that are 'pending' and their scheduled time has passed
            # For recurring tasks, we also check last_triggered_at for idempotency
            stmt = select(Task).where(
                Task.status == "pending",
                Task.scheduled_at <= now,
                Task.deleted_at.is_(None),
            ).with_for_update(skip_locked=True).limit(50)

            result = await session.execute(stmt)
            tasks = result.scalars().all()

            for task in tasks:
                try:
                    if task.cron_expression:
                        # Idempotency guard: don't trigger if already triggered for this scheduled_at
                        if task.last_triggered_at and task.last_triggered_at >= task.scheduled_at:
                            logger.warning("scheduler.skip_duplicate", task_id=task.id)
                            continue

                        await SchedulerWorker._handle_recurring(session, task, now)
                    else:
                        await SchedulerWorker._handle_one_time(session, task, now)
                except Exception as exc:
                    logger.error("scheduler.task_processing_error", task_id=task.id, error=str(exc))
                    await session.rollback()

    @staticmethod
    async def _handle_one_time(session, task, now):
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
                "changes": {"status": new_status},
                "task": TaskOut.model_validate(task).model_dump(mode="json"),
            },
        )

    @staticmethod
    async def _handle_recurring(session, task, now):
        # Transactional all-or-nothing
        # We use session.begin_nested() if we want to catch errors per task
        # or just session.commit() at the end. 
        # Since we are in a loop, we should probably use a sub-transaction or just be careful.
        # Actually, db.begin() from the plan is for a fresh transaction.
        
        it = croniter(task.cron_expression, now)
        next_run = it.get_next(datetime)
        
        new_status = "pending_context" if task.agent_id else "inbox"
        
        # 1. Clone the task
        cloned_task = Task(
            title=task.title,
            description=task.description,
            type=task.type,
            status=new_status,
            priority=task.priority,
            agent_id=task.agent_id,
            created_by=task.created_by,
            input=task.input,
            channel=task.channel,
            session_id=task.session_id,
            payload=task.payload,
            parent_task_id=task.id, # Link to recurring parent
            depth=task.depth,
            tags=task.tags,
            # Don't copy cron_expression or scheduled_at to the clone
        )
        session.add(cloned_task)
        
        # 2. Update the parent
        task.last_triggered_at = now
        task.scheduled_at = next_run
        task.updated_at = now
        
        await session.commit()
        
        logger.info(
            "scheduler.recurring_triggered",
            parent_id=task.id,
            clone_id=cloned_task.id,
            next_run=next_run,
        )

        # Notify UI about both
        from isli_core.routers.tasks import TaskOut
        await EventManager.emit(
            "task:created",
            {"task": TaskOut.model_validate(cloned_task).model_dump(mode="json")}
        )
        await EventManager.emit(
            "task:updated",
            {
                "task_id": task.id,
                "changes": {
                    "last_triggered_at": task.last_triggered_at.isoformat(),
                    "scheduled_at": task.scheduled_at.isoformat(),
                },
                "task": TaskOut.model_validate(task).model_dump(mode="json"),
            },
        )

    @staticmethod
    async def loop():
        logger.info("scheduler.loop_started", interval=SCHEDULER_INTERVAL)
        while True:
            try:
                await SchedulerWorker.run_once()
            except Exception as exc:
                logger.error("scheduler.error", error=str(exc))
            await asyncio.sleep(SCHEDULER_INTERVAL)
