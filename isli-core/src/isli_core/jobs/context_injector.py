import asyncio
import structlog
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update, join
from isli_core.db import async_session
from isli_core.models import Task, Agent
from isli_core.memory.keeper_client import KeeperClient
from isli_core.event_manager import EventManager
from isli_core.routers.tasks import TaskOut

logger = structlog.get_logger()

MAX_CONTEXT_RETRIES = 3
BACKOFF_SECONDS = 30


class ContextInjectorWorker:
    """Background job to inject context into tasks asynchronously.

    Retries up to MAX_CONTEXT_RETRIES with BACKOFF_SECONDS between attempts.
    After max retries the task transitions to ``context_failed`` so it
    does not hammer Keeper forever.
    """

    @staticmethod
    async def run_once():
        async with async_session() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=BACKOFF_SECONDS)

            # Find tasks that need context injection with atomic locking.
            # Join with Agent to get identity metadata.
            stmt = (
                select(Task, Agent.name, Agent.description, Agent.persona, Agent.config)
                .join(Agent, Task.agent_id == Agent.id)
                .where(
                    Task.status == "pending_context",
                    Task.context_summary.is_(None),
                    Task.deleted_at.is_(None),
                    Agent.deleted_at.is_(None),
                    (
                        Task.context_inject_failed_at.is_(None)
                        | (Task.context_inject_failed_at < cutoff)
                    ),
                )
                .with_for_update(of=Task, skip_locked=True)
                .limit(10)
            )

            result = await session.execute(stmt)
            rows = result.all()

            for row in rows:
                task = row[0]
                agent_name = row[1]
                agent_description = row[2]
                agent_persona = row[3]
                agent_config = row[4] or {}

                task.context_inject_attempts += 1
                attempt = task.context_inject_attempts
                logger.info(
                    "context_injector.processing",
                    task_id=task.id,
                    agent_id=task.agent_id,
                    attempt=attempt,
                )
                
                threshold = agent_config.get("memory_similarity_threshold", 0.4)
                
                summary = await KeeperClient.get_context_injection(
                    task.agent_id,
                    task.description or task.title,
                    session_id=task.session_id,
                    agent_name=agent_name,
                    agent_description=agent_description,
                    agent_persona=agent_persona,
                    memory_similarity_threshold=threshold,
                )

                if summary:
                    task.context_summary = summary
                    task.status = "inbox"
                    task.context_inject_attempts = 0
                    task.context_inject_failed_at = None
                    task.updated_at = datetime.now(timezone.utc)
                    await session.commit()

                    # Notify UI via WebSocket
                    await EventManager.emit(
                        "task:updated",
                        {
                            "task_id": task.id,
                            "changes": {
                                "context_summary": summary,
                                "status": "inbox",
                            },
                            "task": TaskOut.model_validate(task).model_dump(mode="json"),
                        },
                    )
                    logger.info("context_injector.success", task_id=task.id)
                else:
                    now = datetime.now(timezone.utc)
                    task.context_inject_failed_at = now
                    if attempt >= MAX_CONTEXT_RETRIES:
                        task.status = "context_failed"
                        await session.commit()
                        await EventManager.emit(
                            "task:context_failed",
                            {
                                "task_id": task.id,
                                "attempts": attempt,
                                "task": TaskOut.model_validate(task).model_dump(mode="json"),
                            },
                        )
                        logger.error(
                            "context_injector.max_retries_exceeded",
                            task_id=task.id,
                            attempts=attempt,
                        )
                    else:
                        await session.commit()
                        logger.warning(
                            "context_injector.failed",
                            task_id=task.id,
                            attempt=attempt,
                            max_retries=MAX_CONTEXT_RETRIES,
                        )

    @staticmethod
    async def loop(interval: float = 5.0):
        logger.info("context_injector.started", interval=interval)
        while True:
            try:
                await ContextInjectorWorker.run_once()
            except Exception as exc:
                logger.error("context_injector.error", error=str(exc))
            await asyncio.sleep(interval)
