"""Web Push delivery handler.

Sends push notifications to all registered browser/mobile endpoints for a user.
Handles 404/410 errors by pruning stale subscriptions.
Resolves external channel user IDs (Telegram, WhatsApp) to board user IDs
via ChannelIdentity mappings.
"""

import json
from typing import Any

import structlog
from pywebpush import webpush, WebPushException
from sqlalchemy import select, delete

from isli_core.config import get_settings
from isli_core.db import get_db_session_manual
from isli_core.models import WebPushSubscription, ChannelIdentity

logger = structlog.get_logger()

# Web Push Payload limit is 4KB.
MAX_PAYLOAD_BYTES = 3800


async def _resolve_board_user_ids(session, user_id: str, channel: str | None) -> list[str]:
    """Resolve a channel user ID to linked board user IDs via ChannelIdentity.

    If the user_id already has direct web push subscriptions, return it as-is.
    Otherwise look up identity mappings and return linked board user IDs.
    """
    # Fast path: direct subscriptions exist
    direct = await session.execute(
        select(WebPushSubscription).where(WebPushSubscription.user_id == user_id).limit(1)
    )
    if direct.scalar_one_or_none():
        return [user_id]

    # Look up identity mappings for this external user
    stmt = select(ChannelIdentity.board_user_id).where(
        ChannelIdentity.channel_user_id == user_id
    )
    if channel:
        stmt = stmt.where(ChannelIdentity.channel == channel)
    stmt = stmt.distinct()
    result = await session.execute(stmt)
    board_ids = [row[0] for row in result.all()]
    return board_ids if board_ids else [user_id]


async def deliver_web_push(topic: str, payload: dict[str, Any], headers: dict[str, Any]) -> None:
    """Fan-out notification to all web push subscriptions for a user."""
    user_id = payload.get("user_id")
    if not user_id:
        raise ValueError("Missing user_id in web_push payload")

    settings = get_settings()
    if not settings.vapid_private_key or not settings.vapid_public_key:
        logger.warning("web_push.not_configured", user_id=user_id)
        return

    async with get_db_session_manual() as session:
        # Resolve external channel IDs to board user IDs
        channel = payload.get("channel")
        board_user_ids = await _resolve_board_user_ids(session, user_id, channel)

        # Collect all subscriptions for resolved users
        all_subs: list[WebPushSubscription] = []
        for board_id in board_user_ids:
            stmt = select(WebPushSubscription).where(WebPushSubscription.user_id == board_id)
            result = await session.execute(stmt)
            all_subs.extend(result.scalars().all())

        if not all_subs:
            logger.debug("web_push.no_subscriptions", user_id=user_id, resolved_users=board_user_ids)
            return

        # Prepare payload
        push_data = {
            "title": payload.get("title", "ISLI Notification"),
            "body": (payload.get("body") or "")[:200],  # Truncate body for safety
            "data": {
                "notification_id": payload.get("notification_id"),
                "event_type": payload.get("event_type"),
                "agent_id": payload.get("agent_id"),
                "task_id": payload.get("task_id"),
            }
        }

        payload_json = json.dumps(push_data)
        if len(payload_json.encode()) > MAX_PAYLOAD_BYTES:
            # Further truncate if needed (extreme case)
            push_data["body"] = push_data["body"][:50] + "..."
            payload_json = json.dumps(push_data)

        vapid_claims = {"sub": f"mailto:{settings.vapid_claims_email}"}

        # Send to all subscriptions (deduplicate by endpoint)
        seen_endpoints = set()
        for sub in all_subs:
            if sub.endpoint in seen_endpoints:
                continue
            seen_endpoints.add(sub.endpoint)

            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {
                            "p256dh": sub.p256dh,
                            "auth": sub.auth
                        }
                    },
                    data=payload_json,
                    vapid_private_key=settings.vapid_private_key,
                    vapid_claims=vapid_claims
                )
                logger.info("web_push.delivered", user_id=user_id, endpoint=sub.endpoint[:30])
            except WebPushException as exc:
                if exc.response is not None and exc.response.status_code in (404, 410):
                    logger.info("web_push.pruning_stale_subscription", user_id=user_id, endpoint=sub.endpoint[:30])
                    await session.execute(delete(WebPushSubscription).where(WebPushSubscription.id == sub.id))
                    await session.commit()
                else:
                    logger.error("web_push.delivery_failed", user_id=user_id, error=str(exc))
            except Exception as exc:
                logger.error("web_push.unexpected_error", user_id=user_id, error=str(exc))
