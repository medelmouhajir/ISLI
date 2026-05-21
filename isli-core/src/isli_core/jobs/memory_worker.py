import asyncio
import structlog
from datetime import datetime, timezone
from sqlalchemy import select
from isli_core.db import get_db_session_manual
from isli_core.models import Session, EpisodicMemory
from isli_core.memory.keeper_client import KeeperClient

logger = structlog.get_logger()

# Threshold for cosine-distance deduplication (distance < 0.08 ≈ similarity > 0.92).
COSINE_DISTANCE_THRESHOLD = 0.08


def _compute_importance(journal_text: str) -> float:
    """Heuristic importance score based on journal content."""
    text_lower = journal_text.lower()
    markers = [
        "decision", "agreed", "concluded", "resolved", "remember",
        "important", "critical", "milestone", "outcome",
    ]
    if any(m in text_lower for m in markers):
        return 0.8
    return 0.5


class MemoryWorker:
    """Background job to extract episodic memories from session journals.

    Runs after JournalWorker has compacted a session. Generates embeddings
    via Keeper, deduplicates against existing episodic memories via pgvector,
    and inserts new rows.
    """

    @staticmethod
    async def run_once():
        async with get_db_session_manual() as session:
            stmt = (
                select(Session)
                .where(
                    Session.deleted_at.is_(None),
                    Session.journal_updated_at.is_not(None),
                    (
                        Session.last_memory_extracted_at.is_(None)
                        | (Session.journal_updated_at > Session.last_memory_extracted_at)
                    ),
                )
                .limit(10)
            )

            result = await session.execute(stmt)
            sessions = result.scalars().all()

            for sess in sessions:
                journal_text = sess.journal or ""
                if not journal_text or len(journal_text.strip()) < 20:
                    sess.last_memory_extracted_at = sess.journal_updated_at
                    await session.commit()
                    logger.info(
                        "memory_worker.skipped",
                        session_id=sess.id,
                        reason="journal_too_short",
                    )
                    continue

                logger.info(
                    "memory_worker.processing",
                    session_id=sess.id,
                    agent_id=sess.agent_id,
                    journal_len=len(journal_text),
                )

                embedding = await KeeperClient.embed(journal_text)
                if not embedding:
                    logger.warning(
                        "memory_worker.embed_failed",
                        session_id=sess.id,
                        agent_id=sess.agent_id,
                    )
                    # Do not update last_memory_extracted_at so we retry later
                    continue

                # Deduplication: check for similar existing memories for this agent
                is_duplicate = False
                try:
                    dup_stmt = (
                        select(EpisodicMemory)
                        .where(
                            EpisodicMemory.agent_id == sess.agent_id,
                            EpisodicMemory.deleted_at.is_(None),
                            EpisodicMemory.embedding.cosine_distance(embedding) < COSINE_DISTANCE_THRESHOLD,
                        )
                        .limit(1)
                    )
                    dup_result = await session.execute(dup_stmt)
                    if dup_result.scalar_one_or_none():
                        is_duplicate = True
                except Exception as exc:
                    logger.warning(
                        "memory_worker.dedup_error",
                        session_id=sess.id,
                        error=str(exc),
                    )

                if is_duplicate:
                    logger.info(
                        "memory_worker.duplicate_skipped",
                        session_id=sess.id,
                        agent_id=sess.agent_id,
                    )
                    sess.last_memory_extracted_at = sess.journal_updated_at
                    await session.commit()
                    continue

                importance = _compute_importance(journal_text)
                memory = EpisodicMemory(
                    agent_id=sess.agent_id,
                    session_id=sess.id,
                    summary=journal_text,
                    embedding=embedding,
                    importance=importance,
                )
                session.add(memory)
                sess.last_memory_extracted_at = sess.journal_updated_at
                await session.commit()
                logger.info(
                    "memory_worker.success",
                    session_id=sess.id,
                    agent_id=sess.agent_id,
                    memory_id=memory.id,
                    importance=importance,
                )

    @staticmethod
    async def loop(interval: float = 15.0):
        logger.info("memory_worker.started", interval=interval)
        while True:
            try:
                await MemoryWorker.run_once()
            except Exception as exc:
                logger.error("memory_worker.error", error=str(exc))
            await asyncio.sleep(interval)
