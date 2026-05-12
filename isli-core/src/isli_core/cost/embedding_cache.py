"""Redis LRU cache for embeddings keyed by content hash."""

import hashlib
import json
import structlog
from typing import Any

from redis.asyncio import Redis

logger = structlog.get_logger()

CACHE_PREFIX = "cost:embedding"
DEFAULT_TTL_SECONDS = 3600


class EmbeddingCache:
    """LRU-style cache for text→embedding to avoid redundant API calls."""

    def __init__(self, redis: Redis):
        self.redis = redis
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _key(self, model: str, text_hash: str) -> str:
        return f"{CACHE_PREFIX}:{model}:{text_hash}"

    async def get(self, model: str, text: str) -> list[float] | None:
        key = self._key(model, self._hash(text))
        raw = await self.redis.get(key)
        if raw is None:
            self._misses += 1
            return None
        self._hits += 1
        data = json.loads(raw)
        logger.info("embedding_cache.hit", model=model)
        return data

    async def set(self, model: str, text: str, embedding: list[float], ttl: int = DEFAULT_TTL_SECONDS) -> None:
        key = self._key(model, self._hash(text))
        await self.redis.setex(key, ttl, json.dumps(embedding))
        logger.info("embedding_cache.set", model=model, key=key)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    def stats(self) -> dict[str, Any]:
        return {"hits": self._hits, "misses": self._misses, "hit_rate": round(self.hit_rate, 4)}
