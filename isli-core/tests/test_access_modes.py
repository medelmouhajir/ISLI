"""Tests for access-mode resolution (opt_in, open, whitelist, closed, scheduled)."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.access import (
    _check_rate_limit,
    _ensure_consent,
    _is_within_schedule,
    _normalize_for_whitelist,
    _require_consent,
    resolve_access,
)
from isli_core.consent import grant_consent
from isli_core.models import Agent, UserConsent


class TestNormalizeForWhitelist:
    def test_plain_jid(self):
        assert _normalize_for_whitelist("1234567890@s.whatsapp.net") == "1234567890"

    def test_device_suffix(self):
        assert _normalize_for_whitelist("1234567890:2@s.whatsapp.net") == "1234567890"

    def test_phone_only(self):
        assert _normalize_for_whitelist("1234567890") == "1234567890"

    def test_lid_suffix(self):
        assert _normalize_for_whitelist("1234567890@lid") == "1234567890"


class TestIsWithinSchedule:
    @patch("isli_core.access.datetime")
    def test_within_hours(self, mock_dt):
        # Monday 10:00 in Casablanca
        mock_now = MagicMock()
        mock_now.weekday.return_value = 0  # Monday
        mock_now.time.return_value = datetime.strptime("10:00", "%H:%M").time()
        mock_now.tzinfo = timezone.utc
        mock_dt.now.return_value = mock_now

        cfg = {
            "timezone": "Africa/Casablanca",
            "windows": [{"days": [1, 2, 3, 4, 5], "from": "09:00", "to": "18:00"}],
        }
        assert _is_within_schedule(cfg) is True

    @patch("isli_core.access.datetime")
    def test_outside_hours(self, mock_dt):
        # Monday 20:00
        mock_now = MagicMock()
        mock_now.weekday.return_value = 0
        mock_now.time.return_value = datetime.strptime("20:00", "%H:%M").time()
        mock_dt.now.return_value = mock_now

        cfg = {
            "timezone": "UTC",
            "windows": [{"days": [1, 2, 3, 4, 5], "from": "09:00", "to": "18:00"}],
        }
        assert _is_within_schedule(cfg) is False

    @patch("isli_core.access.datetime")
    def test_wrong_day(self, mock_dt):
        # Sunday (day 7)
        mock_now = MagicMock()
        mock_now.weekday.return_value = 6  # Sunday
        mock_now.time.return_value = datetime.strptime("10:00", "%H:%M").time()
        mock_dt.now.return_value = mock_now

        cfg = {
            "timezone": "UTC",
            "windows": [{"days": [1, 2, 3, 4, 5], "from": "09:00", "to": "18:00"}],
        }
        assert _is_within_schedule(cfg) is False

    def test_empty_windows(self):
        assert _is_within_schedule({}) is False

    def test_invalid_time_format(self):
        mock_now = MagicMock()
        mock_now.weekday.return_value = 0
        mock_now.time.return_value = datetime.strptime("10:00", "%H:%M").time()
        with patch("isli_core.access.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            cfg = {
                "timezone": "UTC",
                "windows": [{"days": [1], "from": "not-a-time", "to": "18:00"}],
            }
            assert _is_within_schedule(cfg) is False


class TestCheckRateLimit:
    @pytest.mark.asyncio
    async def test_under_limit(self):
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=5)
        redis.expire = AsyncMock()
        await _check_rate_limit("user-1", {"max_msgs": 20, "window_seconds": 3600}, redis)
        redis.incr.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exceeds_limit(self):
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=21)
        redis.expire = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await _check_rate_limit("user-1", {"max_msgs": 20, "window_seconds": 3600}, redis)
        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "rate_limited"

    @pytest.mark.asyncio
    async def test_no_redis(self):
        await _check_rate_limit("user-1", {"max_msgs": 20, "window_seconds": 3600}, None)

    @pytest.mark.asyncio
    async def test_no_config(self):
        redis = AsyncMock()
        await _check_rate_limit("user-1", {}, redis)
        redis.incr.assert_not_awaited()


class TestRequireConsent:
    @pytest.mark.asyncio
    async def test_no_user_id(self, db_session: AsyncSession):
        await _require_consent(db_session, None, "whatsapp")

    @pytest.mark.asyncio
    async def test_has_consent(self, db_session: AsyncSession):
        user_id = "user-consent-1"
        await grant_consent(db_session, user_id, "whatsapp")
        await db_session.commit()
        await _require_consent(db_session, user_id, "whatsapp")

    @pytest.mark.asyncio
    async def test_missing_consent(self, db_session: AsyncSession):
        with pytest.raises(HTTPException) as exc_info:
            await _require_consent(db_session, "user-no-consent", "whatsapp")
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "consent_required"


class TestEnsureConsent:
    @pytest.mark.asyncio
    async def test_already_has_consent(self, db_session: AsyncSession):
        user_id = "user-ensure-1"
        await grant_consent(db_session, user_id, "whatsapp")
        await db_session.commit()
        await _ensure_consent(db_session, user_id, "whatsapp")
        # No error, idempotent

    @pytest.mark.asyncio
    async def test_grants_when_missing(self, db_session: AsyncSession):
        user_id = "user-ensure-2"
        await _ensure_consent(db_session, user_id, "whatsapp")
        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(UserConsent).where(
                UserConsent.user_id == user_id,
                UserConsent.channel == "whatsapp",
                UserConsent.granted == True,
            )
        )
        assert result.scalar_one_or_none() is not None


class TestResolveAccess:
    @pytest.mark.asyncio
    async def test_opt_in_with_consent(self, db_session: AsyncSession):
        agent = Agent(id="agent-optin-1", name="OptIn Agent", config={})
        db_session.add(agent)
        await grant_consent(db_session, "user-optin-ok", "whatsapp")
        await db_session.commit()
        await resolve_access(db_session, "agent-optin-1", "user-optin-ok", "whatsapp")

    @pytest.mark.asyncio
    async def test_opt_in_without_consent(self, db_session: AsyncSession):
        agent = Agent(id="agent-optin-2", name="OptIn Agent", config={})
        db_session.add(agent)
        await db_session.commit()
        with pytest.raises(HTTPException) as exc_info:
            await resolve_access(db_session, "agent-optin-2", "user-optin-no", "whatsapp")
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "consent_required"

    @pytest.mark.asyncio
    async def test_open_auto_grants_consent(self, db_session: AsyncSession):
        agent = Agent(
            id="agent-open-1",
            name="Open Agent",
            config={"whatsapp_access_mode": "open"},
        )
        db_session.add(agent)
        await db_session.commit()
        await resolve_access(db_session, "agent-open-1", "user-open-new", "whatsapp")
        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(UserConsent).where(
                UserConsent.user_id == "user-open-new",
                UserConsent.channel == "whatsapp",
            )
        )
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_open_rate_limit_exceeded(self, db_session: AsyncSession):
        agent = Agent(
            id="agent-open-rl",
            name="Open Agent RL",
            config={
                "whatsapp_access_mode": "open",
                "whatsapp_open_rate_limit": {"max_msgs": 2, "window_seconds": 3600},
            },
        )
        db_session.add(agent)
        await db_session.commit()

        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=3)
        redis.expire = AsyncMock()
        with patch("isli_core.access.get_redis", return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_access(db_session, "agent-open-rl", "user-open-rl", "whatsapp")
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_whitelist_allowed(self, db_session: AsyncSession):
        agent = Agent(
            id="agent-wl-1",
            name="Whitelist Agent",
            config={
                "whatsapp_access_mode": "whitelist",
                "whatsapp_allowed_jids": ["212600000001@s.whatsapp.net"],
            },
        )
        db_session.add(agent)
        await db_session.commit()
        await resolve_access(db_session, "agent-wl-1", "212600000001", "whatsapp")

    @pytest.mark.asyncio
    async def test_whitelist_denied(self, db_session: AsyncSession):
        agent = Agent(
            id="agent-wl-2",
            name="Whitelist Agent",
            config={
                "whatsapp_access_mode": "whitelist",
                "whatsapp_allowed_jids": ["212600000001@s.whatsapp.net"],
            },
        )
        db_session.add(agent)
        await db_session.commit()
        with pytest.raises(HTTPException) as exc_info:
            await resolve_access(db_session, "agent-wl-2", "212699999999", "whatsapp")
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "not_in_whitelist"

    @pytest.mark.asyncio
    async def test_closed_allowed(self, db_session: AsyncSession):
        agent = Agent(
            id="agent-closed-1",
            name="Closed Agent",
            config={
                "whatsapp_access_mode": "closed",
                "whatsapp_allowed_user_id": "212600000001",
            },
        )
        db_session.add(agent)
        await db_session.commit()
        await resolve_access(db_session, "agent-closed-1", "212600000001", "whatsapp")

    @pytest.mark.asyncio
    async def test_closed_denied(self, db_session: AsyncSession):
        agent = Agent(
            id="agent-closed-2",
            name="Closed Agent",
            config={
                "whatsapp_access_mode": "closed",
                "whatsapp_allowed_user_id": "212600000001",
            },
        )
        db_session.add(agent)
        await db_session.commit()
        with pytest.raises(HTTPException) as exc_info:
            await resolve_access(db_session, "agent-closed-2", "212699999999", "whatsapp")
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "closed_mode"

    @pytest.mark.asyncio
    async def test_scheduled_within_hours(self, db_session: AsyncSession):
        agent = Agent(
            id="agent-sched-1",
            name="Scheduled Agent",
            config={
                "whatsapp_access_mode": "scheduled",
                "whatsapp_schedule": {
                    "timezone": "UTC",
                    "windows": [{"days": [1, 2, 3, 4, 5, 6, 7], "from": "00:00", "to": "23:59"}],
                },
            },
        )
        db_session.add(agent)
        await grant_consent(db_session, "user-sched-ok", "whatsapp")
        await db_session.commit()
        await resolve_access(db_session, "agent-sched-1", "user-sched-ok", "whatsapp")

    @pytest.mark.asyncio
    async def test_scheduled_outside_hours(self, db_session: AsyncSession):
        agent = Agent(
            id="agent-sched-2",
            name="Scheduled Agent",
            config={
                "whatsapp_access_mode": "scheduled",
                "whatsapp_schedule": {
                    "timezone": "UTC",
                    "windows": [{"days": [1], "from": "02:00", "to": "04:00"}],
                    "off_hours_reply": "We're closed. Try Mon 2-4am UTC.",
                },
            },
        )
        db_session.add(agent)
        await db_session.commit()

        # Patch datetime to return a time outside the window
        mock_now = MagicMock()
        mock_now.weekday.return_value = 0  # Monday
        mock_now.time.return_value = datetime.strptime("10:00", "%H:%M").time()
        with patch("isli_core.access.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            with pytest.raises(HTTPException) as exc_info:
                await resolve_access(db_session, "agent-sched-2", "user-sched-no", "whatsapp")
            assert exc_info.value.status_code == 403
            assert isinstance(exc_info.value.detail, dict)
            assert exc_info.value.detail["reason"] == "outside_schedule"
            assert exc_info.value.detail["off_hours_reply"] == "We're closed. Try Mon 2-4am UTC."

    @pytest.mark.asyncio
    async def test_missing_agent_fallback_to_consent(self, db_session: AsyncSession):
        with pytest.raises(HTTPException) as exc_info:
            await resolve_access(db_session, "nonexistent-agent", "user-missing", "whatsapp")
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "consent_required"

    @pytest.mark.asyncio
    async def test_no_agent_id_fallback(self, db_session: AsyncSession):
        await grant_consent(db_session, "user-fallback", "whatsapp")
        await db_session.commit()
        await resolve_access(db_session, None, "user-fallback", "whatsapp")
