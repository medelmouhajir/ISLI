import asyncio
from datetime import datetime, timedelta, UTC
import structlog
import httpx
from sqlalchemy import select, update, func

from isli_core.db import async_session
from isli_core.models import Task
from isli_core.config import get_settings
from isli_core.auth import create_internal_token

logger = structlog.get_logger()

class AttachmentCleanupWorker:
    @classmethod
    async def run_once(cls, session):
        settings = get_settings()
        cutoff = datetime.now(UTC) - timedelta(days=30)
        
        # Identify tasks to clean up:
        # 1. status is 'done' or 'failed' (archived in some contexts)
        # 2. updated_at is older than 30 days
        # 3. retain_attachments is False
        # 4. attachments list is NOT empty
        stmt = select(Task).where(
            Task.status.in_(["done", "failed"]),
            Task.updated_at < cutoff,
            Task.retain_attachments == False,
            func.json_array_length(Task.attachments) > 0
        )
        
        result = await session.execute(stmt)
        tasks = result.scalars().all()
        
        if not tasks:
            return
            
        logger.info("attachment_cleanup.start", count=len(tasks))
        
        token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=5)
        headers = {"X-Internal-Auth": f"Bearer {token}"}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for task in tasks:
                try:
                    # Call workspace service to delete attachment directory
                    url = f"{settings.workspace_url}/delete"
                    resp = await client.post(
                        url,
                        json={
                            "agent_id": "system", # system caller
                            "scope": "attachment",
                            "scope_id": task.id,
                            "path": "." # Delete the whole scope root
                        },
                        headers=headers
                    )
                    
                    if resp.status_code in (200, 404):
                        # Update task in DB to reflect empty attachments
                        task.attachments = []
                        task.updated_at = datetime.now(UTC)
                        logger.info("attachment_cleanup.success", task_id=task.id)
                    else:
                        logger.error("attachment_cleanup.failed", task_id=task.id, status=resp.status_code, error=resp.text)
                except Exception as exc:
                    logger.error("attachment_cleanup.error", task_id=task.id, error=str(exc))
                    
        await session.commit()

    @classmethod
    async def loop(cls):
        while True:
            try:
                if async_session:
                    async with async_session() as session:
                        await cls.run_once(session)
            except Exception as exc:
                logger.error("attachment_cleanup.loop_error", error=str(exc))
            
            # Run once every 24 hours
            await asyncio.sleep(86400)
