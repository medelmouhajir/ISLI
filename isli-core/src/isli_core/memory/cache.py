import hashlib
import structlog
from typing import Any

from redis.asyncio import Redis

logger = structlog.get_logger()

CACHE_PREFIX = "memory:cache"
DEFAULT_TTL_SECONDS = 300


class MemoryCache:
    """Redis cache for memory lookups with invalidation on writes."""

    def __init__(self, redis: Redis):
        self.redis = redis

    def _key(self, agent_id: str, query_hash: str) -> str:
        return f"{CACHE_PREFIX}:{agent_id}:{query_hash}"

    @staticmethod
    def hash_query(query: str, top_k: int = 5) -> str:
        raw = f"{query}:{top_k}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def get(self, agent_id: str, query: str, top_k: int = 5) -> list[dict[str, Any]] | None:
        key = self._key(agent_id, self.hash_query(query, top_k))
        raw = await self.redis.get(key)
        if raw is None:
            return None
        import json
        data = json.loads(raw)
        logger.info("memory.cache_hit", agent_id=agent_id, query_hash=self.hash_query(query, top_k))
        return data

    async def set(self, agent_id: str, query: str, top_k: int, results: list[dict[str, Any]], ttl: int = DEFAULT_TTL_SECONDS) -> None:
        key = self._key(agent_id, self.hash_query(query, top_k))
        import json
        await self.redis.setex(key, ttl, json.dumps(results))
        logger.info("memory.cache_set", agent_id=agent_id, query_hash=self.hash_query(query, top_k))

    async def invalidate(self, agent_id: str) -> int:
        pattern = f"{CACHE_PREFIX}:{agent_id}:*"
        keys = []
        async for k in self.redis.scan_iter(match=pattern):
            keys.append(k)
        if keys:
            await self.redis.delete(*keys)
        logger.info("memory.cache_invalidated", agent_id=agent_id, keys_removed=len(keys))
        return len(keys)

    async def invalidate_all(self) -> int:
        pattern = f"{CACHE_PREFIX}:*"
        keys = []
        async for k in self.redis.scan_iter(match=pattern):
            keys.append(k)
        if keys:
            await self.redis.delete(*keys)
        logger.info("memory.cache_invalidated_all", keys_removed=len(keys))
        return len(keys)
