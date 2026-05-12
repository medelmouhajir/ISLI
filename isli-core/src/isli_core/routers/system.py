from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.db import get_db
from isli_core.models import Agent, CostLedger, Task, UserConsent, AuditLog

router = APIRouter(prefix="/system", tags=["system"])


class CostDashboardOut(BaseModel):
    total_agents: int
    total_tasks: int
    total_cost_usd: float
    avg_cost_per_agent: float
    agent_costs: list[dict[str, Any]]


@router.get("/cost/dashboard", response_model=CostDashboardOut)
async def cost_dashboard(db: AsyncSession = Depends(get_db)):
    agents_result = await db.execute(select(func.count()).select_from(Agent))
    total_agents = agents_result.scalar() or 0

    tasks_result = await db.execute(select(func.count()).select_from(Task))
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
async def create_consent(payload: ConsentCreate, db: AsyncSession = Depends(get_db)):
    consent = UserConsent(
        user_id=payload.user_id,
        channel=payload.channel,
        purpose=payload.purpose,
        granted=payload.granted,
        granted_at=datetime.now(timezone.utc) if payload.granted else None,
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
    return [log.__dict__ for log in logs]
