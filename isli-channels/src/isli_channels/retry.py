import asyncio
import structlog
from datetime import timedelta
from typing import Callable, TypeVar

from redis.asyncio import Redis

from isli_channels.rate_limit import RateLimiter

logger = structlog.get_logger()

T = TypeVar("T")

DELIVERY_QUEUE = "channel:delivery:queue"
DLQ_KEY = "channel:delivery:dlq"
MAX_RETRIES = 5
BASE_DELAY_SECONDS = 2


class DeliveryRetry:
    """At-least-once delivery with exponential backoff and DLQ."""

    def __init__(self, redis: Redis, rate_limiter: RateLimiter | None = None):
        self.redis = redis
        self.rate_limiter = rate_limiter

    async def enqueue(
        self,
        channel: str,
        recipient: str,
        content: str,
        message_id: str | None = None,
    ) -> None:
        payload = {
            "channel": channel,
            "recipient": recipient,
            "content": content,
            "message_id": message_id,
            "attempt": 0,
        }
        await self.redis.lpush(DELIVERY_QUEUE, str(payload))
        logger.info("delivery.enqueued", channel=channel, recipient=recipient)

    async def process_queue(self, sender: Callable[[str, str, str], T]) -> None:
        while True:
            try:
                # BRPOP with 5s timeout
                result = await self.redis.brpop(DELIVERY_QUEUE, timeout=5)
                if result is None:
                    continue
                _, raw = result
                import ast
                payload = ast.literal_eval(raw.decode() if isinstance(raw, bytes) else raw)

                channel = payload["channel"]
                recipient = payload["recipient"]
                content = payload["content"]
                attempt = payload.get("attempt", 0)

                if self.rate_limiter:
                    await self.rate_limiter.wait_if_limited(channel)

                try:
                    await sender(channel, recipient, content)
                    logger.info("delivery.success", channel=channel, recipient=recipient)
                except Exception as exc:
                    attempt += 1
                    if attempt >= MAX_RETRIES:
                        payload["attempt"] = attempt
                        payload["error"] = str(exc)
                        await self.redis.lpush(DLQ_KEY, str(payload))
                        logger.error("delivery.dlq", channel=channel, recipient=recipient, error=str(exc))
                    else:
                        delay = BASE_DELAY_SECONDS * (2 ** attempt)
                        payload["attempt"] = attempt
                        await self.redis.lpush(DELIVERY_QUEUE, str(payload))
                        logger.warning(
                            "delivery.retry",
                            channel=channel,
                            recipient=recipient,
                            attempt=attempt,
                            delay=delay,
                        )
                        await asyncio.sleep(delay)
            except Exception:
                logger.exception("delivery.queue_error")
                await asyncio.sleep(1)

    async def list_dlq(self, limit: int = 50) -> list[dict]:
        items = await self.redis.lrange(DLQ_KEY, 0, limit - 1)
        import ast
        return [ast.literal_eval(i.decode() if isinstance(i, bytes) else i) for i in items]

    async def retry_dlq_item(self, payload: dict) -> None:
        payload["attempt"] = 0
        payload.pop("error", None)
        await self.redis.lpush(DELIVERY_QUEUE, str(payload))
        # Remove from DLQ (best-effort; exact match)
        await self.redis.lrem(DLQ_KEY, 0, str(payload))
