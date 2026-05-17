import json
import structlog
from isli_core.redis_client import get_redis

logger = structlog.get_logger()

class EventManager:
    """Publish real-time events to Redis Pub/Sub."""
    
    @staticmethod
    async def emit(event_type: str, payload: dict):
        redis = await get_redis()
        event = {
            "type": event_type,
            "payload": payload
        }
        try:
            await redis.publish("isli:events", json.dumps(event))
            logger.debug("event.emitted", type=event_type)
        except Exception as exc:
            logger.error("event.emit_failed", type=event_type, error=str(exc))
