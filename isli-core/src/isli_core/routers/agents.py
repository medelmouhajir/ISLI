from datetime import datetime, timezone
from typing import Any
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import os
import asyncio
import structlog
from pathlib import Path

logger = structlog.get_logger()

from isli_core.db import get_db
from isli_core.models import Agent, Session, LlmProvider
from isli_core.budget import check_budget, BudgetEngine, BudgetAlerter
from isli_core.cost.dashboard import CostDashboard
from isli_core.auth import (
    create_internal_token, 
    require_admin_auth, 
    require_internal_auth,
    security,
    verify_internal_token,
    _check_token_revocation
)
from isli_core.audit_writer import AuditWriter
from isli_core.config import get_settings
from isli_core.event_manager import EventManager
from isli_core.redis_client import get_redis
from isli_core.services.process_manager import get_pm, AgentProcessManager


def _safe_json(value: Any, default: Any = None) -> Any:
    """Guard against asyncpg returning JSON columns as strings."""
    if value is None:
        return default if default is not None else value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default if default is not None else value
    return value

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
    known_agent_ids: list[str] = Field(default_factory=list)
    max_retries: int = 3
    api_key: str | None = None
    auto_start: bool = True
    model_routing_enabled: bool = False
    secondary_models: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("model_provider")
    @classmethod
    def _validate_provider(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return v.lower()

    @field_validator("config")
    @classmethod
    def _normalize_streaming_mode(cls, v: dict[str, Any]) -> dict[str, Any]:
        valid = {"silent", "text", "tools", "trace", "debug"}
        mode = v.get("streaming_mode", "silent")
        if mode not in valid:
            v["streaming_mode"] = "silent"
        chunk_size = v.get("stream_chunk_size", 5)
        if not isinstance(chunk_size, int) or chunk_size < 1:
            v["stream_chunk_size"] = 5
        delay_ms = v.get("stream_delay_ms", 20)
        if not isinstance(delay_ms, int) or delay_ms < 0:
            v["stream_delay_ms"] = 20
        return v


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
    known_agent_ids: list[str] | None = None
    max_retries: int | None = None
    api_key: str | None = None
    model_routing_enabled: bool | None = None
    secondary_models: list[dict[str, Any]] | None = None

    @field_validator("model_provider")
    @classmethod
    def _validate_provider(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return v.lower()

    @field_validator("config")
    @classmethod
    def _normalize_streaming_mode(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return {"streaming_mode": "silent"}
        valid = {"silent", "text", "tools", "trace", "debug"}
        mode = v.get("streaming_mode", "silent")
        if mode not in valid:
            v["streaming_mode"] = "silent"
        chunk_size = v.get("stream_chunk_size", 5)
        if not isinstance(chunk_size, int) or chunk_size < 1:
            v["stream_chunk_size"] = 5
        delay_ms = v.get("stream_delay_ms", 20)
        if not isinstance(delay_ms, int) or delay_ms < 0:
            v["stream_delay_ms"] = 20
        return v


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}...{key[-4:]}"


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
    known_agent_ids: list[str] = []
    max_retries: int
    heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime
    has_api_key: bool = False
    api_key_mask: str | None = None
    model_routing_enabled: bool = False
    secondary_models: list[dict[str, Any]] = []
    streaming_mode: str = "silent"

    model_config = {"from_attributes": True}

    @classmethod
    def from_agent(cls, agent: Agent) -> "AgentOut":
        base = cls.model_validate(agent)
        base.has_api_key = bool(agent.api_key)
        base.api_key_mask = _mask_key(agent.api_key)
        base.channels = _safe_json(agent.channels, [])
        base.skills = _safe_json(agent.skills, [])
        base.known_agent_ids = _safe_json(agent.known_agent_ids, [])
        base.config = _safe_json(agent.config, {})
        base.streaming_mode = base.config.get("streaming_mode", "silent")
        base.config = _safe_json(agent.config, {})
        base.secondary_models = _safe_json(agent.secondary_models, [])
        return base


class AgentRegistrationOut(AgentOut):
    token: str


@router.get("", response_model=list[AgentOut])
async def list_agents(
    status: str | None = None, 
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth)
):
    stmt = select(Agent).where(Agent.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Agent.status == status)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=AgentRegistrationOut, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreate, 
    db: AsyncSession = Depends(get_db),
    pm: AgentProcessManager = Depends(get_pm),
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
        known_agent_ids=payload.known_agent_ids,
        max_retries=payload.max_retries,
        api_key=payload.api_key,
    )
    db.add(agent)
    agent.token_issued_at = datetime.now(timezone.utc)
    
    if payload.auto_start:
        try:
            await pm.spawn(agent.id)
            agent.status = "starting"
        except Exception as e:
            # Don't fail the whole creation if auto-spawn fails, just log it
            import structlog
            structlog.get_logger().error("agent.auto_start_failed", agent_id=agent.id, error=str(e))
    
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
    
    base = AgentOut.from_agent(agent)
    out = AgentRegistrationOut(**base.model_dump(), token=token)
    return out


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentOut.from_agent(agent)


@router.get("/{agent_id}/peers", response_model=list[AgentOut])
async def get_agent_peers(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth)
):
    """Resolve an agent's known_agent_ids into full agent metadata."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    peer_ids = _safe_json(agent.known_agent_ids, [])
    if not peer_ids:
        return []

    peers_result = await db.execute(
        select(Agent).where(
            Agent.id.in_(peer_ids),
            Agent.deleted_at.is_(None)
        )
    )
    peers = peers_result.scalars().all()
    return [AgentOut.from_agent(p) for p in peers]


class AgentConfigOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    persona: str | None = None
    model_provider: str | None = None
    model_id: str | None = None
    channels: list[str] = []
    skills: list[str] = []
    known_agent_ids: list[str] = []
    config: dict[str, Any] = {}
    token_budget: int | None = None
    api_key: str | None = None


@router.get("/{agent_id}/config", response_model=AgentConfigOut)
async def get_agent_config(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    auth: Any = Depends(security),
):
    # Allow either a valid internal agent token OR the admin API key
    settings = get_settings()
    is_admin = auth.credentials == settings.admin_api_key
    
    if not is_admin:
        payload = verify_internal_token(auth.credentials)
        await _check_token_revocation(payload)
        if payload["sub"] != agent_id:
            raise HTTPException(status_code=403, detail="Not authorized for this agent")
    
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    resolved_key = agent.api_key
    if not resolved_key and agent.model_provider:
        provider_result = await db.execute(
            select(LlmProvider).where(LlmProvider.provider == agent.model_provider)
        )
        provider = provider_result.scalar_one_or_none()
        if provider:
            resolved_key = provider.api_key

    return AgentConfigOut(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        persona=agent.persona,
        model_provider=agent.model_provider,
        model_id=agent.model_id,
        channels=_safe_json(agent.channels, []),
        skills=_safe_json(agent.skills, []),
        known_agent_ids=_safe_json(agent.known_agent_ids, []),
        config=_safe_json(agent.config, {}),
        token_budget=agent.token_budget,
        api_key=resolved_key,
    )


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

    # Notify running agents that their config changed
    if any(k in changes for k in ("skills", "channels", "known_agent_ids", "model_provider", "model_id", "persona", "config", "api_key")):
        await EventManager.emit("agent:config_updated", {"agent_id": agent.id, "fields": list(changes.keys())})

    await AuditWriter.write(
        db, actor_type="system", actor_id="core-api", action="update_agent",
        target_type="agent", target_id=agent.id,
        payload={k: v for k, v in changes.items() if k != "api_key"},
    )
    await db.commit()
    return AgentOut.from_agent(agent)


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
        archive_dir = Path(settings.workspace_base_path) / "_archived"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_name = f"{agent_id}.deleted.{agent.deleted_at.strftime('%Y%m%d%H%M%S')}"
        archive_path = archive_dir / archive_name
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
    agent.status = "online" if agent.status in ("registered", "starting", "offline", "paused", "stopped", "crashed") else agent.status

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
    token = create_internal_token(agent_id, scopes=["agent"], expires_minutes=525600, iat=now)
    latency_ms = (time.perf_counter() - start) * 1000
    from isli_core.telemetry import get_heartbeat_latency_histogram
    get_heartbeat_latency_histogram().record(latency_ms)
    await AuditWriter.write(
        db, actor_type="agent", actor_id=agent_id, action="heartbeat",
        target_type="agent", target_id=agent_id,
        payload={"latency_ms": round(latency_ms, 2)},
    )

    await EventManager.emit("agent:heartbeat", {
        "agent_id": agent_id,
        "status": agent.status,
        "heartbeat_at": agent.heartbeat_at.isoformat() if agent.heartbeat_at else None
    })

    # Revoke the old token ONLY after all side effects succeeded and the new token
    # is guaranteed to be returned. If anything above raises, the old token stays valid.
    agent.token_issued_at = now
    await db.commit()

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
    known_agent_ids = _safe_json(agent.known_agent_ids, [])
    context_summary = await KeeperClient.get_context_injection(
        agent_id=agent_id,
        task_description=task_description,
        session_id=session_id,
        agent_name=agent.name,
        agent_description=agent.description,
        memory_similarity_threshold=threshold,
        known_agent_ids=known_agent_ids,
    )

    # Resolve peer metadata and append directly so the LLM sees it even if
    # the agent runner hasn't yet synced known_agent_ids into its config.
    if known_agent_ids and context_summary:
        peers_result = await db.execute(
            select(Agent).where(
                Agent.id.in_(known_agent_ids),
                Agent.deleted_at.is_(None)
            )
        )
        peers = peers_result.scalars().all()
        if peers:
            peer_block = "\n\n=== PEER AGENTS ===\n"
            peer_block += "You can delegate tasks to the following agents via the Kanban board:\n"
            for peer in peers:
                peer_block += f"- {peer.id} ({peer.name}): {peer.description or 'No description'}\n"
            peer_block += (
                "\nWhen delegating, use create_task and set assignee to the target agent ID."
            )
            context_summary = context_summary + peer_block

    return {"context_summary": context_summary}


class UsageIn(BaseModel):
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int = 0
    model_id: str
    task_id: str | None = None
    tier: str = "standard"


class UsageOut(BaseModel):
    status: str
    cost_usd: float
    agent_id: str


@router.post("/{agent_id}/usage", response_model=UsageOut)
async def record_agent_usage(
    agent_id: str,
    payload: UsageIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_internal_auth),
):
    if auth["sub"] != agent_id:
        raise HTTPException(status_code=403, detail="Not authorized for this agent")

    await check_budget(
        db,
        agent_id,
        payload.input_tokens,
        payload.output_tokens,
        payload.reasoning_tokens,
        payload.task_id,
    )

    entry = await CostDashboard.record_turn(
        db,
        agent_id,
        payload.task_id,
        payload.model_id,
        payload.input_tokens,
        payload.output_tokens,
        payload.reasoning_tokens,
        payload.tier,
    )

    from isli_core.budget import charge_tokens
    await charge_tokens(
        db,
        agent_id,
        payload.input_tokens,
        payload.output_tokens,
        payload.reasoning_tokens,
    )

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()

    if agent:
        if agent.user_id:
            await BudgetEngine.check_user_budget(
                db,
                agent.user_id,
                payload.input_tokens,
                payload.output_tokens,
                payload.reasoning_tokens,
                payload.model_id,
            )
        if agent.org_id:
            await BudgetEngine.check_org_budget(
                db,
                agent.org_id,
                payload.input_tokens,
                payload.output_tokens,
                payload.reasoning_tokens,
                payload.model_id,
            )

    await db.commit()

    if agent:
        if agent.user_id:
            asyncio.create_task(
                _fire_budget_alert(db, agent.user_id, agent.org_id)
            )

    return UsageOut(
        status="recorded",
        cost_usd=round(entry.cost_usd, 6),
        agent_id=agent_id,
    )


async def _fire_budget_alert(db: AsyncSession, user_id: str | None, org_id: str | None) -> None:
    try:
        if user_id:
            status = await BudgetEngine.get_user_budget_status(db, user_id)
            if status:
                await BudgetAlerter.maybe_alert_user(db, user_id, status["token_used"], status["usd_used"])
        if org_id:
            status = await BudgetEngine.get_org_budget_status(db, org_id)
            if status:
                await BudgetAlerter.maybe_alert_org(db, org_id, status["token_used"], status["usd_used"])
    except Exception:
        pass


@router.post("/{agent_id}/start")
async def start_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    pm: AgentProcessManager = Depends(get_pm),
    _admin: str = Depends(require_admin_auth)
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        await pm.spawn(agent_id)
    except Exception as exc:
        agent.status = "stopped"
        agent.status_reason = f"spawn failed: {exc}"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to start agent: {exc}") from exc

    agent.status = "starting"
    await db.commit()
    return {"status": "starting", "agent_id": agent_id}


@router.post("/{agent_id}/stop")
async def stop_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    pm: AgentProcessManager = Depends(get_pm),
    _admin: str = Depends(require_admin_auth)
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    await pm.terminate(agent_id)
    agent.status = "stopped"
    await db.commit()
    return {"status": "stopped", "agent_id": agent_id}


async def _rebuild_and_start(pm: AgentProcessManager, agent_id: str) -> None:
    """Background task: rebuild agent-runner image then spawn the agent."""
    from sqlalchemy import update

    from isli_core.db import get_db_session_manual
    from isli_core.models import Agent

    try:
        await pm.rebuild_image()
        await pm.spawn(agent_id)
        async with get_db_session_manual() as db:
            await db.execute(
                update(Agent)
                .where(Agent.id == agent_id)
                .values(status="starting")
            )
            await db.commit()
        logger.info("agents.restart.done", agent_id=agent_id)
    except Exception as exc:
        logger.error("agents.rebuild_and_start.failed", agent_id=agent_id, error=str(exc))
        async with get_db_session_manual() as db:
            await db.execute(
                update(Agent)
                .where(Agent.id == agent_id)
                .values(status="stopped", status_reason=f"rebuild failed: {exc}")
            )
            await db.commit()


@router.post("/{agent_id}/restart")
async def restart_agent(
    agent_id: str,
    rebuild: bool = False,
    db: AsyncSession = Depends(get_db),
    pm: AgentProcessManager = Depends(get_pm),
    _admin: str = Depends(require_admin_auth)
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    await pm.terminate(agent_id)
    agent.status = "stopped"
    await db.commit()

    if rebuild:
        from isli_core.config import get_settings

        settings = get_settings()
        if not settings.agent_runner_build_context:
            raise HTTPException(
                status_code=400,
                detail="Rebuild not configured: AGENT_RUNNER_BUILD_CONTEXT is not set",
            )

        agent.status = "rebuilding"
        await db.commit()
        asyncio.create_task(_rebuild_and_start(pm, agent_id))
        return {"status": "rebuilding", "agent_id": agent_id}

    await pm.spawn(agent_id)
    agent.status = "starting"
    await db.commit()
    return {"status": "starting", "agent_id": agent_id}


@router.get("/{agent_id}/process-status")
async def get_agent_process_status(
    agent_id: str,
    pm: AgentProcessManager = Depends(get_pm),
    _admin: str = Depends(require_admin_auth)
):
    return pm.get_status(agent_id)


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


@router.get("/{agent_id}/logs/history")
async def get_agent_logs_history(
    agent_id: str,
    limit: int = 100,
    offset: int = 0
):
    """Fetch historical logs for this agent from Redis using end-relative pagination."""
    redis = await get_redis()
    history_key = f"agent:{agent_id}:logs:history"
    
    # Calculate Redis indices relative to the end (newest)
    # offset=0, limit=100 -> start=-100, end=-1 (the 100 newest)
    # offset=100, limit=100 -> start=-200, end=-101 (the next 100 older)
    start = -(offset + limit)
    end = -(offset + 1)
    
    logs = await redis.lrange(history_key, start, end)
    
    parsed_logs = []
    for log_str in logs:
        try:
            if isinstance(log_str, bytes):
                log_str = log_str.decode("utf-8")
            parsed_logs.append(json.loads(log_str))
        except Exception:
            continue
            
    return parsed_logs


class ModelErrorReport(BaseModel):
    category: str
    reason: str | None = None


@router.post("/{agent_id}/model_error", status_code=status.HTTP_204_NO_CONTENT)
async def report_model_error(
    agent_id: str,
    payload: ModelErrorReport,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_internal_auth),
):
    if auth["sub"] != agent_id:
        raise HTTPException(status_code=403, detail="Not authorized for this agent")

    result = await db.execute(
        update(Agent)
        .where(Agent.id == agent_id, Agent.deleted_at.is_(None))
        .values(status="flagged", status_reason=payload.reason)
    )
    await db.commit()
    return Response(status_code=204)


@router.post("/{agent_id}/model_recovery", status_code=status.HTTP_204_NO_CONTENT)
async def report_model_recovery(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_internal_auth),
):
    if auth["sub"] != agent_id:
        raise HTTPException(status_code=403, detail="Not authorized for this agent")

    result = await db.execute(
        update(Agent)
        .where(Agent.id == agent_id, Agent.deleted_at.is_(None), Agent.status == "flagged")
        .values(status="online", status_reason=None)
    )
    await db.commit()
    if result.rowcount == 0:
        logger.info("agents.model_recovery_noop", agent_id=agent_id, reason="agent not in flagged state")
    return Response(status_code=204)


@router.get("/{agent_id}/memory/events")
async def get_agent_memory_events(agent_id: str):
    """Fetch the last 50 memory observability events for this agent."""
    redis = await get_redis()
    key = f"agent:{agent_id}:memory_events"
    events = await redis.lrange(key, 0, -1)
    
    parsed_events = []
    for event_str in events:
        try:
            if isinstance(event_str, bytes):
                event_str = event_str.decode("utf-8")
            parsed_events.append(json.loads(event_str))
        except Exception:
            continue
            
    # Return in chronological order (Redis LPUSH/LRANGE returns newest first)
    parsed_events.reverse()
    return parsed_events
