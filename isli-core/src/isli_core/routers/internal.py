from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.db import get_db
from isli_core.models import Agent, SharedWorkspace, Task
from isli_core.auth import verify_internal_token

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
    curr_id = task_id
    visited = set()
    
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
    auth: dict = Depends(_require_service_auth),
):
    """
    Internal endpoint for other services to verify agent access to a scope.
    """
    if scope == "agent":
        if agent_id == scope_id:
            return {"status": "ok", "access": True}
        return {"status": "denied", "access": False}

    if scope == "attachment":
        # Check if agent is assigned to the task or its parents
        if await _is_member_of_task_hierarchy(db, scope_id, agent_id):
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
