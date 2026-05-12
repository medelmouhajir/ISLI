from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.db import get_db
from isli_core.models import Agent, Session
from isli_core.budget import check_budget
from isli_core.auth import create_internal_token
from isli_core.audit_writer import AuditWriter

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    model_provider: str | None = None
    model_id: str | None = None
    channels: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    token_budget: int | None = None
    user_id: str | None = None
    org_id: str | None = None
    fallback_agent_id: str | None = None
    max_retries: int = 3


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    model_provider: str | None = None
    model_id: str | None = None
    channels: list[str] | None = None
    skills: list[str] | None = None
    config: dict[str, Any] | None = None
    token_budget: int | None = None
    user_id: str | None = None
    org_id: str | None = None
    fallback_agent_id: str | None = None
    max_retries: int | None = None


class AgentOut(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    model_provider: str | None
    model_id: str | None
    channels: list[str]
    skills: list[str]
    token_budget: int | None
    token_used: int
    user_id: str | None
    org_id: str | None
    fallback_agent_id: str | None
    max_retries: int
    heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AgentOut])
async def list_agents(status: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Agent).where(Agent.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Agent.status == status)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentCreate, db: AsyncSession = Depends(get_db)):
    agent_id = payload.id or f"agent-{payload.name.lower().replace(' ', '-')}"
    existing = await db.execute(select(Agent).where(Agent.id == agent_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Agent already exists")

    agent = Agent(
        id=agent_id,
        name=payload.name,
        description=payload.description,
        model_provider=payload.model_provider,
        model_id=payload.model_id,
        channels=payload.channels,
        skills=payload.skills,
        config=payload.config,
        token_budget=payload.token_budget,
        user_id=payload.user_id,
        org_id=payload.org_id,
        fallback_agent_id=payload.fallback_agent_id,
        max_retries=payload.max_retries,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    await AuditWriter.write(
        db, actor_type="system", actor_id="core-api", action="create_agent",
        target_type="agent", target_id=agent.id,
        payload={"name": agent.name, "model_id": agent.model_id},
    )
    await db.commit()
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: str, payload: AgentUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(agent, field, value)
    agent.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(agent)
    await AuditWriter.write(
        db, actor_type="system", actor_id="core-api", action="update_agent",
        target_type="agent", target_id=agent.id,
        payload=changes,
    )
    await db.commit()
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.deleted_at = datetime.now(timezone.utc)
    agent.status = "deleted"
    await db.commit()
    await AuditWriter.write(
        db, actor_type="system", actor_id="core-api", action="delete_agent",
        target_type="agent", target_id=agent_id,
    )
    await db.commit()
    return


@router.post("/{agent_id}/heartbeat", response_model=dict)
async def agent_heartbeat(agent_id: str, db: AsyncSession = Depends(get_db)):
    import time
    start = time.perf_counter()
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.heartbeat_at = datetime.now(timezone.utc)
    agent.status = "online" if agent.status in ("registered", "offline", "paused") else agent.status

    # Update any active session's last_activity_at
    session_result = await db.execute(
        select(Session).where(
            Session.agent_id == agent_id,
            Session.deleted_at.is_(None),
        )
    )
    for sess in session_result.scalars().all():
        sess.last_activity_at = datetime.now(timezone.utc)

    await db.commit()
    token = create_internal_token(agent_id, scopes=["agent"], expires_minutes=60)
    latency_ms = (time.perf_counter() - start) * 1000
    from isli_core.telemetry import get_heartbeat_latency_histogram
    get_heartbeat_latency_histogram().record(latency_ms)
    await AuditWriter.write(
        db, actor_type="agent", actor_id=agent_id, action="heartbeat",
        target_type="agent", target_id=agent_id,
        payload={"latency_ms": round(latency_ms, 2)},
    )
    await db.commit()
    return {"status": "ok", "agent_id": agent_id, "token": token}
