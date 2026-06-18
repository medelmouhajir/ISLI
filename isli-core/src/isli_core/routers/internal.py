from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.auth import create_internal_token, verify_internal_token
from isli_core.config import get_settings
from isli_core.db import get_db
from isli_core.models import SharedWorkspace, Task

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_service_auth(request: Request) -> dict[str, Any]:
    """Verify a valid internal JWT from a sibling service.

    Unlike require_internal_auth, this does not perform agent token revocation
    checks because service-to-service tokens use non-agent subjects.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = auth[7:]
    return verify_internal_token(token)

ScopeType = Literal["agent", "attachment", "shared"]


async def _is_member_of_task_hierarchy(db: AsyncSession, task_id: str, agent_id: str) -> bool:
    """
    Check if the agent is the creator, assignee, or part of the parent task chain.
    """
    curr_id: str | None = task_id
    visited: set[str | None] = set()

    while curr_id and curr_id not in visited:
        visited.add(curr_id)
        result = await db.execute(select(Task).where(Task.id == curr_id, Task.deleted_at.is_(None)))
        task = result.scalar_one_or_none()
        if not task:
            return False

        if task.agent_id == agent_id or task.created_by == agent_id:
            return True

        curr_id = task.parent_task_id

    return False


@router.get("/verify-access")
async def verify_access(
    agent_id: str,
    scope: ScopeType,
    scope_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: dict[str, Any] = Depends(_require_service_auth),
) -> dict[str, Any]:
    """
    Internal endpoint for other services to verify agent access to a scope.
    """
    if scope == "agent":
        if agent_id == scope_id:
            return {"status": "ok", "access": True}
        return {"status": "denied", "access": False}

    if scope == "attachment" and await _is_member_of_task_hierarchy(db, scope_id, agent_id):
        # Agent is the creator, assignee, or part of the parent task chain.
        return {"status": "ok", "access": True}

    if scope == "shared":
        result = await db.execute(
            select(SharedWorkspace).where(
                SharedWorkspace.id == scope_id,
                SharedWorkspace.deleted_at.is_(None)
            )
        )
        workspace = result.scalar_one_or_none()
        if workspace and (agent_id in workspace.members or workspace.owner_id == agent_id):
            return {"status": "ok", "access": True}

    raise HTTPException(status_code=403, detail=f"Access denied to {scope} {scope_id}")


@router.get("/files/download")
async def download_file(token: str) -> Response:
    """Return a single workspace file using a short-lived signed token.

    This endpoint is intended for internal service-to-service use only
    (e.g. isli-channels fetching media bytes). It should not be exposed
    directly to the public internet.
    """
    try:
        payload = verify_internal_token(token)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired download token",
        )

    if "workspace:download" not in payload.get("scopes", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing download scope")

    agent_id = payload.get("agent_id") or ""
    scope = payload.get("scope") or ""
    scope_id = payload.get("scope_id") or ""
    path = payload.get("file_path") or ""
    if not all([agent_id, scope, scope_id, path]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed download token",
        )

    settings = get_settings()
    core_token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=1)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            f"{settings.workspace_url}/download",
            params={"agent_id": agent_id, "scope": scope, "scope_id": scope_id, "path": path},
            headers={"X-Internal-Auth": core_token},
        )
        resp.raise_for_status()
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "application/octet-stream"),
            headers={"Content-Disposition": f'inline; filename="{path.split("/")[-1]}"'},
        )
