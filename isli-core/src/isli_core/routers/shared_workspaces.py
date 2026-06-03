from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.audit_writer import AuditWriter
from isli_core.auth import create_internal_token, verify_internal_token
from isli_core.config import get_settings
from isli_core.db import get_db
from isli_core.models import SharedWorkspace


async def _resolve_caller(request: Request) -> dict[str, Any]:
    """Accept admin API key or internal JWT. Returns caller type and agent_id."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = auth[7:]
    settings = get_settings()
    if token == settings.admin_api_key:
        return {"type": "admin", "agent_id": None}
    payload = verify_internal_token(token)
    from isli_core.auth import _check_token_revocation
    await _check_token_revocation(payload)
    return {"type": "agent", "agent_id": payload.get("sub")}

router = APIRouter(prefix="/shared-workspaces", tags=["shared-workspaces"])


class SharedWorkspaceCreate(BaseModel):
    name: str
    description: str | None = None
    owner_id: str
    members: list[str] = []
    quota_bytes: int = 524288000 # 500MB


class SharedWorkspaceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    members: list[str] | None = None
    quota_bytes: int | None = None


class SharedWorkspaceOut(BaseModel):
    id: str
    name: str
    description: str | None
    owner_id: str
    members: list[str]
    quota_bytes: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromoteRequest(BaseModel):
    agent_id: str
    source_scope: str
    source_scope_id: str
    source_path: str
    target_path: str
    delete_source: bool = False
    quota_bytes: int | None = None


@router.get("", response_model=list[SharedWorkspaceOut])
async def list_shared_workspaces(
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    caller: dict[str, Any] = Depends(_resolve_caller)
):
    stmt = select(SharedWorkspace).where(SharedWorkspace.deleted_at.is_(None))
    result = await db.execute(stmt)
    workspaces = result.scalars().all()

    effective_agent_id = agent_id or caller.get("agent_id")
    is_admin = caller["type"] == "admin"

    if is_admin:
        return workspaces

    # Restrict to workspaces the caller owns or is a member of
    return [
        w for w in workspaces
        if effective_agent_id and (
            effective_agent_id == w.owner_id or effective_agent_id in w.members
        )
    ]


@router.post("", response_model=SharedWorkspaceOut, status_code=201)
async def create_shared_workspace(
    payload: SharedWorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    caller: dict[str, Any] = Depends(_resolve_caller)
):
    is_admin = caller["type"] == "admin"
    agent_id = caller.get("agent_id")

    # Non-admin can only create workspaces they own
    if not is_admin and agent_id != payload.owner_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot create a workspace for another agent",
        )

    workspace = SharedWorkspace(
        name=payload.name,
        description=payload.description,
        owner_id=payload.owner_id,
        members=payload.members,
        quota_bytes=payload.quota_bytes
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)

    await AuditWriter.write(
        db,
        actor_type="system",
        actor_id=caller.get("agent_id") or "core-api",
        action="create_shared_workspace",
        target_type="shared_workspace",
        target_id=workspace.id,
        payload={"name": workspace.name, "owner_id": workspace.owner_id},
    )
    await db.commit()

    return workspace


@router.get("/{workspace_id}", response_model=SharedWorkspaceOut)
async def get_shared_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    caller: dict[str, Any] = Depends(_resolve_caller)
):
    result = await db.execute(
        select(SharedWorkspace).where(
            SharedWorkspace.id == workspace_id,
            SharedWorkspace.deleted_at.is_(None)
        )
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Shared workspace not found")

    is_admin = caller["type"] == "admin"
    agent_id = caller.get("agent_id")
    if not is_admin and agent_id != workspace.owner_id and agent_id not in workspace.members:
        raise HTTPException(
            status_code=403, detail="Access denied to this shared workspace"
        )

    return workspace


@router.put("/{workspace_id}", response_model=SharedWorkspaceOut)
async def update_shared_workspace(
    workspace_id: str,
    payload: SharedWorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    caller: dict[str, Any] = Depends(_resolve_caller)
):
    result = await db.execute(
        select(SharedWorkspace).where(
            SharedWorkspace.id == workspace_id,
            SharedWorkspace.deleted_at.is_(None)
        )
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Shared workspace not found")

    is_admin = caller["type"] == "admin"
    agent_id = caller.get("agent_id")
    if not is_admin and agent_id != workspace.owner_id:
        raise HTTPException(
            status_code=403, detail="Only the workspace owner or an admin can update this workspace"
        )

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(workspace, field, value)

    workspace.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(workspace)

    await AuditWriter.write(
        db,
        actor_type="system",
        actor_id=caller.get("agent_id") or "core-api",
        action="update_shared_workspace",
        target_type="shared_workspace",
        target_id=workspace.id,
        payload=changes,
    )
    await db.commit()

    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shared_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    caller: dict[str, Any] = Depends(_resolve_caller)
):
    result = await db.execute(
        select(SharedWorkspace).where(
            SharedWorkspace.id == workspace_id,
            SharedWorkspace.deleted_at.is_(None)
        )
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Shared workspace not found")

    is_admin = caller["type"] == "admin"
    agent_id = caller.get("agent_id")
    if not is_admin and agent_id != workspace.owner_id:
        raise HTTPException(
            status_code=403,
            detail="Only the workspace owner or an admin can delete this workspace",
        )

    workspace.deleted_at = datetime.now(UTC)
    await db.commit()

    await AuditWriter.write(
        db,
        actor_type="system",
        actor_id=caller.get("agent_id") or "core-api",
        action="delete_shared_workspace",
        target_type="shared_workspace",
        target_id=workspace_id,
    )
    await db.commit()
    return


@router.post("/{workspace_id}/members/{member_id}", response_model=SharedWorkspaceOut)
async def add_member(
    workspace_id: str,
    member_id: str,
    db: AsyncSession = Depends(get_db),
    caller: dict[str, Any] = Depends(_resolve_caller)
):
    result = await db.execute(
        select(SharedWorkspace).where(
            SharedWorkspace.id == workspace_id,
            SharedWorkspace.deleted_at.is_(None)
        )
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Shared workspace not found")

    is_admin = caller["type"] == "admin"
    agent_id = caller.get("agent_id")
    if not is_admin and agent_id != workspace.owner_id:
        raise HTTPException(
            status_code=403,
            detail="Only the workspace owner or an admin can add members",
        )

    current_members = list(workspace.members or [])
    if member_id not in current_members:
        current_members.append(member_id)
        workspace.members = current_members
        workspace.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(workspace)

        await AuditWriter.write(
            db,
            actor_type="system",
            actor_id=caller.get("agent_id") or "core-api",
            action="add_member",
            target_type="shared_workspace",
            target_id=workspace_id,
            payload={"member_id": member_id},
        )
        await db.commit()

    return workspace


@router.delete("/{workspace_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: str,
    member_id: str,
    db: AsyncSession = Depends(get_db),
    caller: dict[str, Any] = Depends(_resolve_caller)
):
    result = await db.execute(
        select(SharedWorkspace).where(
            SharedWorkspace.id == workspace_id,
            SharedWorkspace.deleted_at.is_(None)
        )
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Shared workspace not found")

    is_admin = caller["type"] == "admin"
    agent_id = caller.get("agent_id")
    if not is_admin and agent_id != workspace.owner_id:
        raise HTTPException(
            status_code=403,
            detail="Only the workspace owner or an admin can remove members",
        )

    current_members = list(workspace.members or [])
    if member_id in current_members:
        current_members.remove(member_id)
        workspace.members = current_members
        workspace.updated_at = datetime.now(UTC)
        await db.commit()

        await AuditWriter.write(
            db,
            actor_type="system",
            actor_id=caller.get("agent_id") or "core-api",
            action="remove_member",
            target_type="shared_workspace",
            target_id=workspace_id,
            payload={"member_id": member_id},
        )
        await db.commit()
    return


@router.post("/{workspace_id}/promote", response_model=dict)
async def promote_to_shared(
    workspace_id: str,
    payload: PromoteRequest,
    db: AsyncSession = Depends(get_db),
    caller: dict[str, Any] = Depends(_resolve_caller)
):
    """Proxy file promotion to shared workspace."""
    result = await db.execute(
        select(SharedWorkspace).where(
            SharedWorkspace.id == workspace_id,
            SharedWorkspace.deleted_at.is_(None)
        )
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Shared workspace not found")

    is_admin = caller["type"] == "admin"
    agent_id = caller.get("agent_id")
    if not is_admin and agent_id != workspace.owner_id and agent_id not in workspace.members:
        raise HTTPException(
            status_code=403,
            detail="Access denied to this shared workspace",
        )

    settings = get_settings()
    url = f"{settings.workspace_url}/shared/promote"
    token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=1)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json={
                "agent_id": payload.agent_id,
                "source_scope": payload.source_scope,
                "source_scope_id": payload.source_scope_id,
                "source_path": payload.source_path,
                "target_workspace_id": workspace_id,
                "target_path": payload.target_path,
                "delete_source": payload.delete_source,
                "quota_bytes": (
                    payload.quota_bytes
                    if payload.quota_bytes is not None
                    else workspace.quota_bytes
                )
            },
            headers={"X-Internal-Auth": f"Bearer {token}"}
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

    await AuditWriter.write(
        db,
        actor_type="agent",
        agent_id=payload.agent_id,
        action="promote_to_shared",
        target_type="shared_workspace",
        target_id=workspace_id,
        payload={
            "source_scope": payload.source_scope,
            "source_path": payload.source_path,
            "target_path": payload.target_path,
        },
    )
    await db.commit()

    return {"status": "ok"}
