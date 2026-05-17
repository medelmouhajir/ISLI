import asyncio
import json
import structlog
from isli_core.redis_client import get_redis
from isli_core.memory.keeper_client import KeeperClient
from isli_core.db import get_db_session_manual
from isli_core.models import Agent
from sqlalchemy import select

logger = structlog.get_logger()

async def heartbeat_validator_worker():
    """Background worker to validate agent heartbeats asynchronously via Keeper."""
    retry_delay = 1.0
    
    while True:
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe("isli:events")
            
            logger.info("jobs.heartbeat_validator_started")
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    
                    try:
                        event = json.loads(data)
                        if event.get("type") == "agent:heartbeat":
                            payload = event.get("payload", {})
                            agent_id = payload.get("agent_id")
                            heartbeat_at = payload.get("heartbeat_at")
                            
                            if agent_id and heartbeat_at:
                                asyncio.create_task(validate_and_update(agent_id, heartbeat_at))
                    except Exception as e:
                        logger.debug("jobs.heartbeat_validator_parse_error", error=str(e))
                            
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("jobs.heartbeat_validator_error", error=str(exc))
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60.0)

async def validate_and_update(agent_id: str, heartbeat_at: str):
    is_valid = await KeeperClient.validate_heartbeat(agent_id, heartbeat_at)
    if not is_valid:
        logger.warning("agent.heartbeat_anomaly_detected", agent_id=agent_id)
        try:
            async with get_db_session_manual() as db:
                result = await db.execute(select(Agent).where(Agent.id == agent_id))
                agent = result.scalar_one_or_none()
                if agent:
                    agent.status = "flagged"
                    await db.commit()
                    logger.info("agent.status_updated", agent_id=agent_id, status="flagged")
        except Exception as exc:
            logger.error("jobs.heartbeat_validator_update_failed", agent_id=agent_id, error=str(exc))
