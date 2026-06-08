"""Seed default SystemSetting rows on startup so the Board UI has values."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.db import get_db_session_manual
from isli_core.models import SystemSetting


DEFAULT_SETTINGS: list[dict] = [
    {
        "key": "pii_mesh_default_enabled",
        "scope": "system",
        "value": False,
        "description": "Default pii_mesh_enabled for newly created agents.",
    },
    {
        "key": "pii_use_slm_default",
        "scope": "system",
        "value": False,
        "description": "Default pii_use_slm for newly created agents.",
    },
    {
        "key": "pii_regex_pre_filter",
        "scope": "system",
        "value": True,
        "description": "Enable fast regex pre-filter before SLM inference.",
    },
    {
        "key": "pii_token_ttl_hours",
        "scope": "system",
        "value": 24,
        "description": "How long PII token maps are retained in Keeper vault.",
    },
    {
        "key": "keeper_timeout_seconds",
        "scope": "system",
        "value": 180,
        "description": "HTTP timeout for calls to the Keeper sidecar.",
    },
    {
        "key": "agent_spawn_timeout_seconds",
        "scope": "system",
        "value": 120,
        "description": "Seconds to wait for a new agent container to become healthy.",
    },
]


async def seed_default_settings() -> None:
    """Upsert default system settings if they do not already exist."""
    async with get_db_session_manual() as db:
        for item in DEFAULT_SETTINGS:
            result = await db.execute(
                select(SystemSetting).where(
                    SystemSetting.key == item["key"],
                    SystemSetting.scope == item["scope"],
                )
            )
            if result.scalar_one_or_none() is None:
                row = SystemSetting(
                    key=item["key"],
                    scope=item["scope"],
                    value=item["value"],
                    description=item["description"],
                    updated_at=datetime.now(timezone.utc),
                    updated_by="system_seed",
                )
                db.add(row)
        await db.commit()
