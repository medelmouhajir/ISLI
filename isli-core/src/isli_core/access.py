"""Access-mode resolution for channel webhooks.

Supports five modes per agent (stored in Agent.config JSONB):
  opt_in    — user must /start first (default, backward compatible)
  open      — auto-consent, with optional per-JID rate limiting
  whitelist — only configured JIDs/phone numbers allowed
  closed    — exactly one allowed JID/phone number
  scheduled — time-window gated; falls through to opt_in consent within hours
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from isli_core.consent import check_consent, grant_consent
from isli_core.models import Agent
from isli_core.redis_client import get_redis

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def resolve_access(
    db: AsyncSession,
    agent_id: str | None,
    user_id: str | None,
    channel: str,
) -> None:
    """Raise HTTPException if access is denied; return silently if allowed.

    When *agent_id* is present we look up the agent config and branch by
    ``whatsapp_access_mode``.  When it is missing we fall back to the legacy
    consent-only gate.
    """
    if not agent_id:
        # Fallback path (no agent) — keep existing flat consent behaviour
        await _require_consent(db, user_id, channel)
        return

    agent = await db.get(Agent, agent_id)
    if not agent:
        # Treat missing agent as opt_in for safety
        await _require_consent(db, user_id, channel)
        return

    cfg = agent.config or {}
    mode = cfg.get("whatsapp_access_mode", "opt_in")

    redis = await get_redis()

    if mode == "open":
        await _check_rate_limit(user_id or "", cfg.get("whatsapp_open_rate_limit", {}), redis)
        await _ensure_consent(db, user_id, channel)
        return

    if mode == "whitelist":
        allowed_raw = cfg.get("whatsapp_allowed_jids", [])
        allowed = {_normalize_for_whitelist(j) for j in allowed_raw}
        if (user_id or "") not in allowed:
            raise HTTPException(status_code=403, detail="not_in_whitelist")
        await _ensure_consent(db, user_id, channel)
        return

    if mode == "closed":
        allowed = cfg.get("whatsapp_allowed_user_id")
        if (user_id or "") != allowed:
            raise HTTPException(status_code=403, detail="closed_mode")
        await _ensure_consent(db, user_id, channel)
        return

    if mode == "scheduled":
        schedule = cfg.get("whatsapp_schedule", {})
        if not _is_within_schedule(schedule):
            off_hours_reply = schedule.get(
                "off_hours_reply",
                "This assistant is currently offline. Please try again during business hours.",
            )
            raise HTTPException(
                status_code=403,
                detail={"reason": "outside_schedule", "off_hours_reply": off_hours_reply},
            )
        # Falls through to opt_in consent check below

    # opt_in (default) and scheduled within hours both require explicit consent
    await _require_consent(db, user_id, channel)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_consent(db: AsyncSession, user_id: str | None, channel: str) -> None:
    if user_id is None:
        return
    has = await check_consent(db, user_id, channel)
    if not has:
        raise HTTPException(status_code=403, detail="consent_required")


async def _ensure_consent(db: AsyncSession, user_id: str | None, channel: str) -> None:
    """Idempotently grant consent if missing."""
    if user_id is None:
        return
    has = await check_consent(db, user_id, channel)
    if not has:
        await grant_consent(db, user_id, channel)
        await db.commit()


async def _check_rate_limit(
    user_id: str,
    rl_cfg: dict,
    redis: Redis | None,
) -> None:
    """Sliding-window rate limit backed by Redis.

    Config shape::

        {"max_msgs": 20, "window_seconds": 3600}
    """
    if not redis or not rl_cfg:
        return

    max_msgs = rl_cfg.get("max_msgs")
    window_seconds = rl_cfg.get("window_seconds")
    if not max_msgs or not window_seconds:
        return

    # Use a fixed-window counter with TTL for simplicity.
    # Key expires automatically when the window elapses.
    key = f"rate_limit:{user_id}:{window_seconds}"
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, window_seconds)
    if current > max_msgs:
        raise HTTPException(status_code=429, detail="rate_limited")


def _is_within_schedule(schedule_cfg: dict) -> bool:
    """Return True if current local time falls inside any configured window.

    Config shape::

        {
          "timezone": "Africa/Casablanca",
          "windows": [
            {"days": [1,2,3,4,5], "from": "09:00", "to": "18:00"}
          ]
        }

    *days* are 1-based: 1=Monday … 7=Sunday.
    """
    tz_name = schedule_cfg.get("timezone", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        logger.warning("access.unknown_timezone", timezone=tz_name, fallback="UTC")
        tz = ZoneInfo("UTC")

    now = datetime.now(tz)
    weekday = now.weekday()  # 0=Monday … 6=Sunday
    # Convert to 1-based for comparison with config
    day_number = weekday + 1

    for window in schedule_cfg.get("windows", []):
        days = window.get("days", [])
        if day_number not in days:
            continue
        try:
            from_str = window.get("from", "00:00")
            to_str = window.get("to", "23:59")
            from_time = time.fromisoformat(from_str)
            to_time = time.fromisoformat(to_str)
        except ValueError:
            logger.warning("access.invalid_time_window", window=window)
            continue

        now_time = now.time()
        if from_time <= now_time <= to_time:
            return True

    return False


def _normalize_for_whitelist(value: str) -> str:
    """Strip ``@domain`` and ``:device`` suffix from a JID / phone number."""
    return value.split("@")[0].split(":")[0]
