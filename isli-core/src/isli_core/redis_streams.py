"""Redis Stream helpers for reliable message queuing.

Provides idempotent stream group creation, consumer group reads,
message acknowledgement, pending-message reclaim, and DLQ support.
All payloads include schema version ``v=1`` for forward compatibility.
"""

import json
from typing import Any

import structlog

from isli_core.redis_client import get_redis

logger = structlog.get_logger()

DEFAULT_BLOCK_MS = 5000
DEFAULT_CLAIM_MIN_IDLE_MS = 30000


async def ensure_stream_group(stream_name: str, group_name: str) -> None:
    """Idempotently create a consumer group for a stream.

    Uses ``MKSTREAM`` so the stream is created if it does not exist.
    Silently ignores ``BUSYGROUP`` errors when the group already exists.
    """
    redis = await get_redis()
    try:
        await redis.xgroup_create(
            name=stream_name,
            groupname=group_name,
            id="$",
            mkstream=True,
        )
        logger.info(
            "redis_stream.group_created",
            stream=stream_name,
            group=group_name,
        )
    except Exception as exc:
        if "BUSYGROUP" in str(exc) or "already exists" in str(exc).lower():
            logger.debug(
                "redis_stream.group_already_exists",
                stream=stream_name,
                group=group_name,
            )
        else:
            raise


async def add_to_stream(stream_name: str, payload: dict[str, Any]) -> str:
    """Add a message to a Redis Stream with schema versioning.

    Injects ``{"v": 1}`` into the payload automatically so downstream
    consumers can handle schema migrations gracefully.
    """
    redis = await get_redis()
    payload_with_version = {"v": 1, **payload}
    message_id = await redis.xadd(
        stream_name,
        {"payload": json.dumps(payload_with_version)},
    )
    return message_id


async def read_group(
    stream_name: str,
    group_name: str,
    consumer_name: str,
    count: int = 10,
    block_ms: int = DEFAULT_BLOCK_MS,
) -> list[dict[str, Any]]:
    """Read messages from a stream via XREADGROUP.

    Returns a list of dicts with ``stream``, ``id``, and ``payload`` keys.
    """
    redis = await get_redis()
    raw = await redis.xreadgroup(
        groupname=group_name,
        consumername=consumer_name,
        streams={stream_name: ">"},
        count=count,
        block=block_ms,
    )
    messages: list[dict[str, Any]] = []
    for stream_data in raw:
        for msg_id, fields in stream_data[1]:
            payload = json.loads(fields.get("payload", "{}"))
            messages.append(
                {
                    "stream": stream_data[0],
                    "id": msg_id,
                    "payload": payload,
                }
            )
    return messages


async def acknowledge(stream_name: str, group_name: str, message_id: str) -> None:
    """Acknowledge a message so it is removed from the Pending Entries List."""
    redis = await get_redis()
    await redis.xack(stream_name, group_name, message_id)


async def claim_pending(
    stream_name: str,
    group_name: str,
    consumer_name: str,
    min_idle_ms: int = DEFAULT_CLAIM_MIN_IDLE_MS,
    count: int = 10,
) -> list[dict[str, Any]]:
    """Claim messages that have been idle in the PEL for longer than ``min_idle_ms``.

    Returns claimed messages in the same shape as ``read_group``.
    """
    redis = await get_redis()
    raw = await redis.xautoclaim(
        name=stream_name,
        groupname=group_name,
        consumername=consumer_name,
        min_idle_time=min_idle_ms,
        count=count,
        start_id="0-0",
    )
    # xautoclaim returns (next_start_id, [(msg_id, fields), ...])
    messages: list[dict[str, Any]] = []
    for msg_id, fields in raw[1]:
        payload = json.loads(fields.get("payload", "{}"))
        messages.append(
            {
                "stream": stream_name,
                "id": msg_id,
                "payload": payload,
            }
        )
    return messages


async def write_dlq(
    stream_name: str,
    payload: dict[str, Any],
    error: str,
    attempts: int,
) -> str:
    """Write a failed message to a dedicated Dead Letter Queue stream.

    The DLQ stream name is derived as ``{stream_name}:dlq``.
    """
    dlq_name = f"{stream_name}:dlq"
    redis = await get_redis()
    message_id = await redis.xadd(
        dlq_name,
        {
            "payload": json.dumps(payload),
            "error": error,
            "attempts": str(attempts),
            "stream": stream_name,
        },
    )
    logger.warning(
        "redis_stream.dlq_written",
        dlq=dlq_name,
        original_stream=stream_name,
        attempts=attempts,
        error=error,
    )
    return message_id


async def get_pending_info(
    stream_name: str,
    group_name: str,
) -> dict[str, Any]:
    """Return summary statistics about the Pending Entries List."""
    redis = await get_redis()
    info = await redis.xpending(stream_name, group_name)
    return {
        "count": info.get("pending", 0),
        "lowest_id": info.get("min", None),
        "highest_id": info.get("max", None),
        "consumers": info.get("consumers", []),
    }
