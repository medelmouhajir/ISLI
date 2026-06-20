"""Notification engine: maps events to notifications, resolves recipients,
checks preferences, and stages durable delivery via Outbox.
"""

import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

from isli_core.db import get_db_session_manual
from isli_core.models import (
    Agent,
    Notification,
    NotificationPreference,
    Outbox,
    Task,
)
from isli_core.redis_client import get_redis

logger = structlog.get_logger()

# Default preferences for new users
DEFAULT_CATEGORIES: dict[str, Any] = {
    "agent_crash": {
        "enabled": True,
        "channels": ["in_app", "telegram", "web_push"],
        "priority": "critical",
    },
    "task_completed": {
        "enabled": True,
        "channels": ["in_app", "telegram"],
        "priority": "high",
    },
    "task_failed": {
        "enabled": True,
        "channels": ["in_app", "telegram", "web_push"],
        "priority": "high",
    },
    "task_assigned": {
        "enabled": True,
        "channels": ["in_app"],
        "priority": "high",
    },
    "session_message": {
        "enabled": True,
        "channels": ["in_app", "web_push"],
        "priority": "high",
        "in_app_style": "badge_only",
    },
    "channel_message": {
        "enabled": True,
        "channels": ["in_app", "web_push"],
        "priority": "high",
        "in_app_style": "badge_only",
    },
    "agent_online": {
        "enabled": True,
        "channels": ["in_app"],
        "priority": "normal",
    },
    "agent_offline": {
        "enabled": True,
        "channels": ["in_app", "telegram", "web_push"],
        "priority": "high",
    },
    "memory_write": {
        "enabled": True,
        "channels": ["in_app"],
        "priority": "normal",
    },
    "workspace_update": {
        "enabled": True,
        "channels": ["in_app"],
        "priority": "normal",
    },
    "task_created": {
        "enabled": True,
        "channels": ["in_app"],
        "priority": "normal",
    },
    "system_digest": {
        "enabled": True,
        "channels": ["in_app", "telegram"],
        "priority": "low",
        "digest_window_minutes": 60,
    },
}

# Event types that should be accumulated into digests instead of immediate delivery.
# Currently empty — populate as low-priority background events are added to EVENT_MAP.
digest_eligible_events: set[str] = set()


class NotificationEngine:
    """Maps Redis events to notification Outbox entries."""

    # event_type → {category, title_template, body_template, recipients_field, channels}
    EVENT_MAP: dict[str, dict[str, Any]] = {
        "agent:crash": {
            "category": "critical",
            "title_template": "Agent {agent_name} crashed",
            "body_template": "The agent stopped unexpectedly and recovery failed.",
            "recipients": "agent_owner",
            "channels": ["in_app", "telegram", "web_push"],
        },
        "agent:offline": {
            "category": "high",
            "title_template": "Agent {agent_name} went offline",
            "body_template": "Heartbeat stale. Fallback reassignment triggered.",
            "recipients": "agent_owner",
            "channels": ["in_app", "telegram", "web_push"],
        },
        "task:completed": {
            "category": "high",
            "title_template": "Task completed: {task_title}",
            "body_template": None,
            "recipients": "task_creator",
            "channels": ["in_app", "telegram"],
        },
        "task:failed": {
            "category": "high",
            "title_template": "Task failed: {task_title}",
            "body_template": "Status: {blocked_reason}",
            "recipients": "task_creator",
            "channels": ["in_app", "telegram", "web_push"],
        },
        "task:assigned": {
            "category": "high",
            "title_template": "Task assigned: {task_title}",
            "body_template": "Assigned to agent {agent_name}.",
            "recipients": "task_creator",
            "channels": ["in_app"],
        },
        "task:context_failed": {
            "category": "critical",
            "title_template": "Task context injection failed permanently",
            "body_template": "Task '{task_title}' failed after {attempts} attempts.",
            "recipients": "task_creator",
            "channels": ["in_app", "telegram", "web_push"],
        },
        "session:message": {
            "category": "high",
            "title_template": "New message{channel_suffix} from {sender_name}",
            "body_template": "{last_message_content}",
            "recipients": "alert_target",
            "channels": ["in_app", "web_push"],
        },
        "system:alert": {
            "category": None,  # derived from payload["category"]
            "title_template": None,
            "body_template": "{message}",
            "recipients": "alert_target",
            "channels": ["in_app", "telegram", "web_push"],
        },
    }

    @staticmethod
    async def on_event(event_type: str, payload: dict[str, Any]) -> None:
        """Process a single Redis event."""
        mapping = NotificationEngine.EVENT_MAP.get(event_type)
        if not mapping:
            return

        # Resolve recipients
        recipients = await NotificationEngine._resolve_recipients(event_type, payload, mapping)
        if not recipients:
            logger.debug("notification.no_recipients", event_type=event_type)
            return

        # Determine category
        category = mapping.get("category")
        if category is None and event_type == "system:alert":
            category = _derive_system_alert_category(payload)
        category = category or "normal"

        # Build per-recipient notifications
        for user_id in recipients:
            await NotificationEngine._notify_user(user_id, event_type, payload, mapping, category)

    @staticmethod
    async def _notify_user(
        user_id: str,
        event_type: str,
        payload: dict[str, Any],
        mapping: dict[str, Any],
        category: str,
    ) -> None:
        prefs = await NotificationEngine._get_preferences(user_id)

        # Global kill switch
        if not prefs.get("global_enabled", True):
            return

        # Category-level check
        cat_key = _event_category_key(event_type, payload)
        cat_pref = prefs.get("categories", {}).get(cat_key, {})
        category_enabled = cat_pref.get("enabled", True)

        # Channel messages are always recorded in the in-app activity ledger
        # so the user never loses an inbound message entirely. The per-category
        # toggle controls disruptive/external channels only.
        always_in_app = cat_key == "channel_message"

        if not category_enabled and not always_in_app:
            return

        # Quiet hours (skip for critical)
        if category != "critical" and _in_quiet_hours(prefs):
            exceptions = prefs.get("quiet_hours_exceptions", [])
            if cat_key not in exceptions:
                return

        # Title / body rendering
        title, body = _render(mapping, payload)
        if not title:
            return

        # Low-priority digest accumulation
        if category == "low" and event_type in digest_eligible_events:
            from isli_core.notification.digest import accumulate_digest

            await accumulate_digest(user_id, event_type, payload)
            return

        # Deduplication (24h window for identical events)
        dedup_key = (
            f"{user_id}:{event_type}:"
            f"{payload.get('task_id', '')}:{payload.get('agent_id', '')}:{_today()}"
        )

        # Stage to Outbox for in_app delivery
        # We use the Outbox table for durability; delivery.py handles the actual insert + WS emit
        outbox_payload = {
            "user_id": user_id,
            "event_type": event_type,
            "category": category,
            "title": title,
            "body": body,
            "agent_id": payload.get("agent_id"),
            "task_id": payload.get("task_id"),
            "session_id": payload.get("session_id"),
            "dedup_key": dedup_key,
            "payload": payload,
        }

        try:
            async with get_db_session_manual() as session:
                # Deduplication: skip if identical notification exists today
                if mapping.get("dedup") is not False:
                    from sqlalchemy import select as sa_select

                    dup_stmt = sa_select(Notification).where(
                        Notification.dedup_key == dedup_key,
                        Notification.dismissed_at.is_(None),
                    )
                    dup_result = await session.execute(dup_stmt)
                    if dup_result.scalar_one_or_none():
                        logger.debug("notification.dedup_skip", dedup_key=dedup_key)
                        return

                outbox = Outbox(
                    topic="notification:in_app",
                    payload=outbox_payload,
                    headers={"user_id": user_id, "category": category},
                )
                session.add(outbox)

                # Stage external delivery only when the category is explicitly enabled.
                # For channel_message, disabling the category suppresses push/external
                # noise while still leaving the drawer entry above.
                if category_enabled:
                    external_channels = _external_channels_for_event(cat_pref)
                    if external_channels:
                        for channel in external_channels:
                            topic = "notification:external"
                            if channel == "web_push":
                                topic = "notification:web_push"

                            ext_payload = {
                                **outbox_payload,
                                "channels": [channel],
                            }
                            ext_outbox = Outbox(
                                topic=topic,
                                payload=ext_payload,
                                headers={"user_id": user_id, "category": category},
                            )
                            session.add(ext_outbox)

                await session.commit()
                logger.info(
                    "notification.staged", user_id=user_id, event_type=event_type, category=category
                )
        except Exception as exc:
            logger.error(
                "notification.stage_failed", user_id=user_id, event_type=event_type, error=str(exc)
            )

    @staticmethod
    async def _resolve_recipients(
        event_type: str, payload: dict[str, Any], mapping: dict[str, Any]
    ) -> list[str]:
        recipients_field = mapping.get("recipients")
        recipients: list[str] = []

        try:
            async with get_db_session_manual() as session:
                if recipients_field == "agent_owner":
                    agent_id = payload.get("agent_id")
                    if agent_id:
                        from sqlalchemy import select as sa_select

                        result = await session.execute(sa_select(Agent).where(Agent.id == agent_id))
                        agent = result.scalar_one_or_none()
                        if agent and agent.user_id:
                            recipients.append(agent.user_id)

                elif recipients_field == "task_creator":
                    task_id = payload.get("task_id")
                    if not task_id and "task" in payload:
                        task_id = payload["task"].get("id")
                    if task_id:
                        from sqlalchemy import select as sa_select

                        result = await session.execute(sa_select(Task).where(Task.id == task_id))
                        task = result.scalar_one_or_none()
                        if task:
                            recipients.append(task.created_by)

                elif recipients_field == "alert_target":
                    user_id = payload.get("user_id")
                    agent_id = payload.get("agent_id")
                    if user_id:
                        recipients.append(user_id)
                    elif agent_id:
                        from sqlalchemy import select as sa_select

                        result = await session.execute(sa_select(Agent).where(Agent.id == agent_id))
                        agent = result.scalar_one_or_none()
                        if agent and agent.user_id:
                            recipients.append(agent.user_id)
        except Exception as exc:
            logger.error(
                "notification.resolve_recipients_failed", event_type=event_type, error=str(exc)
            )

        return recipients

    @staticmethod
    async def _get_preferences(user_id: str) -> dict[str, Any]:
        """Fetch preferences from Redis cache or DB, with 1h TTL."""
        try:
            redis = await get_redis()
            cache_key = f"notif:pref:{user_id}"
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

        prefs: dict[str, Any] = {
            "global_enabled": True,
            "quiet_hours_enabled": False,
            "categories": DEFAULT_CATEGORIES,
        }

        try:
            async with get_db_session_manual() as session:
                from sqlalchemy import select as sa_select

                result = await session.execute(
                    sa_select(NotificationPreference).where(
                        NotificationPreference.user_id == user_id
                    )
                )
                row = result.scalar_one_or_none()
                if row:
                    prefs = {
                        "global_enabled": row.global_enabled,
                        "quiet_hours_enabled": row.quiet_hours_enabled,
                        "quiet_hours_start": row.quiet_hours_start.isoformat()
                        if row.quiet_hours_start
                        else None,
                        "quiet_hours_end": row.quiet_hours_end.isoformat()
                        if row.quiet_hours_end
                        else None,
                        "timezone": row.timezone,
                        "quiet_hours_exceptions": row.quiet_hours_exceptions or [],
                        "categories": row.categories or DEFAULT_CATEGORIES,
                    }
        except Exception as exc:
            logger.warning("notification.pref_fetch_failed", user_id=user_id, error=str(exc))

        try:
            redis = await get_redis()
            await redis.setex(f"notif:pref:{user_id}", 3600, json.dumps(prefs))
        except Exception:
            pass

        return prefs


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _event_category_key(event_type: str, payload: dict[str, Any] | None = None) -> str:
    mapping = {
        "agent:crash": "agent_crash",
        "agent:offline": "agent_offline",
        "agent:online": "agent_online",
        "task:completed": "task_completed",
        "task:failed": "task_failed",
        "task:assigned": "task_assigned",
        "task:context_failed": "agent_crash",  # treated as critical
        "system:alert": "system_alert",
    }
    if event_type == "session:message":
        channel = (payload or {}).get("channel") if payload else None
        if channel and channel != "web":
            return "channel_message"
        return "session_message"
    return mapping.get(event_type, event_type.replace(":", "_"))


def _derive_system_alert_category(payload: dict[str, Any]) -> str:
    cat = payload.get("category", "")
    if cat in ("agent_crash", "task_context_failed"):
        return "critical"
    if cat == "budget_threshold":
        return "high"
    return "normal"


def _render(mapping: dict[str, Any], payload: dict[str, Any]) -> tuple[str, str | None]:
    title_tpl = mapping.get("title_template")
    body_tpl = mapping.get("body_template")

    # For system:alert, title comes from severity + message
    if title_tpl is None and payload.get("message"):
        severity = payload.get("severity", "info")
        title = f"[{severity.upper()}] {payload['message'][:80]}"
    elif title_tpl:
        try:
            title = title_tpl.format(**_flatten_payload(payload))
        except (KeyError, ValueError):
            title = title_tpl
    else:
        title = payload.get("message", "Notification")

    body = None
    if body_tpl:
        try:
            body = body_tpl.format(**_flatten_payload(payload))
        except Exception:
            body = body_tpl
    elif payload.get("message") and title != payload["message"]:
        body = payload["message"]

    return title, body


def _flatten_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract scalar fields from payload and nested task dict for template rendering.

    Also injects a human-readable ``channel_suffix`` for notification titles.
    """
    flat: dict[str, Any] = dict(payload)
    if "task" in payload and isinstance(payload["task"], dict):
        for k, v in payload["task"].items():
            flat.setdefault(k, v)
    if "agent" in payload and isinstance(payload["agent"], dict):
        for k, v in payload["agent"].items():
            flat.setdefault(k, v)

    # Extract session message details if present
    messages = payload.get("messages", [])
    if messages and isinstance(messages, list):
        latest = messages[-1]
        if isinstance(latest, dict):
            flat["last_message_content"] = latest.get("content", "")
            flat["last_message_role"] = latest.get("role", "")
    elif "message" in payload and isinstance(payload["message"], dict):
        latest = payload["message"]
        flat["last_message_content"] = latest.get("content", "")
        flat["last_message_role"] = latest.get("role", "")

    flat.setdefault("last_message_content", "")
    flat.setdefault("last_message_role", "user")

    sender_name = payload.get("user_id") or "User"
    flat["sender_name"] = sender_name

    channel = payload.get("channel")
    if channel and channel != "web":
        flat["channel_suffix"] = f" on {channel.capitalize()}"
    else:
        flat["channel_suffix"] = ""
    return flat


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _external_channels_for_event(cat_pref: dict[str, Any]) -> list[str]:
    """Return enabled external channels (non in_app) from category preferences."""
    channels = cat_pref.get("channels", [])
    return [c for c in channels if c != "in_app"]


def _in_quiet_hours(prefs: dict[str, Any]) -> bool:
    if not prefs.get("quiet_hours_enabled", False):
        return False
    tz_str = prefs.get("timezone", "UTC")
    try:
        tz = ZoneInfo(tz_str)
    except ZoneInfoNotFoundError:
        return False
    now = datetime.now(tz)
    start_str = prefs.get("quiet_hours_start")
    end_str = prefs.get("quiet_hours_end")
    if not start_str or not end_str:
        return False
    try:
        start = (
            datetime.strptime(start_str, "%H:%M:%S").time()
            if isinstance(start_str, str)
            else start_str
        )
        end = datetime.strptime(end_str, "%H:%M:%S").time() if isinstance(end_str, str) else end_str
    except Exception:
        return False
    now_time = now.time()
    if start < end:
        return start <= now_time <= end
    else:
        return now_time >= start or now_time <= end
