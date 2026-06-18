"""Session lifecycle: expiration, compaction, idle detection."""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Session, Task

logger = structlog.get_logger()

DEFAULT_IDLE_TIMEOUT_MINUTES = 30


class SessionLifecycleManager:
    """Manage session expiration, compaction, and idle detection."""

    @staticmethod
    async def expire_sessions(session: AsyncSession, cutoff: datetime | None = None) -> int:
        """Soft-delete sessions whose expires_at has passed, unless they have active tasks."""
        now = cutoff or datetime.now(UTC)
        from sqlalchemy import exists

        active_task_exists = exists().where(
            Task.session_id == Session.id,
            Task.status.in_(["doing", "review"]),
            Task.deleted_at.is_(None)
        )

        result = await session.execute(
            select(Session).where(
                Session.expires_at < now,
                Session.deleted_at.is_(None),
                ~active_task_exists
            )
        )
        expired = list(result.scalars().all())
        count = 0
        for sess in expired:
            sess.deleted_at = now
            count += 1
        if count > 0:
            await session.flush()
            logger.info("session.expired", count=count)
        return count

    @staticmethod
    async def compact_sessions(
        session: AsyncSession,
        token_threshold: int = 4096,
        turn_threshold: int = 20,
    ) -> int:
        """Summarize and truncate old messages in large sessions.

        NOTE: This is deprecated. JournalWorker already truncates raw
        messages to last 10, making this compaction redundant. Kept for
        API compatibility but returns 0 immediately.
        """
        logger.debug("session.compaction_skipped", reason="deprecated_by_journal_worker")
        return 0

    @staticmethod
    async def detect_idle(
        session: AsyncSession,
        idle_timeout_minutes: int | None = None,
    ) -> int:
        if idle_timeout_minutes is None:
            idle_timeout_minutes = DEFAULT_IDLE_TIMEOUT_MINUTES
        """Soft-delete sessions idle longer than the threshold, unless they have active tasks."""
        cutoff = datetime.now(UTC) - timedelta(minutes=idle_timeout_minutes)
        from sqlalchemy import exists

        active_task_exists = exists().where(
            Task.session_id == Session.id,
            Task.status.in_(["doing", "review"]),
            Task.deleted_at.is_(None)
        )

        result = await session.execute(
            select(Session).where(
                Session.last_activity_at < cutoff,
                Session.deleted_at.is_(None),
                Session.status != "closed",
                Session.room_id.is_(None),  # Council room sessions follow room lifecycle
                ~active_task_exists
            )
        )
        idle = list(result.scalars().all())
        count = 0
        for sess in idle:
            sess.deleted_at = datetime.now(UTC)
            count += 1
        if count > 0:
            await session.flush()
            logger.info("session.idle_closed", count=count)
        return count
