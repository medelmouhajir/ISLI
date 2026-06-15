"""SkillUpdateWorker: periodically checks for skill updates and auto-applies them."""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
import structlog

from isli_core.config import get_settings
from isli_core.db import get_db_session_manual
from isli_core.models import SkillRegistry
from isli_core.services.skill_manager import SkillContainerManager
from isli_core.redis_client import get_redis

logger = structlog.get_logger()


class SkillUpdateWorker:
    INTERVAL = 3600       # 1 hour between loops
    MIN_RECHECK = 1800    # 30 minutes: skip skills checked more recently than this

    @staticmethod
    async def run_once():
        async with get_db_session_manual() as db:
            result = await db.execute(
                select(SkillRegistry)
                .where(SkillRegistry.update_policy == "auto")
                .where(SkillRegistry.status.in_(["active", "disabled"]))
                .where(
                    (SkillRegistry.last_checked_at == None)  # noqa: E711
                    | (SkillRegistry.last_checked_at < datetime.now(timezone.utc) - timedelta(seconds=SkillUpdateWorker.MIN_RECHECK))
                )
            )
            skills = result.scalars().all()

        scm = SkillContainerManager()
        for skill in skills:
            # Skip if a manual update/rollback is in progress
            redis = await get_redis()
            lock_key = f"skill:update:{skill.id}"
            acquired = await redis.set(lock_key, "1", nx=True, ex=600)
            if acquired is None:
                logger.info("skill_update_worker.skipped_locked", skill_id=skill.id)
                continue
            try:
                check = await scm.check_update(skill.id)
                if check.get("has_update"):
                    await scm.update(skill.id)
                    logger.info("skill_update_worker.auto_updated", skill_id=skill.id, version=skill.version)
            except Exception as exc:
                logger.error("skill_update_worker.skill_error", skill_id=skill.id, error=str(exc))
            finally:
                await redis.delete(lock_key)

    @staticmethod
    async def loop():
        logger.info("skill_update_worker.started", interval=SkillUpdateWorker.INTERVAL)
        while True:
            try:
                await SkillUpdateWorker.run_once()
            except Exception as exc:
                logger.error("skill_update_worker.error", error=str(exc))
            await asyncio.sleep(SkillUpdateWorker.INTERVAL)
