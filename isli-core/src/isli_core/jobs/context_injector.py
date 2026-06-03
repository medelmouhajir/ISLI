import asyncio
import structlog
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from isli_core.db import async_session
from isli_core.models import Task, Agent
from isli_core.memory.keeper_client import KeeperClient
from isli_core.event_manager import EventManager
from isli_core.routers.tasks import TaskOut
from isli_core.cost.complexity import TaskComplexityScorer, filter_models_by_tier

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
            # Join with Agent to get identity metadata + routing config.
            stmt = (
                select(Task, Agent.name, Agent.description, Agent.config,
                       Agent.model_routing_enabled, Agent.secondary_models,
                       Agent.model_provider, Agent.model_id)
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
                agent_config = row[3] or {}
                model_routing_enabled = row[4] or False
                secondary_models_raw = row[5] or []
                default_provider = row[6]
                default_model = row[7]

                task.context_inject_attempts += 1
                attempt = task.context_inject_attempts
                logger.info(
                    "context_injector.processing",
                    task_id=task.id,
                    agent_id=task.agent_id,
                    attempt=attempt,
                )

                # Heuristic complexity scoring (fast, zero-cost)
                score, tier = TaskComplexityScorer.score_task_input(
                    task.description or task.title or task.input
                )
                task.complexity_score = score
                task.complexity_tier = tier

                threshold = agent_config.get("memory_similarity_threshold", 0.4)

                # Build context injection call (always needed)
                context_future = KeeperClient.get_context_injection(
                    task.agent_id,
                    task.description or task.title,
                    session_id=task.session_id,
                    agent_name=agent_name,
                    agent_description=agent_description,
                    memory_similarity_threshold=threshold,
                )

                # Conditionally build model routing call
                routing_future = None
                if model_routing_enabled and secondary_models_raw:
                    filtered_models = filter_models_by_tier(secondary_models_raw, tier)
                    routing_future = KeeperClient.get_model_routing(
                        agent_id=task.agent_id,
                        task_description=task.description or task.title or task.input,
                        complexity_score=score,
                        complexity_tier=tier,
                        secondary_models=filtered_models,
                        default_provider=default_provider,
                        default_model=default_model,
                    )
                elif model_routing_enabled and not secondary_models_raw:
                    logger.warning(
                        "context_injector.routing_no_models",
                        agent_id=task.agent_id,
                        task_id=task.id,
                    )

                # Run calls in parallel when routing is enabled
                if routing_future is not None:
                    summary_result, routing_result = await asyncio.gather(
                        context_future,
                        routing_future,
                        return_exceptions=True,
                    )
                else:
                    summary_result = await context_future
                    routing_result = None

                # Unpack exceptions
                if isinstance(summary_result, Exception):
                    logger.error(
                        "context_injector.context_exception",
                        task_id=task.id,
                        error=str(summary_result),
                    )
                    summary = None
                else:
                    summary = summary_result

                if isinstance(routing_result, Exception):
                    logger.error(
                        "context_injector.routing_exception",
                        task_id=task.id,
                        error=str(routing_result),
                    )
                    routing = None
                else:
                    routing = routing_result

                if summary:
                    task.context_summary = summary
                    task.status = "inbox"
                    task.context_inject_attempts = 0
                    task.context_inject_failed_at = None
                    task.updated_at = datetime.now(timezone.utc)

                    # Store routed model if routing succeeded
                    if routing and isinstance(routing, dict):
                        task.routed_model_provider = routing.get("provider")
                        task.routed_model_id = routing.get("model_id")
                        task.routed_model_reason = routing.get("reason")

                    await session.commit()

                    # Notify UI via WebSocket
                    task_out = TaskOut.model_validate(task).model_dump(mode="json")
                    await EventManager.emit(
                        "task:updated",
                        {
                            "task_id": task.id,
                            "changes": {
                                "context_summary": summary,
                                "status": "inbox",
                            },
                            "task": task_out,
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
                        await EventManager.emit(
                            "system:alert",
                            {
                                "severity": "critical",
                                "message": f"Task {task.id} context injection failed permanently after {attempt} attempts.",
                                "task_id": task.id,
                                "agent_id": task.agent_id,
                                "category": "task_context_failed",
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
