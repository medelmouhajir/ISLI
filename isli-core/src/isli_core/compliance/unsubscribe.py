"""CAN-SPAM/TCPA compliance: unsubscribe/opt-out for Email/SMS."""

import structlog
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import UserConsent

logger = structlog.get_logger()


class UnsubscribeManager:
    """Manage opt-out for email and SMS channels."""

    @staticmethod
    async def unsubscribe(session: AsyncSession, user_id: str, channel: str) -> UserConsent:
        """Record an unsubscribe/opt-out for a channel."""
        from isli_core.consent import revoke_consent
        await revoke_consent(session, user_id, channel, purpose="marketing")
        logger.info("unsubscribe.recorded", user_id=user_id, channel=channel)
        return await session.execute(
            select(UserConsent).where(
                UserConsent.user_id == user_id,
                UserConsent.channel == channel,
            )
        ).scalar_one()

    @staticmethod
    async def is_opted_out(session: AsyncSession, user_id: str, channel: str) -> bool:
        """Check if user has opted out of a channel."""
        result = await session.execute(
            select(UserConsent).where(
                UserConsent.user_id == user_id,
                UserConsent.channel == channel,
                UserConsent.purpose == "marketing",
                UserConsent.granted == False,
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def can_send(session: AsyncSession, user_id: str, channel: str) -> bool:
        """Gate: only send if user has not opted out."""
        opted_out = await UnsubscribeManager.is_opted_out(session, user_id, channel)
        if opted_out:
            logger.info("unsubscribe.blocked_send", user_id=user_id, channel=channel)
            return False
        return True

    @staticmethod
    async def generate_unsubscribe_link(user_id: str, channel: str, base_url: str) -> str:
        """Generate a one-click unsubscribe URL."""
        import hmac
        import hashlib
        secret = "change-me-in-production"
        token = hmac.new(secret.encode(), f"{user_id}:{channel}".encode(), hashlib.sha256).hexdigest()[:16]
        return f"{base_url}/unsubscribe?user={user_id}&channel={channel}&token={token}"
