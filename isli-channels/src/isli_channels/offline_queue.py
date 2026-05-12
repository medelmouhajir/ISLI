import structlog
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

logger = structlog.get_logger()

OFFLINE_QUEUE_PREFIX = "channel:offline"


class OfflineMessageQueue:
    """Per-channel queues for platform outages. Messages buffered and retried."""

    def __init__(self, redis: Redis):
        self.redis = redis

    def _key(self, channel: str) -> str:
        return f"{OFFLINE_QUEUE_PREFIX}:{channel}"

    async def enqueue(self, channel: str, payload: dict[str, Any]) -> None:
        key = self._key(channel)
        payload["_enqueued_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.lpush(key, str(payload))
        logger.info("offline_queue.enqueued", channel=channel)

    async def dequeue(self, channel: str, limit: int = 100) -> list[dict[str, Any]]:
        key = self._key(channel)
        items = await self.redis.lrange(key, 0, limit - 1)
        import ast
        return [
            ast.literal_eval(i.decode() if isinstance(i, bytes) else i) for i in items
        ]

    async def ack(self, channel: str, payload: dict[str, Any]) -> None:
        key = self._key(channel)
        # Remove the exact payload (best-effort)
        raw = str(payload)
        removed = await self.redis.lrem(key, 0, raw)
        logger.info("offline_queue.acked", channel=channel, removed=removed)

    async def size(self, channel: str) -> int:
        key = self._key(channel)
        return await self.redis.llen(key)

    async def is_platform_online(self, channel: str) -> bool:
        """Check if platform circuit is closed (not rate-limited)."""
        circuit = await self.redis.get(f"rate_limit:circuit:{channel}")
        return circuit is None

    async def drain(self, channel: str, sender: Any) -> int:
        """Drain offline queue when platform comes back online."""
        sent = 0
        messages = await self.dequeue(channel)
        for msg in messages:
            try:
                await sender(msg)
                await self.ack(channel, msg)
                sent += 1
            except Exception as exc:
                logger.warning("offline_queue.drain_failed", channel=channel, error=str(exc))
                break
        logger.info("offline_queue.drained", channel=channel, sent=sent, remaining=len(messages) - sent)
        return sent
