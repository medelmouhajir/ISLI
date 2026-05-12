"""Override store — manage policy override requests and grants."""

from datetime import datetime, timezone, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import PolicyOverride

logger = structlog.get_logger()


class OverrideStore:
    """Create and query policy overrides."""

    @staticmethod
    async def request(
        session: AsyncSession,
        user_id: str,
        rule: str,
        context_hash: str,
    ) -> PolicyOverride:
        override = PolicyOverride(
            user_id=user_id,
            rule=rule,
            context_hash=context_hash,
            granted=False,
        )
        session.add(override)
        await session.flush()
        logger.info("override.requested", override_id=override.id, user_id=user_id, rule=rule)
        return override

    @staticmethod
    async def grant(
        session: AsyncSession,
        override_id: str,
        granted_by: str,
        expires_minutes: int = 60,
    ) -> PolicyOverride | None:
        result = await session.execute(
            select(PolicyOverride).where(PolicyOverride.id == override_id)
        )
        override = result.scalar_one_or_none()
        if not override:
            return None
        override.granted = True
        override.granted_by = granted_by
        override.expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        await session.flush()
        logger.info("override.granted", override_id=override_id, granted_by=granted_by)
        return override

    @staticmethod
    async def get(session: AsyncSession, override_id: str) -> PolicyOverride | None:
        result = await session.execute(
            select(PolicyOverride).where(PolicyOverride.id == override_id)
        )
        return result.scalar_one_or_none()
