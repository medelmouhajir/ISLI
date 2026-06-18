import asyncio
import json
import structlog
from isli_core.redis_client import get_redis
from isli_core.memory.keeper_client import KeeperClient
from isli_core.db import get_db_session_manual
from isli_core.models import Agent
from sqlalchemy import select

# ANOMALY_THRESHOLD = 3  # ~30 minutes at 10-min heartbeat intervals
ANOMALY_THRESHOLD = 5    # ~50 minutes at 10-min heartbeat intervals
ANOMALY_COUNTER_TTL_SECONDS = 3600

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
                            consecutive_idle_beats = payload.get("consecutive_idle_beats", 0)
                            current_task_id = payload.get("current_task_id")

                            if agent_id and heartbeat_at:
                                asyncio.create_task(
                                    validate_and_update(
                                        agent_id, heartbeat_at,
                                        consecutive_idle_beats=consecutive_idle_beats,
                                        current_task_id=current_task_id,
                                    )
                                )
                    except Exception as e:
                        logger.debug("jobs.heartbeat_validator_parse_error", error=str(e))
                            
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("jobs.heartbeat_validator_error", error=str(exc))
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60.0)

async def validate_and_update(agent_id: str, heartbeat_at: str, consecutive_idle_beats: int = 0, current_task_id: str | None = None):
    try:
        is_valid = await asyncio.wait_for(
            KeeperClient.validate_heartbeat(
                agent_id, heartbeat_at,
                consecutive_idle_beats=consecutive_idle_beats,
                current_task_id=current_task_id,
            ),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        logger.warning("agent.heartbeat_validate_skipped_slow", agent_id=agent_id)
        is_valid = True  # skip this beat, don't penalize the agent
    redis = await get_redis()
    counter_key = f"agent:heartbeat:anomaly:{agent_id}"

    if not is_valid:
        # Increment consecutive anomaly counter
        count = await redis.incr(counter_key)
        await redis.expire(counter_key, ANOMALY_COUNTER_TTL_SECONDS)
        logger.warning("agent.heartbeat_anomaly_detected", agent_id=agent_id, consecutive_count=count)

        if count >= ANOMALY_THRESHOLD:
            try:
                async with get_db_session_manual() as db:
                    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
                    agent = result.scalar_one_or_none()
                    if agent and agent.status != "flagged":
                        agent.status = "flagged"
                        await db.commit()
                        logger.info("agent.status_updated", agent_id=agent_id, status="flagged", consecutive_count=count)
            except Exception as exc:
                logger.error("jobs.heartbeat_validator_update_failed", agent_id=agent_id, error=str(exc))
    else:
        # Reset anomaly counter on valid heartbeat
        await redis.delete(counter_key)
        try:
            async with get_db_session_manual() as db:
                result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
                agent = result.scalar_one_or_none()
                if agent and agent.status == "flagged":
                    agent.status = "online"
                    await db.commit()
                    logger.info("agent.status_updated", agent_id=agent_id, status="online", reason="heartbeat_valid")
        except Exception as exc:
            logger.error("jobs.heartbeat_validator_unflag_failed", agent_id=agent_id, error=str(exc))
