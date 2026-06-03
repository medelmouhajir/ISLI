import asyncio
import structlog
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
import httpx
from isli_core.db import async_session
from isli_core.models import Session, Agent
from isli_core.memory.keeper_client import KeeperClient
from isli_core.event_manager import EventManager
from isli_core.prompts_loader import get_prompts
from isli_core.config import get_settings
from isli_core.cost.complexity import TaskComplexityScorer, filter_models_by_tier

logger = structlog.get_logger()

MAX_CONTEXT_RETRIES = 3
BACKOFF_SECONDS = 30

_CONTEXT_FAILED_MESSAGE = (
    "Sorry, I'm having trouble processing your message right now. "
    "Please try again later."
)


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
                select(Session, Agent.name, Agent.description, Agent.config,
                       Agent.model_routing_enabled, Agent.secondary_models,
                       Agent.model_provider, Agent.model_id, Agent.user_id)
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
                agent_config = row[3] or {}
                model_routing_enabled = row[4] or False
                secondary_models_raw = row[5] or []
                default_provider = row[6]
                default_model = row[7]
                agent_user_id = row[8]

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

                # Heuristic complexity scoring
                score, tier = TaskComplexityScorer.score_task_input(last_message)
                sess.complexity_score = score
                sess.complexity_tier = tier

                # Build context injection call (always needed)
                context_future = KeeperClient.get_context_injection(
                    sess.agent_id,
                    task_desc,
                    session_id=sess.id,
                    agent_name=agent_name,
                    agent_description=agent_description,
                    memory_similarity_threshold=threshold,
                )

                # Conditionally build model routing call
                # Session lock: only route if session has not been routed before
                routing_future = None
                already_routed = bool(
                    sess.routed_model_provider or sess.routed_model_id
                )
                if model_routing_enabled and secondary_models_raw and not already_routed:
                    filtered_models = filter_models_by_tier(secondary_models_raw, tier)
                    routing_future = KeeperClient.get_model_routing(
                        agent_id=sess.agent_id,
                        task_description=last_message,
                        complexity_score=score,
                        complexity_tier=tier,
                        secondary_models=filtered_models,
                        default_provider=default_provider,
                        default_model=default_model,
                    )
                elif model_routing_enabled and already_routed:
                    logger.info(
                        "session_context_injector.routing_locked",
                        session_id=sess.id,
                        routed_model=sess.routed_model_id,
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
                        "session_context_injector.context_exception",
                        session_id=sess.id,
                        error=str(summary_result),
                    )
                    summary = None
                else:
                    summary = summary_result

                if isinstance(routing_result, Exception):
                    logger.error(
                        "session_context_injector.routing_exception",
                        session_id=sess.id,
                        error=str(routing_result),
                    )
                    routing = None
                else:
                    routing = routing_result

                if summary:
                    sess.context_summary = summary
                    sess.status = "ready"
                    sess.context_inject_attempts = 0
                    sess.context_inject_failed_at = None
                    sess.updated_at = datetime.now(timezone.utc)

                    # Store routed model if routing succeeded and not already locked
                    if routing and isinstance(routing, dict) and not already_routed:
                        sess.routed_model_provider = routing.get("provider")
                        sess.routed_model_id = routing.get("model_id")
                        sess.routed_model_reason = routing.get("reason")

                    await session.commit()

                    # Auto-create channel identity mapping for external channels
                    if sess.user_id and sess.channel and sess.channel != "web" and agent_user_id:
                        from isli_core.models import ChannelIdentity
                        from sqlalchemy.dialects.postgresql import insert as pg_insert
                        try:
                            # Upsert identity mapping (idempotent)
                            mapping_stmt = select(ChannelIdentity).where(
                                ChannelIdentity.channel == sess.channel,
                                ChannelIdentity.channel_user_id == sess.user_id,
                                ChannelIdentity.agent_id == sess.agent_id,
                            )
                            mapping_result = await session.execute(mapping_stmt)
                            existing = mapping_result.scalar_one_or_none()
                            if not existing:
                                identity = ChannelIdentity(
                                    channel=sess.channel,
                                    channel_user_id=sess.user_id,
                                    board_user_id=agent_user_id,
                                    agent_id=sess.agent_id,
                                )
                                session.add(identity)
                                await session.commit()
                                logger.info(
                                    "channel_identity.created",
                                    channel=sess.channel,
                                    channel_user_id=sess.user_id,
                                    board_user_id=agent_user_id,
                                    agent_id=sess.agent_id,
                                )
                        except Exception as exc:
                            logger.warning(
                                "channel_identity.create_failed",
                                session_id=sess.id,
                                error=str(exc),
                            )

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
                            "metadata": sess.session_metadata or {},
                            "routed_model": {
                                "provider": sess.routed_model_provider,
                                "model_id": sess.routed_model_id,
                                "reason": sess.routed_model_reason,
                            } if sess.routed_model_id else None,
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
                        await EventManager.emit(
                            "system:alert",
                            {
                                "severity": "critical",
                                "message": f"Session {sess.id} context injection failed permanently after {attempt} attempts.",
                                "session_id": sess.id,
                                "agent_id": sess.agent_id,
                                "category": "task_context_failed",
                            },
                        )
                        logger.error(
                            "session_context_injector.max_retries_exceeded",
                            session_id=sess.id,
                            attempts=attempt,
                        )
                        await SessionContextInjectorWorker._notify_user(sess)
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
    async def _notify_user(session: Session):
        """Send a proactive message to the user when context injection fails."""
        if not session.channel or session.channel == "web" or not session.user_id:
            return
        try:
            settings = get_settings()
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.channels_url}/send",
                    json={
                        "channel": session.channel,
                        "channel_user_id": session.user_id,
                        "text": _CONTEXT_FAILED_MESSAGE,
                        "agent_id": session.agent_id,
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
                logger.info(
                    "session_context_injector.user_notified",
                    session_id=session.id,
                    user_id=session.user_id,
                )
        except Exception as exc:
            logger.error(
                "session_context_injector.notify_user_failed",
                session_id=session.id,
                error=str(exc),
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
