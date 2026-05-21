from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.auth import create_internal_token, require_admin_auth
from isli_core.budget import BudgetEngine
from isli_core.compliance.audit_integrity import AuditIntegrity
from isli_core.config import get_settings
from isli_core.db import get_db
from isli_core.models import Agent, AuditLog, CostLedger, OrgBudget, Task, UserBudget, UserConsent

router = APIRouter(prefix="/system", tags=["system"])


class CostDashboardOut(BaseModel):
    total_agents: int
    total_tasks: int
    total_cost_usd: float
    avg_cost_per_agent: float
    agent_costs: list[dict[str, Any]]


@router.get("/cost/dashboard", response_model=CostDashboardOut)
async def cost_dashboard(db: AsyncSession = Depends(get_db)):
    agents_result = await db.execute(select(func.count()).select_from(Agent).where(Agent.deleted_at.is_(None)))
    total_agents = agents_result.scalar() or 0

    tasks_result = await db.execute(select(func.count()).select_from(Task).where(Task.deleted_at.is_(None)))
    total_tasks = tasks_result.scalar() or 0

    cost_result = await db.execute(select(func.sum(CostLedger.cost_usd)))
    total_cost = cost_result.scalar() or 0.0

    agent_costs = []
    agent_rows = await db.execute(
        select(
            CostLedger.agent_id,
            func.sum(CostLedger.cost_usd).label("cost"),
            func.sum(CostLedger.input_tokens + CostLedger.output_tokens).label("tokens"),
        ).group_by(CostLedger.agent_id)
    )
    for row in agent_rows.all():
        agent_costs.append({
            "agent_id": row.agent_id,
            "cost_usd": float(row.cost or 0),
            "tokens": int(row.tokens or 0),
        })

    avg_cost = total_cost / total_agents if total_agents > 0 else 0.0

    return CostDashboardOut(
        total_agents=total_agents,
        total_tasks=total_tasks,
        total_cost_usd=round(total_cost, 4),
        avg_cost_per_agent=round(avg_cost, 4),
        agent_costs=agent_costs,
    )


class ConsentOut(BaseModel):
    id: str
    user_id: str
    channel: str
    purpose: str
    granted: bool
    granted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/compliance/consents/{user_id}", response_model=list[ConsentOut])
async def list_consents(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserConsent).where(UserConsent.user_id == user_id)
    )
    return result.scalars().all()


class ConsentCreate(BaseModel):
    user_id: str
    channel: str
    purpose: str
    granted: bool = True


@router.post("/compliance/consents", response_model=ConsentOut, status_code=201)
async def create_consent(
    payload: ConsentCreate,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth)
):
    consent = UserConsent(
        user_id=payload.user_id,
        channel=payload.channel,
        purpose=payload.purpose,
        granted=payload.granted,
        granted_at=datetime.now(UTC) if payload.granted else None,
    )
    db.add(consent)
    await db.commit()
    await db.refresh(consent)
    return consent


@router.get("/audit-logs", response_model=list[dict[str, Any]])
async def list_audit_logs(actor_id: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(AuditLog)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(100)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    out = []
    for log in logs:
        out.append({
            "id": log.id,
            "actor_type": log.actor_type,
            "actor_id": log.actor_id,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "payload": log.payload,
            "chain_hash": log.chain_hash,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })
    return out


@router.get("/audit-integrity")
async def audit_integrity(db: AsyncSession = Depends(get_db)):
    result = await AuditIntegrity.verify_chain(db)
    return result


class BudgetCreate(BaseModel):
    user_id: str | None = None
    org_id: str | None = None
    monthly_usd_cap: float | None = None
    monthly_token_cap: int | None = None
    alert_threshold_pct: float = 80.0
    slack_webhook_url: str | None = None


class BudgetOut(BaseModel):
    id: str
    user_id: str | None = None
    org_id: str | None = None
    monthly_usd_cap: float | None = None
    monthly_token_cap: int | None = None
    alert_threshold_pct: float
    slack_webhook_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BudgetStatusOut(BaseModel):
    scope: str
    scope_id: str
    monthly_token_cap: int | None = None
    monthly_usd_cap: float | None = None
    token_used: int
    usd_used: float
    alert_threshold_pct: float
    slack_webhook_url: str | None = None


@router.post("/budgets/user", response_model=BudgetOut, status_code=201)
async def create_user_budget(
    payload: BudgetCreate,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth)
):
    if not payload.user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    existing = await db.execute(select(UserBudget).where(UserBudget.user_id == payload.user_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User budget already exists")
    budget = UserBudget(
        user_id=payload.user_id,
        monthly_usd_cap=payload.monthly_usd_cap,
        monthly_token_cap=payload.monthly_token_cap,
        alert_threshold_pct=payload.alert_threshold_pct,
        slack_webhook_url=payload.slack_webhook_url,
    )
    db.add(budget)
    await db.commit()
    await db.refresh(budget)
    return budget


@router.post("/budgets/org", response_model=BudgetOut, status_code=201)
async def create_org_budget(
    payload: BudgetCreate,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth)
):
    if not payload.org_id:
        raise HTTPException(status_code=400, detail="org_id is required")
    existing = await db.execute(select(OrgBudget).where(OrgBudget.org_id == payload.org_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Org budget already exists")
    budget = OrgBudget(
        org_id=payload.org_id,
        monthly_usd_cap=payload.monthly_usd_cap,
        monthly_token_cap=payload.monthly_token_cap,
        alert_threshold_pct=payload.alert_threshold_pct,
        slack_webhook_url=payload.slack_webhook_url,
    )
    db.add(budget)
    await db.commit()
    await db.refresh(budget)
    return budget


@router.get("/budgets", response_model=list[BudgetStatusOut])
async def list_budgets(db: AsyncSession = Depends(get_db)):
    out: list[BudgetStatusOut] = []
    user_rows = await db.execute(select(UserBudget))
    for budget in user_rows.scalars().all():
        status = await BudgetEngine.get_user_budget_status(db, budget.user_id)
        if status:
            out.append(BudgetStatusOut(
                scope="user",
                scope_id=status["user_id"],
                monthly_token_cap=status["monthly_token_cap"],
                monthly_usd_cap=status["monthly_usd_cap"],
                token_used=status["token_used"],
                usd_used=status["usd_used"],
                alert_threshold_pct=status["alert_threshold_pct"],
                slack_webhook_url=status["slack_webhook_url"],
            ))
    org_rows = await db.execute(select(OrgBudget))
    for budget in org_rows.scalars().all():
        status = await BudgetEngine.get_org_budget_status(db, budget.org_id)
        if status:
            out.append(BudgetStatusOut(
                scope="org",
                scope_id=status["org_id"],
                monthly_token_cap=status["monthly_token_cap"],
                monthly_usd_cap=status["monthly_usd_cap"],
                token_used=status["token_used"],
                usd_used=status["usd_used"],
                alert_threshold_pct=status["alert_threshold_pct"],
                slack_webhook_url=status["slack_webhook_url"],
            ))
    return out


@router.get("/budgets/{scope}/{scope_id}", response_model=BudgetStatusOut)
async def get_budget(scope: str, scope_id: str, db: AsyncSession = Depends(get_db)):
    if scope == "user":
        status = await BudgetEngine.get_user_budget_status(db, scope_id)
    elif scope == "org":
        status = await BudgetEngine.get_org_budget_status(db, scope_id)
    else:
        raise HTTPException(status_code=400, detail="scope must be 'user' or 'org'")
    if status is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    return BudgetStatusOut(
        scope=scope,
        scope_id=status.get("user_id") or status.get("org_id"),
        monthly_token_cap=status["monthly_token_cap"],
        monthly_usd_cap=status["monthly_usd_cap"],
        token_used=status["token_used"],
        usd_used=status["usd_used"],
        alert_threshold_pct=status["alert_threshold_pct"],
        slack_webhook_url=status["slack_webhook_url"],
    )


@router.get("/keeper/dashboard")
async def keeper_dashboard():
    settings = get_settings()
    url = f"{settings.keeper_url}/dashboard"
    try:
        token = create_internal_token("core-api", scopes=["keeper:dashboard"], expires_minutes=1)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers={"X-Internal-Auth": token})
            resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Keeper unavailable: {exc}")

