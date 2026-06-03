"""Dynamic configuration helper with in-memory TTL cache."""

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import SystemSetting

_cache: dict[tuple[str, str], tuple[Any, float]] = {}
_cache_ttl_seconds = 30.0


async def get_setting(
    session: AsyncSession,
    key: str,
    scope: str = "global",
    default: Any = None,
) -> Any:
    """Read a setting from the DB with a short in-memory cache."""
    cache_key = (key, scope)
    now = asyncio.get_event_loop().time()
    if cache_key in _cache:
        value, expires = _cache[cache_key]
        if now < expires:
            return value

    result = await session.execute(
        select(SystemSetting).where(
            SystemSetting.key == key,
            SystemSetting.scope == scope,
        )
    )
    row = result.scalar_one_or_none()
    value = row.value if row else default
    _cache[cache_key] = (value, now + _cache_ttl_seconds)
    return value


def invalidate_cache(key: str | None = None, scope: str | None = None) -> None:
    """Invalidate cache entries. Called by PUT/DELETE handlers."""
    global _cache
    if key is None and scope is None:
        _cache.clear()
        return
    to_remove = [
        k for k in _cache
        if (key is None or k[0] == key) and (scope is None or k[1] == scope)
    ]
    for k in to_remove:
        _cache.pop(k, None)
