"""Background worker for periodic memory garbage collection."""

import asyncio
import structlog
from datetime import datetime, timezone

from isli_core.db import async_session
from isli_core.redis_client import get_redis
from isli_core.memory.gc import MemoryGC

logger = structlog.get_logger()

CRON_LOCK_KEY = "cron:memory_gc"
CRON_LOCK_TTL_SECONDS = 3600
CRON_INTERVAL_SECONDS = 86400  # Run once every 24 hours


class MemoryGCWorker:
    """Run memory garbage collection on a schedule."""

    @staticmethod
    async def run_once() -> None:
        redis = await get_redis()
        acquired = await redis.set(CRON_LOCK_KEY, "1", nx=True, ex=CRON_LOCK_TTL_SECONDS)
        if not acquired:
            logger.debug("memory_gc.lock_not_acquired")
            return

        try:
            if async_session is None:
                logger.warning("memory_gc.db_not_ready")
                return

            async with async_session() as session:
                deleted = await MemoryGC.run_gc(session)
                purged = await MemoryGC.purge_deleted(session, retention_days=30)
                await session.commit()
                logger.info(
                    "memory_gc.completed",
                    deleted=deleted,
                    purged=purged,
                )
        except Exception as exc:
            logger.error("memory_gc.error", error=str(exc))
        finally:
            await redis.delete(CRON_LOCK_KEY)

    @staticmethod
    async def loop() -> None:
        logger.info("memory_gc.loop_started", interval_seconds=CRON_INTERVAL_SECONDS)
        while True:
            try:
                await MemoryGCWorker.run_once()
            except Exception as exc:
                logger.error("memory_gc.loop_error", error=str(exc))
            await asyncio.sleep(CRON_INTERVAL_SECONDS)
