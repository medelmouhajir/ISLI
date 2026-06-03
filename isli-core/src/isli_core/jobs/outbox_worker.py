import asyncio
import structlog
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable
from sqlalchemy import select, update
from isli_core.db import get_db_session_manual
from isli_core.models import Outbox

logger = structlog.get_logger()

MAX_OUTBOX_RETRIES = 3
OUTBOX_POLL_INTERVAL = 5.0

# Registry mapping topic names to handler coroutines.
# Handlers receive (topic: str, payload: dict, headers: dict) and should raise on failure.
_outbox_handlers: dict[str, Callable[[str, dict[str, Any], dict[str, Any]], Awaitable[None]]] = {}


def register_outbox_handler(
    topic: str, handler: Callable[[str, dict[str, Any], dict[str, Any]], Awaitable[None]]
):
    """Register a handler for a specific outbox topic."""
    _outbox_handlers[topic] = handler
    logger.info("outbox.handler_registered", topic=topic)


class OutboxWorker:
    """Background job that polls the Outbox table and processes pending messages.

    Supports retry with exponential backoff and dead-lettering after max retries.
    """

    @staticmethod
    async def run_once():
        async with get_db_session_manual() as session:
            # 1. Promote retryable failed messages back to pending
            failed_stmt = (
                select(Outbox)
                .where(
                    Outbox.status == "failed",
                    Outbox.retry_count < MAX_OUTBOX_RETRIES,
                )
                .order_by(Outbox.created_at.asc())
                .limit(50)
            )
            failed_result = await session.execute(failed_stmt)
            for item in failed_result.scalars().all():
                item.status = "pending"
                item.retry_count += 1
                logger.info("outbox.retry_queued", outbox_id=item.id, topic=item.topic, retry=item.retry_count)
            await session.commit()

            # 2. Process pending messages
            pending_stmt = (
                select(Outbox)
                .where(Outbox.status == "pending")
                .order_by(Outbox.created_at.asc())
                .limit(50)
            )
            pending_result = await session.execute(pending_stmt)
            messages = list(pending_result.scalars().all())

            for msg in messages:
                handler = _outbox_handlers.get(msg.topic)
                if not handler:
                    logger.warning(
                        "outbox.no_handler",
                        outbox_id=msg.id,
                        topic=msg.topic,
                    )
                    await session.execute(
                        update(Outbox)
                        .where(Outbox.id == msg.id)
                        .values(
                            status="failed",
                            error=f"No handler registered for topic: {msg.topic}",
                            retry_count=Outbox.retry_count + 1,
                        )
                    )
                    await session.commit()
                    continue

                try:
                    await handler(msg.topic, msg.payload, msg.headers or {})
                    await session.execute(
                        update(Outbox)
                        .where(Outbox.id == msg.id)
                        .values(
                            status="done",
                            processed_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()
                    logger.info("outbox.processed", outbox_id=msg.id, topic=msg.topic)
                except Exception as exc:
                    error_str = str(exc)
                    tb = traceback.format_exc()
                    logger.error(
                        "outbox.handler_failed",
                        outbox_id=msg.id,
                        topic=msg.topic,
                        error=error_str,
                        traceback=tb,
                    )
                    await session.execute(
                        update(Outbox)
                        .where(Outbox.id == msg.id)
                        .values(
                            status="failed",
                            error=error_str,
                            retry_count=Outbox.retry_count + 1,
                        )
                    )
                    await session.commit()

    @staticmethod
    async def loop(interval: float = OUTBOX_POLL_INTERVAL):
        logger.info("outbox_worker.started", interval=interval)
        while True:
            try:
                await OutboxWorker.run_once()
            except Exception as exc:
                logger.error("outbox_worker.error", error=str(exc))
            await asyncio.sleep(interval)
