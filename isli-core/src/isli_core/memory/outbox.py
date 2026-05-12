import asyncio
import structlog
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Outbox

logger = structlog.get_logger()


class OutboxPublisher:
    """Outbox pattern for atomic PostgreSQL + ChromaDB writes."""

    @staticmethod
    async def publish(
        session: AsyncSession, topic: str, payload: dict[str, Any], headers: dict[str, Any] | None = None
    ) -> Outbox:
        msg = Outbox(
            topic=topic,
            payload=payload,
            headers=headers or {},
            status="pending",
        )
        session.add(msg)
        await session.flush()
        logger.info("outbox.enqueued", topic=topic, outbox_id=msg.id)
        return msg

    @staticmethod
    async def mark_done(session: AsyncSession, outbox_id: str) -> None:
        await session.execute(
            update(Outbox)
            .where(Outbox.id == outbox_id)
            .values(status="done", processed_at=datetime.now(timezone.utc))
        )

    @staticmethod
    async def mark_failed(session: AsyncSession, outbox_id: str, error: str) -> None:
        await session.execute(
            update(Outbox)
            .where(Outbox.id == outbox_id)
            .values(status="failed", error=error, retry_count=Outbox.retry_count + 1)
        )

    @staticmethod
    async def poll_pending(session: AsyncSession, limit: int = 100) -> list[Outbox]:
        result = await session.execute(
            select(Outbox)
            .where(Outbox.status == "pending")
            .order_by(Outbox.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def retry_failed(session: AsyncSession, max_retries: int = 3) -> list[Outbox]:
        result = await session.execute(
            select(Outbox)
            .where(Outbox.status == "failed", Outbox.retry_count < max_retries)
            .order_by(Outbox.created_at.asc())
            .limit(100)
        )
        items = list(result.scalars().all())
        for item in items:
            item.status = "pending"
            item.retry_count += 1
        await session.flush()
        return items
