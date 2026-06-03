"""Background cron job for session lifecycle management."""

import asyncio
import structlog

from isli_core.db import async_session
from isli_core.redis_client import get_redis
from isli_core.session_lifecycle import SessionLifecycleManager
from isli_core.dynamic_config import get_setting

logger = structlog.get_logger()

CRON_LOCK_KEY = "cron:session_lifecycle"
CRON_LOCK_TTL_SECONDS = 120
CRON_INTERVAL_SECONDS = 60


class SessionCronJob:
    """Run session expiration, compaction, and idle detection on a schedule."""

    @staticmethod
    async def run_once() -> None:
        redis = await get_redis()
        acquired = await redis.set(CRON_LOCK_KEY, "1", nx=True, ex=CRON_LOCK_TTL_SECONDS)
        if not acquired:
            return

        try:
            if async_session is None:
                logger.warning("session_cron.db_not_ready")
                return
            async with async_session() as session:
                idle_timeout = await get_setting(
                    session, "session_idle_timeout_minutes",
                    scope="general", default=30,
                )
                expired = await SessionLifecycleManager.expire_sessions(session)
                idle_closed = await SessionLifecycleManager.detect_idle(session, idle_timeout_minutes=idle_timeout)
                await session.commit()
                logger.info(
                    "session_cron.completed",
                    expired=expired,
                    idle_closed=idle_closed,
                    idle_timeout=idle_timeout,
                )
        except Exception as exc:
            logger.error("session_cron.error", error=str(exc))
        finally:
            await redis.delete(CRON_LOCK_KEY)

    @staticmethod
    async def loop() -> None:
        while True:
            await SessionCronJob.run_once()
            await asyncio.sleep(CRON_INTERVAL_SECONDS)
