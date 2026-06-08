import os
from redis.asyncio import Redis
from isli_skills.config import get_settings

_redis: Redis | None = None

async def get_blob_redis() -> Redis:
    global _redis
    if _redis is not None:
        return _redis

    settings = get_settings()
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # Force DB 10 for blob store
    if "?" in redis_url:
        base, query = redis_url.split("?", 1)
        redis_url = f"{base.rsplit('/', 1)[0]}/{settings.blob_store_db}?{query}"
    else:
        redis_url = f"{redis_url.rsplit('/', 1)[0]}/{settings.blob_store_db}"

    _redis = Redis.from_url(redis_url, decode_responses=False)
    return _redis
