from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal

from isli_core.db import get_db
from isli_core.models import Task, SharedWorkspace, Agent
from isli_core.auth import require_internal_auth

router = APIRouter(prefix="/internal", tags=["internal"])

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
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_internal_auth)
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
