import asyncio
import structlog
from datetime import datetime, timezone
from sqlalchemy import select, update
from isli_core.db import engine
from isli_core.models import Task
from isli_core.memory.keeper_client import KeeperClient
from isli_core.event_manager import EventManager
from isli_core.routers.tasks import TaskOut

logger = structlog.get_logger()

class ContextInjectorWorker:
    """Background job to inject context into tasks asynchronously."""
    
    @staticmethod
    async def run_once():
        from sqlalchemy.ext.asyncio import AsyncSession
        async with AsyncSession(engine) as session:
            # Find tasks that need context injection with atomic locking
            stmt = select(Task).where(
                Task.agent_id.is_not(None),
                Task.status == "pending_context",
                Task.context_summary.is_(None),
                Task.deleted_at.is_(None)
            ).with_for_update(skip_locked=True).limit(10)
            
            result = await session.execute(stmt)
            tasks = result.scalars().all()
            
            for task in tasks:
                logger.info("context_injector.processing", task_id=task.id, agent_id=task.agent_id)
                summary = await KeeperClient.get_context_injection(
                    task.agent_id, 
                    task.description or task.title,
                    session_id=task.session_id
                )
                
                if summary:
                    task.context_summary = summary
                    task.status = "inbox"
                    task.updated_at = datetime.now(timezone.utc)
                    await session.commit()
                    
                    # Notify UI via WebSocket
                    await EventManager.emit("task:updated", {
                        "task_id": task.id,
                        "changes": {"context_summary": summary, "status": "inbox"},
                        "task": TaskOut.model_validate(task).model_dump(mode="json")
                    })
                    logger.info("context_injector.success", task_id=task.id)

    @staticmethod
    async def loop(interval: float = 5.0):
        logger.info("context_injector.started", interval=interval)
        while True:
            try:
                await ContextInjectorWorker.run_once()
            except Exception as exc:
                logger.error("context_injector.error", error=str(exc))
            await asyncio.sleep(interval)
