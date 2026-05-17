from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.db import get_db
from isli_core.models import Task
from isli_core.locking import increment_task_version
from isli_core.audit_writer import AuditWriter
from isli_core.security.content_scanner import ContentScanner
from isli_core.security.policy_engine import PolicyEngine
from isli_core.memory.keeper_client import KeeperClient
from isli_core.event_manager import EventManager
from isli_core.checkpoint import CheckpointManager

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"pending_context", "inbox", "doing", "review", "done", "failed", "blocked"}


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    type: str = "task"
    priority: int = 3
    agent_id: str | None = None
    created_by: str
    input: str = ""
    channel: str | None = None
    session_id: str | None = None
    payload: dict[str, Any] | None = None
    parent_task_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    idempotency_key: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    agent_id: str | None = None
    input: str | None = None
    output: str | None = None
    session_id: str | None = None
    payload: dict[str, Any] | None = None
    blocked_reason: str | None = None
    tags: list[str] | None = None
    token_usage: dict[str, Any] | None = None
    saga_log: list[dict[str, Any]] | None = None


class TaskOut(BaseModel):
    id: str
    title: str
    description: str | None
    type: str
    status: str
    priority: int
    agent_id: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    input: str
    output: str | None
    context_summary: str | None
    payload: dict[str, Any] | None
    session_id: str | None
    channel: str | None
    parent_task_id: str | None
    child_task_ids: list[str]
    depth: int
    blocked_reason: str | None
    saga_log: list[dict[str, Any]]
    token_usage: dict[str, Any] | None
    tags: list[str]
    version: int
    trace_id: str | None
    retry_count: int
    idempotency_key: str | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    status: str | None = None,
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Task).where(Task.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Task.status == status)
    if agent_id:
        stmt = stmt.where(Task.agent_id == agent_id)
    stmt = stmt.order_by(Task.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_db)):
    # Security scan and policy check
    scan = ContentScanner.scan(payload.input)
    decision = await PolicyEngine.evaluate(
        db,
        user_id=payload.created_by,
        input_text=payload.input,
        agent_id=payload.agent_id,
        skill_name=None,
        model_id=None,
        budget_exceeded=False,
        estop_active=False,
    )
    if not decision.allow:
        detail: dict[str, Any] = {
            "detail": f"Policy block: {decision.reason}",
            "policy_decision": {
                "allow": decision.allow,
                "reason": decision.reason,
                "risk_score": decision.risk_score,
                "overrideable": decision.overrideable,
                "rule": decision.rule,
                "context_hash": decision.context_hash,
            },
        }
        if decision.overrideable:
            detail["override_request_url"] = "/v1/security/override-request"
        raise HTTPException(status_code=403, detail=detail)

    if payload.idempotency_key:
        existing = await db.execute(
            select(Task).where(Task.idempotency_key == payload.idempotency_key)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Duplicate idempotency key")

    depth = 0
    if payload.parent_task_id:
        parent = await db.execute(
            select(Task).where(Task.id == payload.parent_task_id, Task.deleted_at.is_(None))
        )
        parent_task = parent.scalar_one_or_none()
        if not parent_task:
            raise HTTPException(status_code=404, detail="Parent task not found")
        depth = parent_task.depth + 1
        if depth > 3:
            raise HTTPException(status_code=400, detail="Max delegation depth exceeded")

    task = Task(
        title=payload.title,
        description=payload.description,
        type=payload.type,
        status="pending_context" if payload.agent_id else "inbox",
        priority=payload.priority,
        agent_id=payload.agent_id,
        created_by=payload.created_by,
        input=payload.input,
        channel=payload.channel,
        session_id=payload.session_id,
        payload=payload.payload,
        parent_task_id=payload.parent_task_id,
        depth=depth,
        tags=payload.tags,
        idempotency_key=payload.idempotency_key,
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)

    if payload.parent_task_id:
        parent_task.child_task_ids = list(parent_task.child_task_ids or []) + [task.id]
        await db.commit()

    from isli_core.telemetry import get_task_creation_counter
    get_task_creation_counter().add(1)
    await AuditWriter.write(
        db, actor_type="user", actor_id=payload.created_by, action="create_task",
        target_type="task", target_id=task.id,
        payload={"title": task.title, "agent_id": task.agent_id},
    )
    await db.commit()
    
    await EventManager.emit("task:created", {"task": TaskOut.model_validate(task).model_dump(mode="json")})
    
    return task


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskOut)
async def update_task(task_id: str, payload: TaskUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    await increment_task_version(db, task_id, task.version)

    changes = payload.model_dump(exclude_unset=True)
    
    for field, value in changes.items():
        setattr(task, field, value)
    task.updated_at = datetime.now(timezone.utc)
    task.version += 1
    await db.commit()
    await db.refresh(task)
    await AuditWriter.write(
        db, actor_type="system", actor_id="core-api", action="update_task",
        target_type="task", target_id=task.id,
        payload=changes,
    )
    await db.commit()
    
    await EventManager.emit("task:updated", {
        "task_id": task_id,
        "changes": changes,
        "task": TaskOut.model_validate(task).model_dump(mode="json")
    })
    
    return task


@router.post("/{task_id}/move", response_model=TaskOut)
async def move_task(task_id: str, new_status: str, db: AsyncSession = Depends(get_db)):
    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

    result = await db.execute(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = new_status
    task.updated_at = datetime.now(timezone.utc)
    if new_status == "doing":
        task.started_at = datetime.now(timezone.utc)
    if new_status in ("done", "failed"):
        task.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    await AuditWriter.write(
        db, actor_type="system", actor_id="core-api", action="move_task",
        target_type="task", target_id=task.id,
        payload={"new_status": new_status},
    )
    await db.commit()
    
    await EventManager.emit("task:moved", {
        "task_id": task_id,
        "from": task.status,
        "to": new_status,
        "task": TaskOut.model_validate(task).model_dump(mode="json")
    })
    
    return task


@router.post("/{task_id}/saga", response_model=dict)
async def append_saga_entry(
    task_id: str,
    entry: dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Append to saga log (SQLAlchemy JSON mutation detection helper)
    current_log = list(task.saga_log or [])
    current_log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **entry
    })
    task.saga_log = current_log
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {"status": "ok", "log_size": len(current_log)}


@router.post("/{task_id}/checkpoint", response_model=dict)
async def save_checkpoint(
    task_id: str,
    turn_number: int,
    messages: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]] | None = None,
    db: AsyncSession = Depends(get_db)
):
    cp = await CheckpointManager.save(db, task_id, turn_number, messages, tool_calls)
    await db.commit()
    return {"status": "ok", "checkpoint_id": cp.id}


@router.get("/{task_id}/checkpoint/latest", response_model=dict | None)
async def get_latest_checkpoint(task_id: str, db: AsyncSession = Depends(get_db)):
    cp = await CheckpointManager.load_latest(db, task_id)
    if not cp:
        return None
    return {
        "id": cp.id,
        "task_id": cp.task_id,
        "turn_number": cp.turn_number,
        "messages": cp.messages,
        "tool_calls": cp.tool_calls,
        "created_at": cp.created_at.isoformat() if cp.created_at else None
    }


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    await AuditWriter.write(
        db, actor_type="system", actor_id="core-api", action="delete_task",
        target_type="task", target_id=task_id,
    )
    await db.commit()
    return
