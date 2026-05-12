import os

from redis.asyncio import Redis

try:
    from fakeredis.aioredis import FakeRedis
except Exception:
    FakeRedis = None  # type: ignore[misc,assignment]


async def get_redis(url: str | None = None) -> Redis:
    redis_url = url or os.getenv("REDIS_URL", "redis://localhost:6379")
    if redis_url.startswith("fakeredis://"):
        if FakeRedis is None:
            raise RuntimeError("fakeredis is not installed")
        return FakeRedis()
    return Redis.from_url(redis_url, decode_responses=True)
