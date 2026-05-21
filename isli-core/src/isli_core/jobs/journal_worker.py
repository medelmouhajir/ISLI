import asyncio
import structlog
from datetime import datetime, timezone
from sqlalchemy import select
from isli_core.db import get_db_session_manual
from isli_core.models import Session, Task
from isli_core.memory.keeper_client import KeeperClient

logger = structlog.get_logger()


async def update_session_journal(db_session, sess: Session, trigger: str):
    """Update journal for one session and truncate raw messages."""
    recent_messages = sess.messages[-10:] if sess.messages else []
    if not recent_messages:
        return False

    new_journal = await KeeperClient.update_journal(
        sess.id,
        sess.journal,
        recent_messages,
        agent_id=sess.agent_id,
    )

    if new_journal:
        sess.journal = new_journal
        sess.journal_updated_at = datetime.now(timezone.utc)

        if len(sess.messages) > 10:
            to_archive = sess.messages[:-10]
            sess.archived_messages = list(sess.archived_messages or []) + to_archive
            sess.messages = sess.messages[-10:]

        await db_session.commit()
        logger.info("journal_worker.success", session_id=sess.id, trigger=trigger)
        return True

    return False


class JournalWorker:
    """Background job to update session journals incrementally after task completion
    or chat activity."""

    @staticmethod
    async def run_once():
        async with get_db_session_manual() as session:
            processed_sessions = set()

            # --- 1. Task-based sessions (original flow) ---
            stmt_tasks = (
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

            result = await session.execute(stmt_tasks)
            rows = result.all()

            for sess, task in rows:
                if sess.id in processed_sessions:
                    continue
                logger.info("journal_worker.processing", session_id=sess.id, trigger="task", task_id=task.id)
                await update_session_journal(session, sess, trigger=f"task:{task.id}")
                processed_sessions.add(sess.id)

            # --- 2. Chat sessions without tasks (direct user-agent conversation) ---
            # These never produce completed tasks, so we trigger on new activity
            # since the last journal update.
            stmt_chat = (
                select(Session)
                .where(
                    Session.deleted_at.is_(None),
                    (Session.journal_updated_at.is_(None)) | (Session.last_message_at > Session.journal_updated_at),
                )
                .limit(10)
            )

            result_chat = await session.execute(stmt_chat)
            chat_sessions = result_chat.scalars().all()

            for sess in chat_sessions:
                if sess.id in processed_sessions:
                    continue
                messages = sess.messages or []
                if len(messages) < 3:
                    continue
                logger.info("journal_worker.processing", session_id=sess.id, trigger="chat")
                await update_session_journal(session, sess, trigger="chat")
                processed_sessions.add(sess.id)

    @staticmethod
    async def loop(interval: float = 10.0):
        logger.info("journal_worker.started", interval=interval)
        while True:
            try:
                await JournalWorker.run_once()
            except Exception as exc:
                logger.error("journal_worker.error", error=str(exc))
            await asyncio.sleep(interval)
