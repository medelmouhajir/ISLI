"""Unified context injection worker.

Replaces both ``ContextInjectorWorker`` and ``SessionContextInjectorWorker``
with a single consumer reading from a Redis Stream (``context:requests``).

Features:
- Normal XREADGROUP read loop
- Periodic XPENDING/XCLAIM sweep for stuck messages
- DLQ after ``DLQ_AFTER_CLAIMS`` failed reclaim attempts
- Three-tier caching via ``ContextCache`` (assembled strings only)
- Complexity delta re-route trigger for sessions
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select

from isli_core.db import async_session
from isli_core.event_manager import EventManager
from isli_core.memory.context_cache import ContextCache
from isli_core.memory.keeper_client import KeeperClient, KeeperAuthError
from isli_core.models import Agent, Session, Task
from isli_core.redis_streams import (
    acknowledge,
    add_to_stream,
    claim_pending,
    ensure_stream_group,
    read_group,
    write_dlq,
)
from isli_core.routers.tasks import TaskOut

logger = structlog.get_logger()

STREAM_NAME = "context:requests"
GROUP_NAME = "context_workers"
DLQ_AFTER_CLAIMS = 3
CLAIM_SWEEP_INTERVAL = 10  # every N normal-read loops
COMPLEXITY_DELTA_THRESHOLD = 6  # tune from logs after a week


class ContextWorker:
    """Single worker that consumes context injection requests from a Redis Stream."""

    def __init__(self) -> None:
        self.running = True
        self._loop_counter = 0

    @staticmethod
    async def loop(
        interval: float = 0.5,
        block_ms: int = 5000,
        consumer_name: str | None = None,
    ) -> None:
        """Main worker loop (factory — instantiates ContextWorker and runs it).

        Reads from Redis Stream via consumer group, processes messages,
        and periodically sweeps pending entries for reclaim.
        """
        worker = ContextWorker()
        await worker._run(interval=interval, block_ms=block_ms, consumer_name=consumer_name)

    async def _run(
        self,
        interval: float = 0.5,
        block_ms: int = 5000,
        consumer_name: str | None = None,
    ) -> None:
        """Instance-level run loop."""
        if consumer_name is None:
            import socket

            consumer_name = f"worker-{socket.gethostname()}-{id(self)}"

        logger.info(
            "context_worker.started",
            stream=STREAM_NAME,
            group=GROUP_NAME,
            consumer=consumer_name,
        )

        while self.running:
            try:
                # 1. Normal consumer-group read
                messages = await read_group(
                    STREAM_NAME,
                    GROUP_NAME,
                    consumer_name,
                    count=10,
                    block_ms=block_ms,
                )
                for msg in messages:
                    await self._process_one(msg, consumer_name, is_reclaim=False)

                # 2. Periodic claim sweep
                self._loop_counter += 1
                if self._loop_counter % CLAIM_SWEEP_INTERVAL == 0:
                    claimed = await claim_pending(
                        STREAM_NAME,
                        GROUP_NAME,
                        consumer_name,
                        min_idle_ms=30000,
                        count=10,
                    )
                    for msg in claimed:
                        await self._process_one(
                            msg, consumer_name, is_reclaim=True
                        )
            except Exception as exc:
                logger.error("context_worker.loop_error", error=str(exc))
                await asyncio.sleep(interval)

    async def _process_one(
        self,
        msg: dict[str, Any],
        consumer_name: str,
        is_reclaim: bool = False,
    ) -> None:
        """Process a single stream message."""
        payload = msg.get("payload", {})
        message_id = msg.get("id")

        # Gracefully handle v=1 schema; tolerate missing fields
        type_ = payload.get("type")
        id_ = payload.get("id")
        agent_id = payload.get("agent_id")
        task_description = payload.get("task_description")
        session_id = payload.get("session_id")
        complexity_score = payload.get("complexity_score")
        memory_similarity_threshold = payload.get(
            "memory_similarity_threshold", 0.4
        )

        if not type_ or not id_ or not agent_id:
            logger.error(
                "context_worker.malformed_payload",
                payload=payload,
                message_id=message_id,
            )
            # Poison pill: ACK so it does not sit in PEL forever
            await acknowledge(STREAM_NAME, GROUP_NAME, message_id)
            return

        logger.info(
            "context_worker.processing",
            type=type_,
            id=id_,
            agent_id=agent_id,
            is_reclaim=is_reclaim,
            message_id=message_id,
        )

        # Resolve reclaim count from payload or default
        reclaim_count = payload.get("__reclaim_count", 0)
        if is_reclaim:
            reclaim_count += 1
            payload["__reclaim_count"] = reclaim_count

        # Cache lookup
        last_message_ids = await self._get_last_message_ids(type_, id_)
        cached = await ContextCache.get(
            agent_id,
            session_id,
            task_description,
            last_message_ids,
        )

        if cached:
            summary = cached
            logger.info("context_worker.cache_hit", type=type_, id=id_)
        else:
            logger.info("context_worker.cache_miss", type=type_, id=id_)
            try:
                summary = await self._call_keeper(
                    agent_id,
                    task_description,
                    session_id,
                    memory_similarity_threshold,
                )
            except KeeperAuthError:
                logger.error(
                    "context_worker.keeper_auth_error",
                    type=type_,
                    id=id_,
                    agent_id=agent_id,
                )
                await acknowledge(STREAM_NAME, GROUP_NAME, message_id)
                return
            if summary:
                await ContextCache.set(
                    agent_id,
                    session_id,
                    task_description,
                    last_message_ids,
                    summary,
                    ttl=30,
                )

        if summary:
            try:
                await self._on_success(
                    type_, id_, summary, payload, message_id
                )
                await acknowledge(STREAM_NAME, GROUP_NAME, message_id)
            except Exception as exc:
                logger.error(
                    "context_worker.on_success_failed",
                    type=type_,
                    id=id_,
                    error=str(exc),
                )
                # Do not ACK; let reclaim handle it
        else:
            if is_reclaim and reclaim_count >= DLQ_AFTER_CLAIMS:
                await write_dlq(
                    STREAM_NAME,
                    payload,
                    error="Max reclaim attempts exceeded without success",
                    attempts=reclaim_count,
                )
                await acknowledge(STREAM_NAME, GROUP_NAME, message_id)
                logger.error(
                    "context_worker.dlq",
                    type=type_,
                    id=id_,
                    attempts=reclaim_count,
                )
            else:
                logger.warning(
                    "context_worker.failed_no_summary",
                    type=type_,
                    id=id_,
                    reclaim_count=reclaim_count,
                )
                # Leave unacked for reclaim/retry

    async def _call_keeper(
        self,
        agent_id: str,
        task_description: str | None,
        session_id: str | None,
        memory_similarity_threshold: float,
    ) -> str | None:
        """Fetch context from Keeper.  May raise ``KeeperAuthError``."""
        # Load agent metadata for Keeper call
        async with async_session() as session:
            agent = await session.get(Agent, agent_id)
            if not agent:
                logger.warning("context_worker.agent_not_found", agent_id=agent_id)
                return None

            return await KeeperClient.get_context_injection(
                agent_id=agent_id,
                task_description=task_description,
                session_id=session_id,
                agent_name=agent.name,
                agent_description=agent.description,
                memory_similarity_threshold=memory_similarity_threshold,
                known_agent_ids=agent.config.get("known_agent_ids") if agent.config else None,
            )

    async def _on_success(
        self,
        type_: str,
        id_: str,
        summary: str,
        payload: dict[str, Any],
        message_id: str,
    ) -> None:
        """Persist result to DB and emit WebSocket event."""
        async with async_session() as session:
            if type_ == "task":
                task = await session.get(Task, id_)
                if not task:
                    logger.warning("context_worker.task_not_found", task_id=id_)
                    return

                task.context_summary = summary
                task.status = "inbox"
                task.context_inject_attempts = 0
                task.context_inject_failed_at = None
                task.updated_at = datetime.now(timezone.utc)

                # Model routing (task-level, no lock)
                complexity_score = payload.get("complexity_score")
                complexity_tier = payload.get("complexity_tier")
                secondary_models = payload.get("secondary_models", [])
                if (
                    task.agent_id
                    and complexity_score is not None
                    and secondary_models
                ):
                    routing = await KeeperClient.get_model_routing(
                        agent_id=task.agent_id,
                        task_description=task.description or task.title or task.input,
                        complexity_score=complexity_score,
                        complexity_tier=complexity_tier or "standard",
                        secondary_models=secondary_models,
                    )
                    if routing:
                        task.routed_model_provider = routing.get("provider")
                        task.routed_model_id = routing.get("model_id")
                        task.routed_model_reason = routing.get("reason")

                await session.commit()

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
                logger.info("context_worker.task_success", task_id=task.id)

            elif type_ == "session":
                sess = await session.get(Session, id_)
                if not sess:
                    logger.warning("context_worker.session_not_found", session_id=id_)
                    return

                sess.context_summary = summary
                sess.status = "ready"
                sess.context_inject_attempts = 0
                sess.context_inject_failed_at = None
                sess.updated_at = datetime.now(timezone.utc)

                # Complexity delta re-route trigger
                new_score = payload.get("complexity_score")
                if (
                    sess.routed_model_id
                    and new_score is not None
                    and sess.complexity_score is not None
                ):
                    delta = abs(new_score - sess.complexity_score)
                    if delta > COMPLEXITY_DELTA_THRESHOLD:
                        secondary_models = payload.get("secondary_models", [])
                        routing = await KeeperClient.get_model_routing(
                            agent_id=sess.agent_id,
                            task_description=payload.get("task_description", ""),
                            complexity_score=new_score,
                            complexity_tier=payload.get("complexity_tier", "standard"),
                            secondary_models=secondary_models,
                        )
                        if routing:
                            old_model = sess.routed_model_id
                            sess.routed_model_provider = routing.get("provider")
                            sess.routed_model_id = routing.get("model_id")
                            sess.routed_model_reason = routing.get("reason")
                            sess.complexity_score = new_score
                            logger.info(
                                "model.re_route_triggered",
                                session_id=sess.id,
                                delta=delta,
                                old_model=old_model,
                                new_model=routing.get("model_id"),
                            )

                await session.commit()

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
                        }
                        if sess.routed_model_id
                        else None,
                    },
                )
                logger.info("context_worker.session_success", session_id=sess.id)

    async def _get_last_message_ids(
        self,
        type_: str,
        id_: str,
    ) -> list[str]:
        """Fetch last message IDs for cache turn-hash computation."""
        try:
            async with async_session() as session:
                if type_ == "session":
                    sess = await session.get(Session, id_)
                    if sess and sess.messages:
                        return [
                            m.get("id", str(i))
                            for i, m in enumerate(sess.messages[-3:])
                        ]
                elif type_ == "task":
                    task = await session.get(Task, id_)
                    if task and task.session_id:
                        sess = await session.get(Session, task.session_id)
                        if sess and sess.messages:
                            return [
                                m.get("id", str(i))
                                for i, m in enumerate(sess.messages[-3:])
                            ]
        except Exception as exc:
            logger.warning("context_worker.message_ids_failed", error=str(exc))
        return []
