from datetime import datetime, timezone, timedelta
from typing import Any
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Agent, Task, EpisodicMemory, Session, AuditLog


class GDPRManager:
    RETENTION_DAYS = 30

    @staticmethod
    async def soft_delete_agent(session: AsyncSession, agent_id: str) -> None:
        now = datetime.now(timezone.utc)
        await session.execute(
            update(Agent).where(Agent.id == agent_id).values(
                deleted_at=now,
                status="deleted",
                status_reason="GDPR deletion request",
                name="[deleted]",
                description="[deleted]",
            )
        )
        # Also soft-delete related tasks and memories
        await session.execute(
            update(Task).where(Task.agent_id == agent_id).values(deleted_at=now)
        )
        await session.execute(
            update(EpisodicMemory).where(EpisodicMemory.agent_id == agent_id).values(deleted_at=now)
        )
        await session.execute(
            update(Session).where(Session.agent_id == agent_id).values(deleted_at=now)
        )

    @staticmethod
    async def soft_delete_user(session: AsyncSession, user_id: str) -> None:
        now = datetime.now(timezone.utc)
        await session.execute(
            update(Session).where(Session.user_id == user_id).values(
                deleted_at=now, messages=[]
            )
        )
        # Tasks created by this user
        await session.execute(
            update(Task).where(Task.created_by == user_id).values(deleted_at=now)
        )

    @staticmethod
    async def purge_expired(session: AsyncSession) -> dict[str, int]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=GDPRManager.RETENTION_DAYS)
        deleted_tasks = await session.execute(
            delete(Task).where(Task.deleted_at < cutoff)
        )
        deleted_memories = await session.execute(
            delete(EpisodicMemory).where(EpisodicMemory.deleted_at < cutoff)
        )
        deleted_sessions = await session.execute(
            delete(Session).where(Session.deleted_at < cutoff)
        )
        await session.commit()
        return {
            "tasks": deleted_tasks.rowcount,
            "episodic_memories": deleted_memories.rowcount,
            "sessions": deleted_sessions.rowcount,
        }

    @staticmethod
    async def crypto_shred(session: AsyncSession, agent_id: str) -> None:
        # Overwrite PII-containing fields with deterministic tokens (simulated)
        await session.execute(
            update(Task)
            .where(Task.agent_id == agent_id)
            .values(input="[shredded]", output="[shredded]")
        )
        await session.execute(
            update(EpisodicMemory)
            .where(EpisodicMemory.agent_id == agent_id)
            .values(summary="[shredded]")
        )
