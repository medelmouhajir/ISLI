"""Transparency and audit endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.db import get_db
from isli_core.model_transparency import TransparencyService

router = APIRouter(prefix="/tasks", tags=["transparency"])


class TransparencyOut(BaseModel):
    task_id: str
    agent_id: str | None
    model_id: str | None
    selection_reason: str | None
    total_cost_usd: float
    turns: list[dict[str, Any]]
    audit_entries: list[dict[str, Any]]


@router.get("/{task_id}/transparency", response_model=TransparencyOut)
async def get_transparency(task_id: str, db: AsyncSession = Depends(get_db)):
    report = await TransparencyService.build_report(db, task_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return report
