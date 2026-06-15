import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.event_manager import EventManager
from isli_core.memory.context_cache import ContextCache
from isli_core.models import Agent, EpisodicMemory, Session, Task


class GDPRManager:
    RETENTION_DAYS = 30

    @staticmethod
    async def soft_delete_agent(session: AsyncSession, agent_id: str) -> None:
        now = datetime.now(UTC)
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
        await session.commit()

        # Remove the deleted agent from every other agent's delegation map
        result = await session.execute(select(Agent).where(Agent.deleted_at.is_(None)))
        changed_agents: list[Agent] = []
        for agent in result.scalars().all():
            peer_ids = agent.known_agent_ids or []
            if isinstance(peer_ids, str):
                peer_ids = json.loads(peer_ids)
            if agent_id in peer_ids:
                agent.known_agent_ids = [pid for pid in peer_ids if pid != agent_id]
                agent.updated_at = now
                changed_agents.append(agent)
        await session.commit()

        for agent in changed_agents:
            await EventManager.emit(
                "agent:config_updated",
                {"agent_id": agent.id, "fields": ["known_agent_ids"]},
            )
            await ContextCache.invalidate_for_agent(agent.id)

    @staticmethod
    async def soft_delete_user(session: AsyncSession, user_id: str) -> None:
        now = datetime.now(UTC)
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
        cutoff = datetime.now(UTC) - timedelta(days=GDPRManager.RETENTION_DAYS)
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
