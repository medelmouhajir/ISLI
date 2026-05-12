import hashlib
import structlog
from datetime import timedelta

from redis.asyncio import Redis

logger = structlog.get_logger()

DEFAULT_WINDOW_SECONDS = 300  # 5 minutes


class WebhookIdempotency:
    """Platform-specific webhook deduplication using Redis."""

    def __init__(self, redis: Redis, window_seconds: int = DEFAULT_WINDOW_SECONDS):
        self.redis = redis
        self.window_seconds = window_seconds

    @staticmethod
    def extract_id(platform: str, payload: dict) -> str | None:
        """Extract platform-specific unique webhook ID."""
        if platform == "telegram":
            return payload.get("update_id")
        if platform == "whatsapp":
            return payload.get("messages", [{}])[0].get("id")
        if platform == "web":
            return payload.get("request_id")
        if platform == "email":
            msg_id = payload.get("message_id") or payload.get("headers", {}).get("Message-ID")
            return msg_id
        return None

    def _key(self, platform: str, webhook_id: str) -> str:
        return f"webhook:dedup:{platform}:{webhook_id}"

    async def is_duplicate(self, platform: str, payload: dict) -> bool:
        webhook_id = self.extract_id(platform, payload)
        if webhook_id is None:
            # No idempotency key — hash the payload as fallback
            raw = str(sorted(payload.items()))
            webhook_id = hashlib.sha256(raw.encode()).hexdigest()[:32]

        key = self._key(platform, str(webhook_id))
        exists = await self.redis.get(key)
        if exists:
            logger.info("webhook.duplicate_detected", platform=platform, webhook_id=webhook_id)
            return True

        await self.redis.setex(key, timedelta(seconds=self.window_seconds), "1")
        return False
