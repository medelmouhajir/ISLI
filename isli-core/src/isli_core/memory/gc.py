import math
import structlog
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import EpisodicMemory

logger = structlog.get_logger()

DEFAULT_HALF_LIFE_DAYS = 30
DEFAULT_GC_CUTOFF_IMPORTANCE = 0.1


class MemoryGC:
    """Exponential decay + scheduled physical deletion of old memories."""

    @staticmethod
    def decayed_importance(
        base_importance: float,
        created_at: datetime,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    ) -> float:
        now = datetime.now(timezone.utc)
        age_days = (now - created_at).total_seconds() / 86400.0
        decay = math.exp(-0.693 * age_days / half_life_days)
        return base_importance * decay

    @staticmethod
    async def run_gc(
        session: AsyncSession,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
        cutoff_importance: float = DEFAULT_GC_CUTOFF_IMPORTANCE,
    ) -> int:
        result = await session.execute(
            select(EpisodicMemory).where(EpisodicMemory.deleted_at.is_(None))
        )
        memories = result.scalars().all()
        deleted = 0
        for mem in memories:
            current = MemoryGC.decayed_importance(
                mem.importance, mem.created_at, half_life_days
            )
            if current < cutoff_importance:
                await session.delete(mem)
                deleted += 1
                logger.info(
                    "gc.deleted",
                    memory_id=mem.id,
                    original_importance=mem.importance,
                    decayed_importance=current,
                )
        await session.flush()
        logger.info("gc.complete", deleted=deleted, scanned=len(memories))
        return deleted

    @staticmethod
    async def purge_deleted(session: AsyncSession, retention_days: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await session.execute(
            delete(EpisodicMemory).where(EpisodicMemory.deleted_at < cutoff)
        )
        await session.flush()
        logger.info("gc.purged", count=result.rowcount, cutoff=cutoff.isoformat())
        return result.rowcount
