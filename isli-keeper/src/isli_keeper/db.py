import asyncpg
import pgvector.asyncpg
import structlog
from typing import Any
from .config import get_settings

logger = structlog.get_logger()

_pool: asyncpg.Pool | None = None

async def init_db():
    global _pool
    settings = get_settings()
    if not settings.database_url:
        logger.warning("db.no_database_url_configured")
        return
    
    try:
        _pool = await asyncpg.create_pool(
            settings.database_url,
            init=pgvector.asyncpg.register_vector
        )
        logger.info("db.pool_created")
    except Exception as exc:
        logger.error("db.init_failed", error=str(exc))

async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        logger.info("db.pool_closed")

async def get_recent_memories(agent_id: str, limit: int = 5) -> list[str]:
    global _pool
    if not _pool:
        return []
    
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT summary FROM episodic_memories WHERE agent_id = $1 AND deleted_at IS NULL ORDER BY created_at DESC LIMIT $2",
            agent_id, limit
        )
        return [r["summary"] for r in rows]

async def get_relevant_memories(agent_id: str, query_embedding: list[float], limit: int = 5) -> list[str]:
    global _pool
    if not _pool:
        return []
    
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT summary FROM episodic_memories WHERE agent_id = $1 AND deleted_at IS NULL ORDER BY embedding <=> $2 LIMIT $3",
            agent_id, query_embedding, limit
        )
        return [r["summary"] for r in rows]

async def get_session_data(session_id: str) -> dict[str, Any]:
    global _pool
    if not _pool:
        return {}
    
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT messages, journal, journal_updated_at FROM sessions WHERE id = $1 AND deleted_at IS NULL",
            session_id
        )
        if not row:
            return {}
        
        return dict(row)

async def get_session_messages(session_id: str, limit: int = 5) -> list[dict[str, Any]]:
    data = await get_session_data(session_id)
    messages = data.get("messages", [])
    if not messages:
        return []
    return messages[-limit:] if isinstance(messages, list) else []
