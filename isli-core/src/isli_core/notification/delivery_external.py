"""External channel delivery handler (Telegram/WhatsApp).

Posts formatted notification text to isli-channels for outbound push.
Respects presence-based suppression: if user is active on Board UI,
non-critical notifications are suppressed to avoid double-notification.
"""

from typing import Any

import httpx
import structlog

from isli_core.auth import create_internal_token
from isli_core.config import get_settings
from isli_core.redis_client import get_redis

logger = structlog.get_logger()


async def deliver_external(topic: str, payload: dict[str, Any], headers: dict[str, Any]) -> None:
    """Forward a notification to external channels (Telegram/WhatsApp).

    Payload must contain:
      - user_id (maps to channel_user_id)
      - title, body
      - category (used for presence suppression logic)
      - channels list from preferences (e.g., ["telegram"])
    """
    user_id = payload.get("user_id")
    category = payload.get("category", "normal")
    pref_channels = payload.get("channels", [])
    title = payload.get("title", "")
    body = payload.get("body", "")

    if not user_id:
        raise ValueError("Missing user_id in external notification payload")

    # Presence suppression: if user is active on Board and this is non-critical, skip push
    if category != "critical":
        try:
            redis = await get_redis()
            is_present = await redis.exists(f"presence:board:{user_id}")
            if is_present:
                logger.info(
                    "notification.external_suppressed_presence",
                    user_id=user_id,
                    category=category,
                )
                return
        except Exception as exc:
            logger.warning("notification.presence_check_failed", user_id=user_id, error=str(exc))

    # Build notification text
    text = f"🔔 *{title}*"
    if body:
        text += f"\n\n{body}"

    settings = get_settings()
    channels_url = settings.channels_url

    # Try each enabled external channel
    for channel in pref_channels:
        if channel == "in_app":
            continue

        try:
            async with httpx.AsyncClient() as client:
                req_body: dict[str, Any] = {
                    "channel": channel,
                    "channel_user_id": user_id,
                    "text": text,
                    "agent_id": payload.get("agent_id"),
                    "source": "notification",
                }
                if channel == "telegram":
                    req_body["parse_mode"] = "Markdown"
                resp = await client.post(
                    f"{channels_url}/send",
                    json=req_body,
                    headers={"X-Internal-Auth": create_internal_token("core", scopes=["channels:send"], expires_minutes=5)},
                    timeout=10.0,
                )
                resp.raise_for_status()
                logger.info(
                    "notification.external_delivered",
                    user_id=user_id,
                    channel=channel,
                    category=category,
                )
        except Exception as exc:
            logger.error(
                "notification.external_delivery_failed",
                user_id=user_id,
                channel=channel,
                error=str(exc),
            )
