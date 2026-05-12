"""Security endpoints — content scan, policy overrides."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.db import get_db
from isli_core.auth import require_scopes
from isli_core.security.content_scanner import ContentScanner
from isli_core.security.policy_engine import PolicyEngine
from isli_core.security.override_store import OverrideStore

router = APIRouter(prefix="/security", tags=["security"])


class ScanIn(BaseModel):
    text: str


class ScanOut(BaseModel):
    blocked: bool
    reason: str | None
    risk_score: float


@router.post("/scan", response_model=ScanOut)
async def scan_text(payload: ScanIn):
    result = ContentScanner.scan(payload.text)
    return ScanOut(blocked=result.blocked, reason=result.reason, risk_score=result.risk_score)


class OverrideRequestIn(BaseModel):
    user_id: str
    rule: str
    context_hash: str


class OverrideOut(BaseModel):
    id: str
    user_id: str
    rule: str
    context_hash: str
    granted: bool
    granted_by: str | None
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/override-request", response_model=OverrideOut, status_code=201)
async def request_override(payload: OverrideRequestIn, db: AsyncSession = Depends(get_db)):
    override = await OverrideStore.request(db, payload.user_id, payload.rule, payload.context_hash)
    await db.commit()
    await db.refresh(override)
    return override


@router.post("/override-grant", response_model=OverrideOut)
async def grant_override(
    override_id: str,
    granted_by: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_scopes(["admin"])),
):
    override = await OverrideStore.grant(db, override_id, granted_by)
    if not override:
        raise HTTPException(status_code=404, detail="Override request not found")
    await db.commit()
    await db.refresh(override)
    return override


@router.get("/override-status/{override_id}", response_model=OverrideOut)
async def get_override_status(override_id: str, db: AsyncSession = Depends(get_db)):
    override = await OverrideStore.get(db, override_id)
    if not override:
        raise HTTPException(status_code=404, detail="Override request not found")
    return override


class PolicyCheckIn(BaseModel):
    user_id: str
    input_text: str | None = None
    agent_id: str | None = None
    skill_name: str | None = None
    model_id: str | None = None
    budget_exceeded: bool = False
    estop_active: bool = False


class PolicyCheckOut(BaseModel):
    allow: bool
    reason: str | None
    risk_score: float
    overrideable: bool
    rule: str | None
    context_hash: str | None


@router.post("/check", response_model=PolicyCheckOut)
async def check_policy(payload: PolicyCheckIn, db: AsyncSession = Depends(get_db)):
    decision = await PolicyEngine.evaluate(
        db,
        user_id=payload.user_id,
        input_text=payload.input_text,
        agent_id=payload.agent_id,
        skill_name=payload.skill_name,
        model_id=payload.model_id,
        budget_exceeded=payload.budget_exceeded,
        estop_active=payload.estop_active,
    )
    return PolicyCheckOut(
        allow=decision.allow,
        reason=decision.reason,
        risk_score=decision.risk_score,
        overrideable=decision.overrideable,
        rule=decision.rule,
        context_hash=decision.context_hash,
    )
