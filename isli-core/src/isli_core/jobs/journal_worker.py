import asyncio
import structlog
from datetime import datetime, timezone
from sqlalchemy import select, update
from isli_core.db import engine
from isli_core.models import Session, Task
from isli_core.memory.keeper_client import KeeperClient

logger = structlog.get_logger()

class JournalWorker:
    """Background job to update session journals incrementally after task completion."""
    
    @staticmethod
    async def run_once():
        from sqlalchemy.ext.asyncio import AsyncSession
        async with AsyncSession(engine) as session:
            # 1. Find sessions that had a task completed since the last journal update
            # We look for tasks where status='done' and task.completed_at > session.journal_updated_at (or journal is null)
            stmt = (
                select(Session, Task)
                .join(Task, Task.session_id == Session.id)
                .where(
                    Task.status == "done",
                    Task.deleted_at.is_(None),
                    Session.deleted_at.is_(None),
                    (Session.journal_updated_at.is_(None)) | (Task.completed_at > Session.journal_updated_at)
                )
                .with_for_update(of=Session, skip_locked=True)
                .limit(10)
            )
            
            result = await session.execute(stmt)
            rows = result.all()
            
            processed_sessions = set()
            
            for sess, task in rows:
                if sess.id in processed_sessions:
                    continue
                
                logger.info("journal_worker.processing", session_id=sess.id, trigger_task_id=task.id)
                
                # Use the last 10 messages for context during journal update
                recent_messages = sess.messages[-10:] if sess.messages else []
                
                new_journal = await KeeperClient.update_journal(
                    sess.id,
                    sess.journal,
                    recent_messages
                )
                
                if new_journal:
                    sess.journal = new_journal
                    sess.journal_updated_at = datetime.now(timezone.utc)
                    
                    # Truncate message buffer to last 10 raw messages
                    if len(sess.messages) > 10:
                        sess.messages = sess.messages[-10:]
                    
                    await session.commit()
                    processed_sessions.add(sess.id)
                    logger.info("journal_worker.success", session_id=sess.id)

    @staticmethod
    async def loop(interval: float = 10.0):
        logger.info("journal_worker.started", interval=interval)
        while True:
            try:
                await JournalWorker.run_once()
            except Exception as exc:
                logger.error("journal_worker.error", error=str(exc))
            await asyncio.sleep(interval)
