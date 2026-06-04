"""Admin-facing secret vault router for the Board UI."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from structlog import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.auth import require_admin_auth
from isli_core.db import get_db
from isli_core.secrets_service import (
    create_or_update_secret,
    list_secrets,
    delete_secret,
)
from isli_core.audit_writer import AuditWriter

logger = get_logger()
router = APIRouter(prefix="/secrets", tags=["secrets"])


class SecretCreateRequest(BaseModel):
    agent_id: str
    name: str
    value: str
    description: str | None = None


class SecretOut(BaseModel):
    name: str
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@router.post("", response_model=dict[str, Any])
async def create_secret(
    request: SecretCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_auth),
):
    """Create or update a secret for an agent."""
    secret = await create_or_update_secret(
        db, request.agent_id, request.name, request.value, request.description
    )
    await db.commit()
    return {
        "status": "ok",
        "agent_id": request.agent_id,
        "name": secret.name,
        "created_at": secret.created_at.isoformat() if secret.created_at else None,
        "updated_at": secret.updated_at.isoformat() if secret.updated_at else None,
    }


@router.get("", response_model=list[SecretOut])
async def get_secrets(
    agent_id: str = Query(..., description="Agent ID to list secrets for"),
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_auth),
):
    """List secret names and metadata for an agent. Values are never exposed."""
    return await list_secrets(db, agent_id)


@router.delete("/{name}", response_model=dict[str, Any])
async def remove_secret(
    name: str,
    agent_id: str = Query(..., description="Agent ID owning the secret"),
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_auth),
):
    """Delete a secret by name."""
    deleted = await delete_secret(db, agent_id, name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Secret '{name}' not found for agent '{agent_id}'")
    await db.commit()
    return {"status": "deleted", "agent_id": agent_id, "name": name}
