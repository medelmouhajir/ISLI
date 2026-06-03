"""Admin-facing prompts management router for the Board UI.

Reads and writes the shared prompts.yaml file directly.
Uses file mtime for optimistic concurrency control.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from isli_core.audit_writer import AuditWriter
from isli_core.auth import create_internal_token, require_admin_auth
from isli_core.config import get_settings
from isli_core.db import get_db
from isli_core.prompts_loader import clear_prompts_cache

logger = get_logger()
router = APIRouter(prefix="/prompts", tags=["prompts"])


# ── Helpers ────────────────────────────────────────────────────────────


def _resolve_prompts_path() -> Path:
    """Resolve the same path that prompts_loader.py would use."""
    if env_path := os.getenv("PROMPTS_FILE"):
        p = Path(env_path)
        if p.exists():
            return p
    p = Path("/app/prompts.yaml")
    if p.exists():
        return p
    p = Path(__file__).resolve().parent.parent.parent.parent.parent / "prompts.yaml"
    if p.exists():
        return p
    raise FileNotFoundError("prompts.yaml not found")


def _read_prompts_with_mtime() -> tuple[dict[str, Any], float]:
    path = _resolve_prompts_path()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    mtime = path.stat().st_mtime
    return data, mtime


def _write_prompts(data: dict[str, Any]) -> None:
    path = _resolve_prompts_path()
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _merge_prompts(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge incoming into existing. Only overwrite keys that are present
    in incoming. Unknown keys in existing are preserved."""
    merged: dict[str, Any] = {}
    for key, value in existing.items():
        if key in incoming and isinstance(value, dict) and isinstance(incoming[key], dict):
            merged[key] = _merge_prompts(value, incoming[key])
        elif key in incoming:
            merged[key] = incoming[key]
        else:
            merged[key] = value
    # Bring in any new keys from incoming that don't exist in existing
    for key, value in incoming.items():
        if key not in merged:
            merged[key] = value
    return merged


# ── Pydantic models ────────────────────────────────────────────────────


class PromptsOut(BaseModel):
    keeper: dict[str, Any]
    agent: dict[str, Any]
    core: dict[str, Any]
    last_modified: str
    keeper_reloaded: bool = True
    keeper_error: str | None = None


class PromptsUpdate(BaseModel):
    keeper: dict[str, Any] | None = None
    agent: dict[str, Any] | None = None
    core: dict[str, Any] | None = None
    last_modified: str


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("", response_model=PromptsOut)
async def get_prompts(_admin: str = Depends(require_admin_auth)):
    """Read the current prompts.yaml from disk (bypasses cache)."""
    try:
        data, mtime = _read_prompts_with_mtime()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="prompts.yaml not found") from exc

    return PromptsOut(
        keeper=data.get("keeper", {}),
        agent=data.get("agent", {}),
        core=data.get("core", {}),
        last_modified=datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),  # noqa: UP017
    )


@router.put("", response_model=PromptsOut)
async def update_prompts(
    payload: PromptsUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth),
):
    """Merge updates into prompts.yaml, write to disk, and trigger Keeper reload."""
    # 1. Read current file and mtime
    try:
        current, current_mtime = _read_prompts_with_mtime()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="prompts.yaml not found") from exc

    # 2. Optimistic locking: check mtime matches
    expected_mtime = datetime.fromisoformat(payload.last_modified).timestamp()
    if abs(current_mtime - expected_mtime) > 0.001:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Prompts were modified by another process. Please refresh and try again.",
        )

    # 3. Validate required top-level keys exist in current file
    for required in ("keeper", "agent", "core"):
        if required not in current:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"prompts.yaml is missing required section: {required}",
            )

    # 4. Build merged data
    incoming: dict[str, Any] = {}
    if payload.keeper is not None:
        incoming["keeper"] = payload.keeper
    if payload.agent is not None:
        incoming["agent"] = payload.agent
    if payload.core is not None:
        incoming["core"] = payload.core

    merged = _merge_prompts(current, incoming)

    # 5. Write to disk
    try:
        _write_prompts(merged)
    except Exception as exc:
        logger.error("prompts.write_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write prompts.yaml: {exc}",
        ) from exc

    # 6. Clear Core cache
    clear_prompts_cache()

    # 7. Trigger Keeper reload (best-effort)
    keeper_reloaded = False
    keeper_error: str | None = None
    settings = get_settings()
    try:
        token = create_internal_token("core", ["internal"], expires_minutes=1)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.keeper_url}/admin/reload-prompts",
                headers={"X-Internal-Auth": token},
            )
            resp.raise_for_status()
            keeper_reloaded = True
    except Exception as exc:
        keeper_error = str(exc)
        logger.warning("prompts.keeper_reload_failed", error=keeper_error)

    # 8. Audit log
    await AuditWriter.write(
        db,
        actor_type="admin",
        actor_id=_admin,
        action="update_prompts",
        target_type="system",
        target_id="prompts.yaml",
        payload={
            "sections_updated": list(incoming.keys()),
            "keeper_reloaded": keeper_reloaded,
            "keeper_error": keeper_error,
        },
    )
    await db.commit()

    # 9. Read new mtime for response
    _, new_mtime = _read_prompts_with_mtime()

    return PromptsOut(
        keeper=merged.get("keeper", {}),
        agent=merged.get("agent", {}),
        core=merged.get("core", {}),
        last_modified=datetime.fromtimestamp(new_mtime, tz=timezone.utc).isoformat(),  # noqa: UP017
        keeper_reloaded=keeper_reloaded,
        keeper_error=keeper_error,
    )
