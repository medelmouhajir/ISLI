"""Cost anomaly detection: per-agent p95 historical baselines + alert routing."""

import structlog
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import CostLedger

logger = structlog.get_logger()

DEFAULT_WINDOW_DAYS = 7
DEFAULT_Z_SCORE_THRESHOLD = 2.0


class CostAnomalyDetector:
    """Detect anomalous spend based on per-agent p95 historical baseline."""

    @staticmethod
    async def _agent_daily_costs(session: AsyncSession, agent_id: str, days: int) -> list[float]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await session.execute(
            select(
                func.date_trunc("day", CostLedger.created_at),
                func.sum(CostLedger.cost_usd),
            )
            .where(
                CostLedger.agent_id == agent_id,
                CostLedger.created_at >= cutoff,
            )
            .group_by(func.date_trunc("day", CostLedger.created_at))
            .order_by(func.date_trunc("day", CostLedger.created_at))
        )
        return [float(row[1] or 0.0) for row in result.all()]

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _stddev(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = CostAnomalyDetector._mean(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5

    @staticmethod
    async def check_agent(session: AsyncSession, agent_id: str) -> dict[str, Any]:
        daily = await CostAnomalyDetector._agent_daily_costs(session, agent_id, DEFAULT_WINDOW_DAYS)
        if len(daily) < 3:
            return {"agent_id": agent_id, "anomaly": False, "reason": "insufficient_data"}

        mean = CostAnomalyDetector._mean(daily)
        stddev = CostAnomalyDetector._stddev(daily)
        p95 = sorted(daily)[int(len(daily) * 0.95)] if len(daily) >= 20 else max(daily)
        today = daily[-1] if daily else 0.0

        z_score = (today - mean) / stddev if stddev > 0 else 0.0
        anomaly = z_score > DEFAULT_Z_SCORE_THRESHOLD or today > p95 * 2

        if anomaly:
            logger.warning(
                "anomaly.detected",
                agent_id=agent_id,
                today=today,
                mean=mean,
                stddev=stddev,
                p95=p95,
                z_score=z_score,
            )

        return {
            "agent_id": agent_id,
            "anomaly": anomaly,
            "today_cost": round(today, 4),
            "mean_cost": round(mean, 4),
            "stddev": round(stddev, 4),
            "p95": round(p95, 4),
            "z_score": round(z_score, 2),
        }
