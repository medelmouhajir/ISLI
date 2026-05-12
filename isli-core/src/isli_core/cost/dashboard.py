"""Per-agent cost dashboard: cost ledger queries."""

import structlog
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import CostLedger, Agent

logger = structlog.get_logger()


class CostDashboard:
    """Query cost data for Kanban Agent Status Bar widget."""

    @staticmethod
    async def agent_summary(session: AsyncSession, agent_id: str, days: int = 30) -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await session.execute(
            select(
                func.sum(CostLedger.input_tokens),
                func.sum(CostLedger.output_tokens),
                func.sum(CostLedger.cost_usd),
                func.count(CostLedger.id),
            ).where(
                CostLedger.agent_id == agent_id,
                CostLedger.created_at >= cutoff,
            )
        )
        row = result.one_or_none()
        return {
            "agent_id": agent_id,
            "period_days": days,
            "input_tokens": int(row[0] or 0),
            "output_tokens": int(row[1] or 0),
            "cost_usd": float(row[2] or 0.0),
            "turns": int(row[3] or 0),
            "avg_cost_per_turn": round(float(row[2] or 0.0) / max(row[3] or 1, 1), 6),
        }

    @staticmethod
    async def all_agents_summary(session: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await session.execute(
            select(
                CostLedger.agent_id,
                func.sum(CostLedger.input_tokens),
                func.sum(CostLedger.output_tokens),
                func.sum(CostLedger.cost_usd),
                func.count(CostLedger.id),
            )
            .where(CostLedger.created_at >= cutoff)
            .group_by(CostLedger.agent_id)
            .order_by(func.sum(CostLedger.cost_usd).desc())
        )
        rows = result.all()
        return [
            {
                "agent_id": row[0],
                "input_tokens": int(row[1] or 0),
                "output_tokens": int(row[2] or 0),
                "cost_usd": float(row[3] or 0.0),
                "turns": int(row[4] or 0),
            }
            for row in rows
        ]

    @staticmethod
    async def record_turn(
        session: AsyncSession,
        agent_id: str,
        task_id: str | None,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        tier: str = "standard",
    ) -> CostLedger:
        from isli_core.cost.rate_card import CostEstimator
        cost = CostEstimator.estimate_turn(model_id, input_tokens, output_tokens)
        entry = CostLedger(
            agent_id=agent_id,
            task_id=task_id,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            tier=tier,
        )
        session.add(entry)
        await session.flush()
        logger.info("cost.recorded", agent_id=agent_id, cost_usd=cost, model=model_id)
        return entry
