import asyncio
import os
import httpx
from datetime import datetime, timezone, timedelta
import structlog

# Configuration
CORE_API_URL = os.getenv("CORE_API_URL", "http://localhost:8000")
SKILLS_SERVICE_URL = os.getenv("SKILL_WEB_FETCH_URL", "http://localhost:8100")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "dev-admin-key")
STALE_THRESHOLD_DAYS = 30

logger = structlog.get_logger()

async def run_janitor():
    logger.info("janitor.start")
    
    headers = {"Authorization": f"Bearer {ADMIN_API_KEY}"}
    
    # 1. Fetch all skills from isli-skills
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # We need an internal token for isli-skills usually, but let's assume it accepts admin key or we bypass in dev
            # In a real setup, we'd use create_internal_token
            resp = await client.get(f"{SKILLS_SERVICE_URL}/skills", headers=headers)
            resp.raise_for_status()
            skills = resp.json().get("skills", [])
        except Exception as e:
            logger.error("janitor.fetch_skills_failed", error=str(e))
            return

    now = datetime.now(timezone.utc)
    stale_count = 0

    for skill in skills:
        name = skill.get("name")
        last_used_str = skill.get("last_used_at")
        usage_count = skill.get("usage_count", 0)
        
        is_stale = False
        reason = ""

        if not last_used_str:
            # Never used
            created_at_str = skill.get("created_at")
            if created_at_str:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if (now - created_at).days > 7:
                    is_stale = True
                    reason = "Skill never used since creation (> 7 days)"
        else:
            last_used = datetime.fromisoformat(last_used_str.replace("Z", "+00:00"))
            if (now - last_used).days > STALE_THRESHOLD_DAYS:
                is_stale = True
                reason = f"Skill unused for > {STALE_THRESHOLD_DAYS} days"

        if is_stale:
            logger.info("janitor.stale_skill_detected", name=name, reason=reason)
            stale_count += 1
            
            # 2. Create cleanup task on Kanban board
            task_payload = {
                "title": f"Skill Cleanup: {name}",
                "description": f"The skill '{name}' has been flagged for deprecation.\nReason: {reason}\nUsage Count: {usage_count}",
                "type": "cleanup",
                "priority": 4,
                "created_by": "system-janitor",
                "tags": ["hygiene", "skills"]
            }
            
            try:
                t_resp = await client.post(f"{CORE_API_URL}/v1/tasks", json=task_payload, headers=headers)
                t_resp.raise_for_status()
                logger.info("janitor.cleanup_task_created", name=name, task_id=t_resp.json().get("id"))
            except Exception as e:
                logger.error("janitor.create_task_failed", name=name, error=str(e))

    logger.info("janitor.finished", stale_detected=stale_count)

if __name__ == "__main__":
    asyncio.run(run_janitor())
