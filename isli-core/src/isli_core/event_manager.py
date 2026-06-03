import json
import structlog
from datetime import datetime, timezone
from isli_core.redis_client import get_redis

logger = structlog.get_logger()

class EventManager:
    """Publish real-time events to Redis Pub/Sub."""
    
    @staticmethod
    async def emit(event_type: str, payload: dict):
        redis = await get_redis()
        event = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        try:
            event_json = json.dumps(event)
            await redis.publish("isli:events", event_json)
            logger.debug("event.emitted", type=event_type)

            # Persist memory events for history fetching
            if event_type.startswith("memory:") and "agent_id" in payload:
                agent_id = payload["agent_id"]
                key = f"agent:{agent_id}:memory_events"
                await redis.lpush(key, event_json)
                await redis.ltrim(key, 0, 49)  # Keep last 50 events

        except Exception as exc:
            logger.error("event.emit_failed", type=event_type, error=str(exc))
