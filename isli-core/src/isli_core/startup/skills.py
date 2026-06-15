"""Skill container resurrection on Core startup.

Re-enables any SkillRegistry rows with status='active' so that skill
containers survive docker-compose restarts.
"""

import structlog
from fastapi import FastAPI

from isli_core.services.skill_manager import skill_manager

logger = structlog.get_logger()


async def initialize_skills(app: FastAPI) -> None:
    """On boot, re-enable any DB-backed skills that were active before shutdown."""
    try:
        active_skills = await skill_manager._container._get_active_skills()
    except Exception as exc:
        logger.warning("startup.skill_resurrect_fetch_failed", error=str(exc))
        return

    if not active_skills:
        logger.info("startup.no_active_skills_to_resurrect")
        return

    for skill in active_skills:
        logger.info("startup.skill_resurrect", skill_id=skill.id, status=skill.status)
        try:
            await skill_manager.enable(skill.id)
        except Exception as exc:
            logger.error("startup.skill_resurrect_failed", skill_id=skill.id, error=str(exc))

    logger.info("startup.skill_resurrect_complete", count=len(active_skills))
