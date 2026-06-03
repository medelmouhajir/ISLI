"""In-app notification delivery handler.

Inserts into the notifications table, updates Redis unread cache,
and emits a WebSocket event to the Board UI.
"""

from typing import Any

import structlog
from sqlalchemy import select as sa_select

from isli_core.db import get_db_session_manual
from isli_core.event_manager import EventManager
from isli_core.models import Notification
from isli_core.redis_client import get_redis

logger = structlog.get_logger()

UNREAD_CACHE_TTL = 300  # 5 minutes


async def deliver_in_app(topic: str, payload: dict[str, Any], headers: dict[str, Any]) -> None:
    """Insert notification row, emit WS event, warm unread cache."""
    user_id = payload.get("user_id")
    if not user_id:
        raise ValueError("Missing user_id in notification payload")

    async with get_db_session_manual() as session:
        # Deduplication guard (already checked in engine, but belt-and-suspenders)
        dedup_key = payload.get("dedup_key")
        if dedup_key:
            dup_stmt = sa_select(Notification).where(
                Notification.dedup_key == dedup_key,
                Notification.dismissed_at.is_(None),
            )
            dup_result = await session.execute(dup_stmt)
            if dup_result.scalar_one_or_none():
                logger.debug("delivery.dedup_skip", dedup_key=dedup_key)
                return

        notif = Notification(
            user_id=user_id,
            event_type=payload["event_type"],
            category=payload["category"],
            title=payload["title"],
            body=payload.get("body"),
            payload=payload.get("payload", {}),
            agent_id=payload.get("agent_id"),
            task_id=payload.get("task_id"),
            session_id=payload.get("session_id"),
            dedup_key=dedup_key,
        )
        session.add(notif)
        await session.commit()
        await session.refresh(notif)

        # Emit real-time event to Board UI
        await EventManager.emit(
            "notification:new",
            {
                "notification_id": notif.id,
                "user_id": user_id,
                "event_type": notif.event_type,
                "category": notif.category,
                "title": notif.title,
                "body": notif.body,
                "created_at": notif.created_at.isoformat() if notif.created_at else None,
                "agent_id": notif.agent_id,
                "task_id": notif.task_id,
                "session_id": notif.session_id,
            },
        )

        # Warm Redis unread cache only if key already exists (anti-drift)
        try:
            redis = await get_redis()
            unread_key = f"notif:unread:{user_id}"
            exists = await redis.exists(unread_key)
            if exists:
                await redis.incr(unread_key)
        except Exception as exc:
            logger.warning("delivery.unread_cache_failed", user_id=user_id, error=str(exc))

        logger.info(
            "notification.delivered_in_app",
            notification_id=notif.id,
            user_id=user_id,
            event_type=notif.event_type,
        )
