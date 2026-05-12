from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import UserConsent


class ConsentRequiredError(HTTPException):
    def __init__(self, user_id: str, channel: str):
        super().__init__(
            status_code=403,
            detail=f"User {user_id} on channel {channel} has not given consent",
        )


async def check_consent(session: AsyncSession, user_id: str, channel: str, purpose: str = "default") -> bool:
    result = await session.execute(
        select(UserConsent).where(
            UserConsent.user_id == user_id,
            UserConsent.channel == channel,
            UserConsent.purpose == purpose,
            UserConsent.granted == True,
            UserConsent.revoked_at.is_(None),
        )
    )
    consent = result.scalar_one_or_none()
    return consent is not None


async def require_consent(session: AsyncSession, user_id: str, channel: str, purpose: str = "default") -> None:
    if not await check_consent(session, user_id, channel, purpose):
        raise ConsentRequiredError(user_id, channel)


async def grant_consent(session: AsyncSession, user_id: str, channel: str, purpose: str = "default") -> UserConsent:
    result = await session.execute(
        select(UserConsent).where(
            UserConsent.user_id == user_id,
            UserConsent.channel == channel,
            UserConsent.purpose == purpose,
        )
    )
    consent = result.scalar_one_or_none()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if consent is None:
        consent = UserConsent(
            user_id=user_id,
            channel=channel,
            purpose=purpose,
            granted=True,
            granted_at=now,
        )
        session.add(consent)
    else:
        consent.granted = True
        consent.granted_at = now
        consent.revoked_at = None
    await session.flush()
    return consent


async def revoke_consent(session: AsyncSession, user_id: str, channel: str, purpose: str = "default") -> None:
    from datetime import datetime, timezone
    result = await session.execute(
        select(UserConsent).where(
            UserConsent.user_id == user_id,
            UserConsent.channel == channel,
            UserConsent.purpose == purpose,
        )
    )
    consent = result.scalar_one_or_none()
    if consent:
        consent.granted = False
        consent.revoked_at = datetime.now(timezone.utc)
        await session.flush()
