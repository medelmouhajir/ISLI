import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Agent, Task, Session

logger = structlog.get_logger()


class FallbackManager:
    """Auto-reassign tasks when primary agent goes OFFLINE."""

    @staticmethod
    async def reassign_tasks(session: AsyncSession, offline_agent_id: str) -> list[str]:
        result = await session.execute(
            select(Agent).where(Agent.id == offline_agent_id, Agent.deleted_at.is_(None))
        )
        agent = result.scalar_one_or_none()
        if agent is None or agent.fallback_agent_id is None:
            return []

        fallback_id = agent.fallback_agent_id
        # Verify fallback agent exists and is healthy
        fallback_result = await session.execute(
            select(Agent).where(Agent.id == fallback_id, Agent.deleted_at.is_(None))
        )
        fallback = fallback_result.scalar_one_or_none()
        if fallback is None or fallback.status == "offline":
            logger.warning("fallback.unavailable", fallback_id=fallback_id)
            return []

        # Reassign inbox / in_progress tasks
        task_result = await session.execute(
            select(Task).where(
                Task.agent_id == offline_agent_id,
                Task.status.in_(["inbox", "assigned", "in_progress"]),
                Task.deleted_at.is_(None),
            )
        )
        tasks = list(task_result.scalars().all())
        reassigned_ids = []
        for task in tasks:
            task.agent_id = fallback_id
            task.status = "inbox"
            reassigned_ids.append(task.id)

        await session.flush()
        logger.info(
            "fallback.reassigned",
            offline_agent=offline_agent_id,
            fallback_agent=fallback_id,
            count=len(reassigned_ids),
        )

        # Reassign ready sessions
        session_result = await session.execute(
            select(Session).where(
                Session.agent_id == offline_agent_id,
                Session.status == "ready",
                Session.deleted_at.is_(None),
            )
        )
        sessions = list(session_result.scalars().all())
        for sess in sessions:
            sess.agent_id = fallback_id

        await session.flush()
        logger.info(
            "fallback.sessions_reassigned",
            offline_agent=offline_agent_id,
            fallback_agent=fallback_id,
            count=len(sessions),
        )
        return reassigned_ids
