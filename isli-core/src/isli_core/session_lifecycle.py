"""Session lifecycle: expiration, compaction, idle detection."""

import structlog
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Session, Task

logger = structlog.get_logger()

DEFAULT_IDLE_TIMEOUT_MINUTES = 30
DEFAULT_COMPACTION_TURNS = 20


class SessionLifecycleManager:
    """Manage session expiration, compaction, and idle detection."""

    @staticmethod
    async def expire_sessions(session: AsyncSession, cutoff: datetime | None = None) -> int:
        """Soft-delete sessions whose expires_at has passed, unless they have active tasks."""
        now = cutoff or datetime.now(timezone.utc)
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
            sess.messages = []
            count += 1
        if count > 0:
            await session.flush()
            logger.info("session.expired", count=count)
        return count

    @staticmethod
    async def compact_sessions(
        session: AsyncSession,
        token_threshold: int = 4096,
        turn_threshold: int = DEFAULT_COMPACTION_TURNS,
    ) -> int:
        """Summarize and truncate old messages in large sessions."""
        result = await session.execute(
            select(Session).where(
                Session.token_count > token_threshold,
                Session.compacted_at.is_(None),
                Session.deleted_at.is_(None),
            )
        )
        candidates = list(result.scalars().all())
        count = 0
        for sess in candidates:
            messages = sess.messages or []
            if len(messages) > turn_threshold:
                # Keep the last turn_threshold messages; drop the rest
                sess.messages = messages[-turn_threshold:]
                sess.token_count = sum(len(str(m)) for m in sess.messages)
                sess.compacted_at = datetime.now(timezone.utc)
                count += 1
        if count > 0:
            await session.flush()
            logger.info("session.compacted", count=count)
        return count

    @staticmethod
    async def detect_idle(
        session: AsyncSession,
        idle_timeout_minutes: int = DEFAULT_IDLE_TIMEOUT_MINUTES,
    ) -> int:
        """Soft-delete sessions idle longer than the threshold, unless they have active tasks."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=idle_timeout_minutes)
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
                ~active_task_exists
            )
        )
        idle = list(result.scalars().all())
        count = 0
        for sess in idle:
            sess.deleted_at = datetime.now(timezone.utc)
            sess.messages = []
            count += 1
        if count > 0:
            await session.flush()
            logger.info("session.idle_closed", count=count)
        return count
