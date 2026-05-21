import json
import os
import structlog
import redis
from typing import Any, Dict

class RedisPubSubProcessor:
    def __init__(self, redis_url: str, agent_id: str):
        self.redis_client = redis.from_url(redis_url)
        self.channel = f"agent:{agent_id}:logs"

    def __call__(self, logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Create a copy to avoid modifying the original dict for other processors
            log_entry = event_dict.copy()
            # Ensure timestamp and level are included if they were added by other processors
            # Publish as JSON string
            self.redis_client.publish(self.channel, json.dumps(log_entry, default=str))
        except Exception:
            # Fallback: don't let logging failures crash the agent
            pass
        return event_dict

def configure_logging(agent_id: str):
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add Redis processor if URL is available
    if redis_url:
        processors.append(RedisPubSubProcessor(redis_url, agent_id))

    # Finally, format as console output for standard docker logs
    processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(0),
        cache_logger_on_first_use=True,
    )
