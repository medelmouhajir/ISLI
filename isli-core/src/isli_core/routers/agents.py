from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.db import get_db
from isli_core.models import Agent
from isli_core.budget import check_budget
from isli_core.auth import create_internal_token

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
        fallback_agent_id=payload.fallback_agent_id,
        max_retries=payload.max_retries,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
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

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    agent.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(agent)
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
    await db.commit()
    token = create_internal_token(agent_id, scopes=["agent"], expires_minutes=60)
    latency_ms = (time.perf_counter() - start) * 1000
    from isli_core.telemetry import get_heartbeat_latency_histogram
    get_heartbeat_latency_histogram().record(latency_ms)
    return {"status": "ok", "agent_id": agent_id, "token": token}
