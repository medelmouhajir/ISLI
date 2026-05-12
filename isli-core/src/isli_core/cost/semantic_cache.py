"""Response semantic cache keyed by task embedding similarity."""

import hashlib
import json
import structlog
from typing import Any

from redis.asyncio import Redis

from isli_core.memory.validation import MemoryValidator

logger = structlog.get_logger()

CACHE_PREFIX = "cost:semantic_cache"
DEFAULT_TTL_SECONDS = 3600
DEFAULT_SIMILARITY_THRESHOLD = 0.92


class SemanticResponseCache:
    """Cache agent responses keyed by task embedding similarity."""

    def __init__(self, redis: Redis, threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
        self.redis = redis
        self.threshold = threshold
        self._hits = 0
        self._misses = 0

    def _key(self, agent_id: str, task_hash: str) -> str:
        return f"{CACHE_PREFIX}:{agent_id}:{task_hash}"

    @staticmethod
    def _hash_task(task_input: str) -> str:
        return hashlib.sha256(task_input.encode()).hexdigest()[:16]

    async def lookup(self, agent_id: str, task_input: str, embedding: list[float]) -> dict[str, Any] | None:
        """Find a cached response with sufficiently similar embedding."""
        pattern = f"{CACHE_PREFIX}:{agent_id}:*"
        async for key in self.redis.scan_iter(match=pattern):
            raw = await self.redis.get(key)
            if raw is None:
                continue
            entry = json.loads(raw)
            cached_embedding = entry.get("embedding")
            if cached_embedding is None:
                continue
            try:
                sim = MemoryValidator.cosine_similarity(embedding, cached_embedding)
            except ValueError:
                continue
            if sim >= self.threshold:
                self._hits += 1
                logger.info("semantic_cache.hit", agent_id=agent_id, similarity=sim)
                return entry.get("response")

        self._misses += 1
        logger.info("semantic_cache.miss", agent_id=agent_id)
        return None

    async def store(
        self,
        agent_id: str,
        task_input: str,
        embedding: list[float],
        response: dict[str, Any],
        ttl: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        key = self._key(agent_id, self._hash_task(task_input))
        entry = {
            "embedding": embedding,
            "response": response,
            "stored_at": structlog.processors.TimeStamper(fmt="iso").__repr__(),
        }
        await self.redis.setex(key, ttl, json.dumps(entry))
        logger.info("semantic_cache.store", agent_id=agent_id, key=key)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    def stats(self) -> dict[str, Any]:
        return {"hits": self._hits, "misses": self._misses, "hit_rate": round(self.hit_rate, 4)}
