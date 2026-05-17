import os

from redis.asyncio import Redis

try:
    from fakeredis.aioredis import FakeRedis
except Exception:
    FakeRedis = None  # type: ignore[misc,assignment]


_redis: Redis | None = None


async def get_redis(url: str | None = None) -> Redis:
    global _redis
    if _redis is not None and url is None:
        return _redis

    redis_url = url or os.getenv("REDIS_URL", "redis://localhost:6379")
    if redis_url.startswith("fakeredis://"):
        if FakeRedis is None:
            raise RuntimeError("fakeredis is not installed")
        client = FakeRedis()
    else:
        client = Redis.from_url(redis_url, decode_responses=True)
    
    if url is None:
        _redis = client
    return client
