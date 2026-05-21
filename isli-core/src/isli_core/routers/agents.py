from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import os
import asyncio
from pathlib import Path

from isli_core.db import get_db
from isli_core.models import Agent, Session
from isli_core.budget import check_budget
from isli_core.auth import create_internal_token, require_admin_auth, require_internal_auth
from isli_core.audit_writer import AuditWriter
from isli_core.config import get_settings
from isli_core.event_manager import EventManager
from isli_core.redis_client import get_redis

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    persona: str | None = None
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

    @field_validator("model_provider")
    @classmethod
    def _validate_provider(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"ollama", "anthropic", "openai", "kimi", "deepseek", "google", "azure"}
        if v.lower() not in allowed:
            raise ValueError(f"model_provider must be one of {allowed}, got '{v}'")
        return v.lower()


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    persona: str | None = None
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

    @field_validator("model_provider")
    @classmethod
    def _validate_provider(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"ollama", "anthropic", "openai", "kimi", "deepseek", "google", "azure"}
        if v.lower() not in allowed:
            raise ValueError(f"model_provider must be one of {allowed}, got '{v}'")
        return v.lower()


class AgentOut(BaseModel):
    id: str
    name: str
    description: str | None
    persona: str | None
    status: str
    model_provider: str | None
    model_id: str | None
    channels: list[str]
    skills: list[str]
    config: dict[str, Any]
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


class AgentRegistrationOut(AgentOut):
    token: str


@router.get("", response_model=list[AgentOut])
async def list_agents(status: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Agent).where(Agent.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Agent.status == status)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=AgentRegistrationOut, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreate, 
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth)
):
    agent_id = payload.id or f"agent-{payload.name.lower().replace(' ', '-')}"
    existing = await db.execute(select(Agent).where(Agent.id == agent_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Agent already exists")

    agent = Agent(
        id=agent_id,
        name=payload.name,
        description=payload.description,
        persona=payload.persona,
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
    agent.token_issued_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(agent)

    token = create_internal_token(agent.id, scopes=["agent"], expires_minutes=525600)

    settings = get_settings()
    ws_path = Path(settings.workspace_base_path) / agent.id
    ws_path.mkdir(parents=True, exist_ok=True)
    await AuditWriter.write(
        db, actor_type="system", actor_id="core-api", action="create_agent",
        target_type="agent", target_id=agent.id,
        payload={"name": agent.name, "model_id": agent.model_id, "workspace_path": str(ws_path)},
    )
    await db.commit()
    
    base = AgentOut.model_validate(agent)
    out = AgentRegistrationOut(**base.model_dump(), token=token)
    return out


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth)
):
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
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth)
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.deleted_at = datetime.now(timezone.utc)
    agent.status = "deleted"
    await db.commit()

    settings = get_settings()
    ws_path = Path(settings.workspace_base_path) / agent_id
    if ws_path.exists():
        archive_name = f"{agent_id}.deleted.{agent.deleted_at.strftime('%Y%m%d%H%M%S')}"
        archive_path = Path(settings.workspace_base_path) / archive_name
        ws_path.rename(archive_path)
        await AuditWriter.write(
            db, actor_type="system", actor_id="core-api", action="archive_workspace",
            target_type="agent", target_id=agent_id,
            payload={"archive_path": str(archive_path)},
        )
        await db.commit()

    await AuditWriter.write(
        db, actor_type="system", actor_id="core-api", action="delete_agent",
        target_type="agent", target_id=agent_id,
    )
    await db.commit()
    return


@router.post("/{agent_id}/token", response_model=dict)
async def issue_agent_token(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth)
):
    """Issue a fresh agent-scoped JWT, invalidating any previous token."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.token_issued_at = datetime.now(timezone.utc)
    token = create_internal_token(agent_id, scopes=["agent"], expires_minutes=525600)
    await db.commit()
    return {"token": token, "agent_id": agent_id}


@router.post("/{agent_id}/heartbeat", response_model=dict)
async def agent_heartbeat(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_internal_auth)
):
    if auth["sub"] != agent_id:
        raise HTTPException(status_code=403, detail="Not authorized for this agent")

    import time
    start = time.perf_counter()
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    old_status = agent.status
    agent.heartbeat_at = datetime.now(timezone.utc)
    agent.status = "online" if agent.status in ("registered", "offline", "paused") else agent.status

    if old_status != agent.status and agent.status == "online":
        await EventManager.emit("agent:online", {"agent_id": agent_id, "status": agent.status})

    # Update any active session's last_activity_at
    session_result = await db.execute(
        select(Session).where(
            Session.agent_id == agent_id,
            Session.deleted_at.is_(None),
        )
    )
    for sess in session_result.scalars().all():
        sess.last_activity_at = datetime.now(timezone.utc)

    now = datetime.now(timezone.utc)
    agent.token_issued_at = now
    await db.commit()
    token = create_internal_token(agent_id, scopes=["agent"], expires_minutes=525600, iat=now)
    latency_ms = (time.perf_counter() - start) * 1000
    from isli_core.telemetry import get_heartbeat_latency_histogram
    get_heartbeat_latency_histogram().record(latency_ms)
    await AuditWriter.write(
        db, actor_type="agent", actor_id=agent_id, action="heartbeat",
        target_type="agent", target_id=agent_id,
        payload={"latency_ms": round(latency_ms, 2)},
    )
    await db.commit()

    await EventManager.emit("agent:heartbeat", {
        "agent_id": agent_id,
        "status": agent.status,
        "heartbeat_at": agent.heartbeat_at.isoformat() if agent.heartbeat_at else None
    })

    return {"status": "ok", "agent_id": agent_id, "token": token}


@router.post("/{agent_id}/context", response_model=dict)
async def get_agent_context(
    agent_id: str, 
    task_description: str | None = None, 
    session_id: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """Proxy context injection from Keeper through Core API."""
    from isli_core.memory.keeper_client import KeeperClient
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    threshold = (agent.config or {}).get("memory_similarity_threshold", 0.4)
    context_summary = await KeeperClient.get_context_injection(
        agent_id=agent_id,
        task_description=task_description,
        session_id=session_id,
        agent_name=agent.name,
        agent_description=agent.description,
        agent_persona=agent.persona,
        memory_similarity_threshold=threshold,
    )
    return {"context_summary": context_summary}


@router.websocket("/{agent_id}/logs/stream")
async def stream_agent_logs(websocket: WebSocket, agent_id: str):
    await websocket.accept()
    
    redis = await get_redis()
    pubsub = redis.pubsub()
    channel = f"agent:{agent_id}:logs"
    
    try:
        await pubsub.subscribe(channel)
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        # Log error or send to client? For now just close
        print(f"Error streaming logs for {agent_id}: {e}")
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
