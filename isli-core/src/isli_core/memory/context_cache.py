"""Context cache for fully-assembled context_summary strings.

Caches the **final assembled string** returned by Keeper so that subsequent
turns in the same session can skip the Keeper call entirely.  The block
assembly format lives only in Keeper (``/context/inject``); this module
never re-assembles blocks locally.

Invalidation is event-driven:
- Agent identity/config change  → ``invalidate_for_agent``
- JournalWorker flush           → ``invalidate_for_session``
- New messages (turn hash miss) → natural cache miss
"""

import hashlib
import json
from typing import Any

import structlog

from isli_core.redis_client import get_redis

logger = structlog.get_logger()

FULL_KEY_PREFIX = "ctx:full"
SESSION_MAP_KEY_PREFIX = "ctx:session_map"


def _turn_hash(
    session_id: str | None,
    task_description: str | None,
    last_message_ids: list[str],
) -> str:
    """Deterministic hash of the session state that affects context content."""
    parts = [
        session_id or "",
        task_description or "",
        *last_message_ids,
    ]
    joined = "\n".join(parts)
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def _full_key(agent_id: str, turn_hash: str) -> str:
    return f"{FULL_KEY_PREFIX}:{agent_id}:{turn_hash}"


def _session_map_key(session_id: str) -> str:
    return f"{SESSION_MAP_KEY_PREFIX}:{session_id}"


class ContextCache:
    """Tiered cache that stores assembled context_summary strings."""

    @staticmethod
    async def get(
        agent_id: str,
        session_id: str | None,
        task_description: str | None,
        last_message_ids: list[str],
    ) -> str | None:
        """Return cached context_summary or None on miss."""
        redis = await get_redis()
        th = _turn_hash(session_id, task_description, last_message_ids)
        key = _full_key(agent_id, th)
        value = await redis.get(key)
        if value is not None:
            logger.info(
                "context.cache_hit",
                agent_id=agent_id,
                session_id=session_id,
                turn_hash=th,
            )
            return value.decode() if isinstance(value, bytes) else value
        logger.info(
            "context.cache_miss",
            agent_id=agent_id,
            session_id=session_id,
            turn_hash=th,
        )
        return None

    @staticmethod
    async def set(
        agent_id: str,
        session_id: str | None,
        task_description: str | None,
        last_message_ids: list[str],
        context_summary: str,
        ttl: int = 30,
    ) -> None:
        """Cache assembled context_summary with a short TTL.

        Also writes a secondary index mapping ``session_id → agent_id`` so
        ``invalidate_for_session`` can derive the key pattern.
        """
        redis = await get_redis()
        th = _turn_hash(session_id, task_description, last_message_ids)
        key = _full_key(agent_id, th)
        await redis.setex(key, ttl, context_summary)

        if session_id:
            session_map_key = _session_map_key(session_id)
            await redis.setex(session_map_key, 3600, agent_id)

        logger.info(
            "context.cache_set",
            agent_id=agent_id,
            session_id=session_id,
            turn_hash=th,
            ttl=ttl,
        )

    @staticmethod
    async def invalidate_for_agent(agent_id: str) -> int:
        """Delete all cached contexts for an agent. Called on config update."""
        redis = await get_redis()
        pattern = f"{FULL_KEY_PREFIX}:{agent_id}:*"
        count = 0
        cursor = b"0"
        while cursor:
            cursor, keys = await redis.scan(
                cursor=cursor, match=pattern, count=100
            )
            if keys:
                await redis.delete(*keys)
                count += len(keys)
            if cursor == b"0":
                break
        logger.info(
            "context.invalidated_agent",
            agent_id=agent_id,
            keys_deleted=count,
        )
        return count

    @staticmethod
    async def invalidate_for_session(session_id: str) -> int:
        """Delete all cached contexts for a session. Called after journal flush."""
        redis = await get_redis()
        session_map_key = _session_map_key(session_id)
        agent_id = await redis.get(session_map_key)
        if agent_id is None:
            logger.warning(
                "context.invalidate_session_no_agent",
                session_id=session_id,
            )
            return 0

        agent_id = agent_id.decode() if isinstance(agent_id, bytes) else agent_id
        pattern = f"{FULL_KEY_PREFIX}:{agent_id}:*"
        count = 0
        cursor = b"0"
        while cursor:
            cursor, keys = await redis.scan(
                cursor=cursor, match=pattern, count=100
            )
            if keys:
                await redis.delete(*keys)
                count += len(keys)
            if cursor == b"0":
                break

        await redis.delete(session_map_key)
        logger.info(
            "context.invalidated_session",
            session_id=session_id,
            agent_id=agent_id,
            keys_deleted=count,
        )
        return count
