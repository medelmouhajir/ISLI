import structlog
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import EpisodicMemory
from isli_core.memory.validation import MemoryValidator

logger = structlog.get_logger()

DEFAULT_DEDUP_THRESHOLD = 0.95


class SemanticDeduplicator:
    """Pre-write similarity check to avoid duplicate episodic memories."""

    @staticmethod
    async def is_duplicate(
        session: AsyncSession,
        agent_id: str,
        new_embedding: list[float],
        threshold: float | None = None,
    ) -> bool:
        threshold = threshold or DEFAULT_DEDUP_THRESHOLD
        result = await session.execute(
            select(EpisodicMemory).where(
                EpisodicMemory.agent_id == agent_id,
                EpisodicMemory.deleted_at.is_(None),
            )
        )
        memories = result.scalars().all()
        for mem in memories:
            if mem.embedding is None:
                continue
            try:
                sim = MemoryValidator.cosine_similarity(new_embedding, mem.embedding)
                if sim >= threshold:
                    logger.info(
                        "dedup.duplicate_found",
                        agent_id=agent_id,
                        existing_id=mem.id,
                        similarity=sim,
                    )
                    return True
            except ValueError:
                continue
        return False

    @staticmethod
    async def find_similar(
        session: AsyncSession,
        agent_id: str,
        embedding: list[float],
        top_k: int = 5,
        threshold: float | None = None,
    ) -> list[tuple[EpisodicMemory, float]]:
        threshold = threshold or 0.80
        result = await session.execute(
            select(EpisodicMemory).where(
                EpisodicMemory.agent_id == agent_id,
                EpisodicMemory.deleted_at.is_(None),
            )
        )
        memories = result.scalars().all()
        scored: list[tuple[EpisodicMemory, float]] = []
        for mem in memories:
            if mem.embedding is None:
                continue
            try:
                sim = MemoryValidator.cosine_similarity(embedding, mem.embedding)
                if sim >= threshold:
                    scored.append((mem, sim))
            except ValueError:
                continue
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
