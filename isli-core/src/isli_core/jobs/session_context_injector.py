import asyncio
import structlog
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from isli_core.db import async_session
from isli_core.models import Session, Agent
from isli_core.memory.keeper_client import KeeperClient
from isli_core.event_manager import EventManager
from isli_core.prompts_loader import get_prompts

logger = structlog.get_logger()

MAX_CONTEXT_RETRIES = 3
BACKOFF_SECONDS = 30


class SessionContextInjectorWorker:
    """Background job to inject context into sessions asynchronously.

    When a human message arrives, the session status is set to
    ``pending_context``.  This worker polls for such sessions, calls the
    Keeper for a context summary, and emits a ``session:message`` event
    to the agent via Redis / WebSocket.

    Retries up to MAX_CONTEXT_RETRIES with BACKOFF_SECONDS between attempts.
    After max retries the session transitions to ``context_failed``.
    """

    @staticmethod
    async def run_once():
        async with async_session() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=BACKOFF_SECONDS)

            stmt = (
                select(Session, Agent.name, Agent.description, Agent.persona, Agent.config)
                .join(Agent, Session.agent_id == Agent.id)
                .where(
                    Session.status == "pending_context",
                    Session.deleted_at.is_(None),
                    Agent.deleted_at.is_(None),
                    (
                        Session.context_inject_failed_at.is_(None)
                        | (Session.context_inject_failed_at < cutoff)
                    ),
                )
                .with_for_update(of=Session, skip_locked=True)
                .limit(10)
            )

            result = await session.execute(stmt)
            rows = result.all()

            for row in rows:
                sess = row[0]
                agent_name = row[1]
                agent_description = row[2]
                agent_persona = row[3]
                agent_config = row[4] or {}

                sess.context_inject_attempts += 1
                attempt = sess.context_inject_attempts
                sess.status = "processing_context"
                await session.commit()

                logger.info(
                    "session_context_injector.processing",
                    session_id=sess.id,
                    agent_id=sess.agent_id,
                    attempt=attempt,
                )
                
                threshold = agent_config.get("memory_similarity_threshold", 0.4)

                # Build task description from session messages
                last_message = ""
                if sess.messages:
                    last_message = sess.messages[-1].get("content", "")
                task_desc = get_prompts()["core"]["context_inject_task_desc"].format(
                    user_id=sess.user_id or "user", last_message=last_message
                )

                summary = await KeeperClient.get_context_injection(
                    sess.agent_id,
                    task_desc,
                    session_id=sess.id,
                    agent_name=agent_name,
                    agent_description=agent_description,
                    agent_persona=agent_persona,
                    memory_similarity_threshold=threshold,
                )

                if summary:
                    sess.context_summary = summary
                    sess.status = "ready"
                    sess.context_inject_attempts = 0
                    sess.context_inject_failed_at = None
                    sess.updated_at = datetime.now(timezone.utc)
                    await session.commit()

                    # Emit event for agent via WebSocket
                    await EventManager.emit(
                        "session:message",
                        {
                            "session_id": sess.id,
                            "agent_id": sess.agent_id,
                            "user_id": sess.user_id,
                            "channel": sess.channel,
                            "messages": sess.messages,
                            "context_summary": summary,
                        },
                    )
                    logger.info("session_context_injector.success", session_id=sess.id)
                else:
                    now = datetime.now(timezone.utc)
                    sess.context_inject_failed_at = now
                    if attempt >= MAX_CONTEXT_RETRIES:
                        sess.status = "context_failed"
                        await session.commit()
                        await EventManager.emit(
                            "session:context_failed",
                            {
                                "session_id": sess.id,
                                "attempts": attempt,
                            },
                        )
                        logger.error(
                            "session_context_injector.max_retries_exceeded",
                            session_id=sess.id,
                            attempts=attempt,
                        )
                    else:
                        sess.status = "pending_context"
                        await session.commit()
                        logger.warning(
                            "session_context_injector.failed",
                            session_id=sess.id,
                            attempt=attempt,
                            max_retries=MAX_CONTEXT_RETRIES,
                        )

    @staticmethod
    async def loop(interval: float = 5.0):
        logger.info("session_context_injector.started", interval=interval)
        while True:
            try:
                await SessionContextInjectorWorker.run_once()
            except Exception as exc:
                logger.error("session_context_injector.error", error=str(exc))
            await asyncio.sleep(interval)
