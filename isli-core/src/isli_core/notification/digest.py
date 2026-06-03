"""Digest worker: accumulates low-priority events in Redis and flushes
batched digests to the Outbox on a schedule.

Idempotency: uses LRANGE + LTRIM so a crash mid-flush never double-delivers.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import structlog

from isli_core.db import get_db_session_manual
from isli_core.models import Outbox
from isli_core.redis_client import get_redis

logger = structlog.get_logger()

DIGEST_POLL_INTERVAL = 300  # 5 minutes
DIGEST_MAX_AGE_SECONDS = 3600  # 1 hour max accumulation window
DIGEST_MAX_COUNT = 10  # flush immediately if 10+ items accumulated

# Events eligible for digesting
digest_eligible_events = {
    "task:created",
    "memory:journal_updated",
    "memory:context_injected",
    "agent:heartbeat",
    "keeper:inference",
}


class DigestWorker:
    """Accumulate low-priority events into digests and flush periodically."""

    @staticmethod
    async def run_once():
        redis = await get_redis()
        now = datetime.now(UTC)

        # Find all batch keys
        try:
            keys = await redis.keys("notif:batch:*")
        except Exception as exc:
            logger.warning("digest.keys_failed", error=str(exc))
            return

        for key in keys:
            try:
                # LRANGE all items
                items_raw = await redis.lrange(key, 0, -1)
                if not items_raw:
                    continue

                # LTRIM atomically remove the items we're about to process
                # so a crash here means we lose items but never double-deliver
                await redis.ltrim(key, len(items_raw), -1)

                items = [json.loads(i) for i in items_raw]

                # Parse key: notif:batch:{user_id}:{category}
                parts = key.decode().split(":")
                if len(parts) < 4:
                    continue
                user_id = parts[2]
                category = parts[3] if len(parts) > 3 else "low"

                # Decide whether to flush based on age or count
                oldest_ts = items[0].get("timestamp", now.isoformat())
                oldest_dt = datetime.fromisoformat(oldest_ts)
                age_seconds = (now - oldest_dt).total_seconds()

                if age_seconds < DIGEST_MAX_AGE_SECONDS and len(items) < DIGEST_MAX_COUNT:
                    # Not ready to flush — push items back to Redis
                    # (We already trimmed them, so we re-push)
                    pipe = redis.pipeline()
                    for item in items:
                        pipe.lpush(key, json.dumps(item))
                    await pipe.execute()
                    continue

                # Build digest content
                digest = _collapse_items(items)
                title = f"Digest: {len(items)} updates"
                body_lines = []
                for line in digest:
                    body_lines.append(f"• {line}")
                body = "\n".join(body_lines)

                # Stage to Outbox as a single in_app notification
                outbox_payload = {
                    "user_id": user_id,
                    "event_type": "system:digest",
                    "category": "low",
                    "title": title,
                    "body": body,
                    "dedup_key": None,  # digests are never deduped
                    "payload": {"digest_count": len(items), "items": items},
                }

                async with get_db_session_manual() as session:
                    outbox = Outbox(
                        topic="notification:in_app",
                        payload=outbox_payload,
                        headers={"user_id": user_id, "category": "low", "digest": "true"},
                    )
                    session.add(outbox)
                    await session.commit()

                logger.info(
                    "digest.flushed",
                    user_id=user_id,
                    count=len(items),
                    category=category,
                    age_seconds=age_seconds,
                )

                # Clean up empty Redis key
                remaining = await redis.llen(key)
                if remaining == 0:
                    await redis.delete(key)

            except Exception as exc:
                logger.error("digest.batch_failed", key=key, error=str(exc))

    @staticmethod
    async def loop(interval: float = DIGEST_POLL_INTERVAL):
        logger.info("digest_worker.started", interval=interval)
        while True:
            try:
                await DigestWorker.run_once()
            except Exception as exc:
                logger.error("digest_worker.error", error=str(exc))
            await asyncio.sleep(interval)


def _collapse_items(items: list[dict[str, Any]]) -> list[str]:
    """Collapse similar events into summary lines."""
    counters: dict[str, int] = {}
    for item in items:
        et = item.get("event_type", "update")
        counters[et] = counters.get(et, 0) + 1

    lines: list[str] = []
    for et, count in sorted(counters.items(), key=lambda x: -x[1]):
        label = et.replace(":", " ").replace("_", " ").title()
        if count == 1:
            lines.append(f"1 {label}")
        else:
            lines.append(f"{count} {label}s")
    return lines


async def accumulate_digest(
    user_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Push a low-priority event into the digest accumulator.
    Called by NotificationEngine when an event is marked as digest-eligible."""
    try:
        redis = await get_redis()
        key = f"notif:batch:{user_id}:low"
        item = {
            "event_type": event_type,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await redis.lpush(key, json.dumps(item))
        # Set TTL so orphaned keys expire automatically
        await redis.expire(key, DIGEST_MAX_AGE_SECONDS + 60)
    except Exception as exc:
        logger.warning("digest.accumulate_failed", user_id=user_id, error=str(exc))
