"""Notification REST API.

Provides inbox CRUD, unread badge count, and preference management.
"""

import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.config import get_settings
from isli_core.db import get_db
from isli_core.models import Notification, NotificationPreference, WebPushSubscription
from isli_core.notification.notification_engine import DEFAULT_CATEGORIES
from isli_core.redis_client import get_redis

logger = structlog.get_logger()
router = APIRouter(prefix="/notifications", tags=["notifications"])

UNREAD_CACHE_TTL = 300  # 5 minutes
AGENT_NOTIFY_RATE_LIMIT = 20  # per agent per user per hour


# ─── Schemas ──────────────────────────────────────────────────────────────────


class NotificationOut(BaseModel):
    id: str
    user_id: str
    event_type: str
    category: str
    title: str
    body: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    read_at: str | None = None
    dismissed_at: str | None = None
    created_at: str
    agent_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None

    @classmethod
    def from_orm(cls, obj: Notification) -> "NotificationOut":
        return cls(
            id=obj.id,
            user_id=obj.user_id,
            event_type=obj.event_type,
            category=obj.category,
            title=obj.title,
            body=obj.body,
            payload=obj.payload or {},
            read_at=obj.read_at.isoformat() if obj.read_at else None,
            dismissed_at=obj.dismissed_at.isoformat() if obj.dismissed_at else None,
            created_at=obj.created_at.isoformat() if obj.created_at else "",
            agent_id=obj.agent_id,
            task_id=obj.task_id,
            session_id=obj.session_id,
        )


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int


class MarkReadIn(BaseModel):
    pass


class NotificationPreferencesOut(BaseModel):
    user_id: str
    global_enabled: bool
    quiet_hours_enabled: bool
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str
    quiet_hours_exceptions: list[str]
    categories: dict[str, Any]


VALID_NOTIFICATION_CHANNELS = {"in_app", "web_push", "telegram", "whatsapp", "email"}


class UpdatePreferencesIn(BaseModel):
    global_enabled: bool | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str | None = None
    quiet_hours_exceptions: list[str] | None = None
    categories: dict[str, Any] | None = None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid timezone: {v}") from exc
        return v

    @field_validator("categories")
    @classmethod
    def _validate_categories(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return v
        for cat_key, cat_val in v.items():
            if not isinstance(cat_val, dict):
                continue
            channels = cat_val.get("channels")
            if channels is not None:
                if not isinstance(channels, list) or not all(isinstance(c, str) for c in channels):
                    raise ValueError(f"Category '{cat_key}': channels must be a list of strings")
                unknown = set(channels) - VALID_NOTIFICATION_CHANNELS
                if unknown:
                    raise ValueError(
                        f"Category '{cat_key}': unknown channels {sorted(unknown)}. "
                        f"Allowed: {sorted(VALID_NOTIFICATION_CHANNELS)}"
                    )
            priority = cat_val.get("priority")
            if priority is not None and priority not in {"critical", "high", "normal", "low"}:
                raise ValueError(
                    f"Category '{cat_key}': priority must be one of critical, high, normal, low"
                )
        return v


class SendNotificationIn(BaseModel):
    user_id: str
    title: str
    message: str = ""
    priority: str = "normal"
    agent_id: str | None = None


class WebPushSubscriptionIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class WebPushPublicKeyOut(BaseModel):
    public_key: str


# ─── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/web-push/public-key", response_model=WebPushPublicKeyOut)
async def get_vapid_public_key():
    """Returns the VAPID public key for frontend subscription."""
    settings = get_settings()
    if not settings.vapid_public_key:
        raise HTTPException(
            status_code=503,
            detail="Web Push is not configured on this server (missing VAPID keys).",
        )
    return WebPushPublicKeyOut(public_key=settings.vapid_public_key)


@router.post("/web-push/subscribe")
async def subscribe_web_push(
    subscription: WebPushSubscriptionIn,
    user_id: str = Query(..., description="The canonical user ID to subscribe"),
    db: AsyncSession = Depends(get_db),
):
    """Register a new web push subscription for a user."""
    # Check if endpoint already exists
    stmt = select(WebPushSubscription).where(WebPushSubscription.endpoint == subscription.endpoint)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.p256dh = subscription.p256dh
        existing.auth = subscription.auth
        existing.user_id = user_id
    else:
        new_sub = WebPushSubscription(
            user_id=user_id,
            endpoint=subscription.endpoint,
            p256dh=subscription.p256dh,
            auth=subscription.auth,
        )
        db.add(new_sub)

    await db.commit()

    # Ensure the user's notification preferences actually include the web_push channel
    pref_stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    pref_result = await db.execute(pref_stmt)
    pref = pref_result.scalar_one_or_none()

    if pref:
        # If user has existing preferences, ensure web_push is in the channel list
        # for enabled categories.
        updated_categories = dict(pref.categories or {})
        changed = False
        for cat_key, cat_val in updated_categories.items():
            if "web_push" not in cat_val.get("channels", []) and (
                "web_push" in DEFAULT_CATEGORIES.get(cat_key, {}).get("channels", [])
            ):
                cat_val["channels"] = cat_val.get("channels", []) + ["web_push"]
                changed = True

        if changed:
            pref.categories = updated_categories
            await db.commit()
            logger.info("web_push.preferences_updated", user_id=user_id)

            # Invalidate cached preferences so the next read picks up web_push
            try:
                redis = await get_redis()
                await redis.delete(f"notif:pref:{user_id}")
            except Exception as exc:
                logger.warning(
                    "web_push.pref_cache_invalidate_failed", user_id=user_id, error=str(exc)
                )

    return {"status": "subscribed"}


@router.delete("/web-push/unsubscribe")
async def unsubscribe_web_push(
    endpoint: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Remove a web push subscription."""
    from sqlalchemy import delete

    # Get user_id before deleting
    stmt = select(WebPushSubscription).where(WebPushSubscription.endpoint == endpoint)
    result = await db.execute(stmt)
    sub = result.scalar_one_or_none()

    if not sub:
        return {"status": "not_found"}

    user_id = sub.user_id

    await db.execute(delete(WebPushSubscription).where(WebPushSubscription.endpoint == endpoint))
    await db.commit()

    # Check if user has any remaining subscriptions
    count_stmt = (
        select(func.count())
        .select_from(WebPushSubscription)
        .where(WebPushSubscription.user_id == user_id)
    )
    count_result = await db.execute(count_stmt)
    remaining_count = count_result.scalar() or 0

    if remaining_count == 0:
        # Remove web_push from preferences
        pref_stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        pref_result = await db.execute(pref_stmt)
        pref = pref_result.scalar_one_or_none()

        if pref:
            updated_categories = dict(pref.categories or {})
            changed = False
            for _cat_key, cat_val in updated_categories.items():
                if "web_push" in cat_val.get("channels", []):
                    cat_val["channels"] = [
                        c for c in cat_val.get("channels", []) if c != "web_push"
                    ]
                    changed = True

            if changed:
                pref.categories = updated_categories
                await db.commit()
                logger.info("web_push.preferences_cleaned", user_id=user_id)

    return {"status": "unsubscribed"}


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    filter_status: str = Query("all", enum=["all", "unread", "read"]),
    event_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> NotificationListOut:
    # In a real system we'd derive user_id from auth. For now use a query param
    # or admin auth fallback. Since ISLI doesn't have a full user auth session in
    # the API yet, we require admin auth and accept ?user_id=...
    # TODO: replace with proper user scoping when auth system matures.
    # For compatibility we skip strict user scoping and return all (admin view).
    stmt = select(Notification).where(Notification.dismissed_at.is_(None))
    if filter_status == "unread":
        stmt = stmt.where(Notification.read_at.is_(None))
    elif filter_status == "read":
        stmt = stmt.where(Notification.read_at.is_not(None))
    if event_type:
        stmt = stmt.where(Notification.event_type == event_type)
    stmt = stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    items = [NotificationOut.from_orm(r) for r in result.scalars().all()]

    total_stmt = (
        select(func.count()).select_from(Notification).where(Notification.dismissed_at.is_(None))
    )
    if filter_status == "unread":
        total_stmt = total_stmt.where(Notification.read_at.is_(None))
    elif filter_status == "read":
        total_stmt = total_stmt.where(Notification.read_at.is_not(None))
    if event_type:
        total_stmt = total_stmt.where(Notification.event_type == event_type)
    total_result = await db.execute(total_stmt)
    total = total_result.scalar() or 0

    unread_stmt = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.read_at.is_(None),
            Notification.dismissed_at.is_(None),
        )
    )
    if event_type:
        unread_stmt = unread_stmt.where(Notification.event_type == event_type)
    unread_result = await db.execute(unread_stmt)
    unread_count = unread_result.scalar() or 0

    return NotificationListOut(items=items, total=total, unread_count=unread_count)


@router.get("/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Return unread notification count. DB is authority; Redis is cache."""
    try:
        redis = await get_redis()
        # Since we don't have a single canonical user_id from auth yet,
        # we return the global unread count for admin overview.
        # In a multi-user system this would be scoped per user.
        cached = await redis.get("notif:unread:global")
        if cached:
            return {"unread_count": int(cached)}
    except Exception as exc:
        logger.warning("notification.unread_redis_failed", error=str(exc))

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.read_at.is_(None),
            Notification.dismissed_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    count = result.scalar() or 0

    try:
        redis = await get_redis()
        await redis.setex("notif:unread:global", UNREAD_CACHE_TTL, str(count))
    except Exception as exc:
        logger.warning("notification.unread_cache_set_failed", error=str(exc))

    return {"unread_count": count}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    now = datetime.now(UTC)
    stmt = (
        update(Notification)
        .where(Notification.id == notification_id)
        .values(read_at=now)
        .returning(Notification.user_id)
    )
    result = await db.execute(stmt)
    user_id = result.scalar_one_or_none()
    await db.commit()

    if user_id:
        try:
            redis = await get_redis()
            unread_key = "notif:unread:global"
            if await redis.exists(unread_key):
                await redis.decr(unread_key)
        except Exception as exc:
            logger.warning("notification.mark_read_cache_failed", error=str(exc))

    return {"ok": True, "notification_id": notification_id}


@router.post("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    now = datetime.now(UTC)
    stmt = (
        update(Notification)
        .where(Notification.read_at.is_(None), Notification.dismissed_at.is_(None))
        .values(read_at=now)
    )
    await db.execute(stmt)
    await db.commit()

    try:
        redis = await get_redis()
        keys = await redis.keys("notif:unread:*")
        for key in keys:
            await redis.delete(key)
        await redis.delete("notif:unread:global")
    except Exception as exc:
        logger.warning("notification.read_all_cache_failed", error=str(exc))

    return {"ok": True}


@router.delete("/{notification_id}")
async def dismiss_notification(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    now = datetime.now(UTC)
    stmt = update(Notification).where(Notification.id == notification_id).values(dismissed_at=now)
    await db.execute(stmt)
    await db.commit()
    return {"ok": True, "notification_id": notification_id}


@router.get("/preferences", response_model=NotificationPreferencesOut)
async def get_preferences(
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> NotificationPreferencesOut:
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        return NotificationPreferencesOut(
            user_id=user_id,
            global_enabled=True,
            quiet_hours_enabled=False,
            timezone="UTC",
            quiet_hours_exceptions=[],
            categories=DEFAULT_CATEGORIES,
        )

    # asyncpg may return JSON columns as strings; guard with json.loads().
    categories = row.categories or DEFAULT_CATEGORIES
    if isinstance(categories, str):
        try:
            categories = json.loads(categories)
        except json.JSONDecodeError:
            logger.warning(
                "notification.pref_categories_json_parse_failed",
                user_id=user_id,
                raw=categories[:200],
            )
            categories = DEFAULT_CATEGORIES

    return NotificationPreferencesOut(
        user_id=row.user_id,
        global_enabled=row.global_enabled,
        quiet_hours_enabled=row.quiet_hours_enabled,
        quiet_hours_start=row.quiet_hours_start.strftime("%H:%M")
        if row.quiet_hours_start
        else None,
        quiet_hours_end=row.quiet_hours_end.strftime("%H:%M") if row.quiet_hours_end else None,
        timezone=row.timezone,
        quiet_hours_exceptions=row.quiet_hours_exceptions or [],
        categories=categories,
    )


@router.patch("/preferences", response_model=NotificationPreferencesOut)
async def update_preferences(
    body: UpdatePreferencesIn,
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> NotificationPreferencesOut:
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )
    row = result.scalar_one_or_none()

    updates: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    if body.global_enabled is not None:
        updates["global_enabled"] = body.global_enabled
    if body.quiet_hours_enabled is not None:
        updates["quiet_hours_enabled"] = body.quiet_hours_enabled
    if body.timezone is not None:
        updates["timezone"] = body.timezone
    if body.quiet_hours_exceptions is not None:
        updates["quiet_hours_exceptions"] = body.quiet_hours_exceptions
    if body.categories is not None:
        updates["categories"] = body.categories
    if body.quiet_hours_start is not None:
        try:
            h, m = body.quiet_hours_start.split(":")
            updates["quiet_hours_start"] = datetime.strptime(body.quiet_hours_start, "%H:%M").time()
        except Exception as exc:
            raise HTTPException(422, f"Invalid quiet_hours_start: {exc}")
    if body.quiet_hours_end is not None:
        try:
            updates["quiet_hours_end"] = datetime.strptime(body.quiet_hours_end, "%H:%M").time()
        except Exception as exc:
            raise HTTPException(422, f"Invalid quiet_hours_end: {exc}")

    if row:
        await db.execute(
            update(NotificationPreference)
            .where(NotificationPreference.user_id == user_id)
            .values(**updates)
        )
    else:
        pref = NotificationPreference(
            user_id=user_id,
            global_enabled=updates.get("global_enabled", True),
            quiet_hours_enabled=updates.get("quiet_hours_enabled", False),
            timezone=updates.get("timezone", "UTC"),
            quiet_hours_exceptions=updates.get("quiet_hours_exceptions", []),
            categories=updates.get("categories", DEFAULT_CATEGORIES),
        )
        if "quiet_hours_start" in updates:
            pref.quiet_hours_start = updates["quiet_hours_start"]
        if "quiet_hours_end" in updates:
            pref.quiet_hours_end = updates["quiet_hours_end"]
        db.add(pref)

    try:
        await db.commit()
    except Exception as exc:
        logger.error("notification.pref_save_failed", user_id=user_id, error=str(exc))
        await db.rollback()
        raise HTTPException(500, f"Failed to save preferences: {exc}") from exc

    # Invalidate Redis cache
    try:
        redis = await get_redis()
        await redis.delete(f"notif:pref:{user_id}")
    except Exception as exc:
        logger.warning("notification.pref_cache_invalidate_failed", user_id=user_id, error=str(exc))

    return await get_preferences(user_id=user_id, db=db)


@router.post("/send")
async def send_notification(
    body: SendNotificationIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Agent-facing endpoint for the notify_user SDK tool.
    Rate-limited per agent per user per hour to prevent runaway spam."""
    try:
        redis = await get_redis()
        rate_key = f"notif:agent_rate:{body.agent_id or 'unknown'}:{body.user_id}"
        count = await redis.incr(rate_key)
        if count == 1:
            await redis.expire(rate_key, 3600)
        if count > AGENT_NOTIFY_RATE_LIMIT:
            raise HTTPException(429, "Notification rate limit exceeded for this agent")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("notification.rate_limit_redis_failed", error=str(exc))

    notif = Notification(
        user_id=body.user_id,
        event_type="agent:proactive",
        category=body.priority,
        title=body.title,
        body=body.message or None,
        agent_id=body.agent_id,
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)

    from isli_core.event_manager import EventManager

    await EventManager.emit(
        "notification:new",
        {
            "notification_id": notif.id,
            "user_id": body.user_id,
            "event_type": "agent:proactive",
            "category": body.priority,
            "title": body.title,
            "body": body.message,
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
            "agent_id": body.agent_id,
        },
    )

    return {"ok": True, "notification_id": notif.id}
