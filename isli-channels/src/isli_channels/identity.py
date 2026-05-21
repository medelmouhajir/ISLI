import structlog
from typing import Any

logger = structlog.get_logger()


class CrossChannelIdentity:
    """Manage user identity linking across Telegram, WhatsApp, Web, Email."""

    @staticmethod
    async def resolve_or_create(
        session: Any,
        channel: str,
        channel_user_id: str,
        display_name: str | None = None,
    ) -> Any:
        from sqlalchemy import select
        from isli_core.models import UserProfile

        identity_key = f"{channel}:{channel_user_id}"
        result = await session.execute(
            select(UserProfile).where(
                UserProfile.identities.contains({channel: channel_user_id})
            )
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = UserProfile(
                canonical_user_id=identity_key,
                display_name=display_name or channel_user_id,
                identities={channel: channel_user_id},
            )
            session.add(profile)
            await session.flush()
            logger.info("identity.created", channel=channel, user_id=channel_user_id)
        return profile

    @staticmethod
    async def link_identity(
        session: Any,
        canonical_user_id: str,
        channel: str,
        channel_user_id: str,
    ) -> Any | None:
        from sqlalchemy import select
        from isli_core.models import UserProfile

        result = await session.execute(
            select(UserProfile).where(UserProfile.canonical_user_id == canonical_user_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return None
        identities = dict(profile.identities)
        identities[channel] = channel_user_id
        profile.identities = identities
        await session.flush()
        logger.info("identity.linked", canonical=canonical_user_id, channel=channel)
        return profile

    @staticmethod
    async def verify_identity(
        session: Any,
        canonical_user_id: str,
        channel: str,
        verification_code: str,
    ) -> bool:
        from sqlalchemy import select
        from isli_core.models import UserProfile

        result = await session.execute(
            select(UserProfile).where(UserProfile.canonical_user_id == canonical_user_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return False
        profile.verified = True
        await session.flush()
        logger.info("identity.verified", canonical=canonical_user_id)
        return True

    @staticmethod
    async def get_identities(session: Any, canonical_user_id: str) -> dict:
        from sqlalchemy import select
        from isli_core.models import UserProfile

        result = await session.execute(
            select(UserProfile).where(UserProfile.canonical_user_id == canonical_user_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return {}
        return dict(profile.identities)
