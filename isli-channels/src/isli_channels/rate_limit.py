import structlog
import asyncio
from datetime import datetime, timezone

from redis.asyncio import Redis

logger = structlog.get_logger()

DEFAULT_LIMITS = {
    "telegram": {"messages_per_second": 30, "burst": 100},
    "whatsapp": {"messages_per_second": 20, "burst": 80},
    "email": {"messages_per_second": 10, "burst": 50},
    "web": {"messages_per_second": 100, "burst": 500},
}


class RateLimiter:
    """Per-platform rate limiter respecting Retry-After."""

    def __init__(self, redis: Redis, limits: dict | None = None):
        self.redis = redis
        self.limits = limits or DEFAULT_LIMITS

    def _key(self, channel: str) -> str:
        return f"rate_limit:{channel}"

    def _circuit_key(self, channel: str) -> str:
        return f"rate_limit:circuit:{channel}"

    async def is_limited(self, channel: str) -> bool:
        if self.redis is None:
            return False
        circuit_open = await self.redis.get(self._circuit_key(channel))
        if circuit_open:
            return True
        return False

    async def wait_if_limited(self, channel: str) -> None:
        if self.redis is None:
            return
        circuit_open = await self.redis.get(self._circuit_key(channel))
        if circuit_open:
            retry_after = int(circuit_open)
            logger.warning("rate_limit.circuit_open", channel=channel, retry_after=retry_after)
            await asyncio.sleep(retry_after)
            return

        config = self.limits.get(channel, {"messages_per_second": 10, "burst": 50})
        key = self._key(channel)
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 1)
        results = await pipe.execute()
        current = results[0]

        if current > config["messages_per_second"]:
            logger.warning("rate_limit.hit", channel=channel, current=current)
            await asyncio.sleep(1.0)

    async def report_rate_limit(self, channel: str, retry_after: int) -> None:
        """Called when platform returns 429 with Retry-After."""
        if self.redis is None:
            return
        await self.redis.setex(
            self._circuit_key(channel),
            retry_after,
            str(retry_after),
        )
        logger.warning("rate_limit.platform_429", channel=channel, retry_after=retry_after)

    async def reset(self, channel: str) -> None:
        if self.redis is None:
            return
        await self.redis.delete(self._circuit_key(channel))
        await self.redis.delete(self._key(channel))
