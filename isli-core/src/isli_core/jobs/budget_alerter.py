"""Background budget alert worker."""

import asyncio
import structlog
from datetime import datetime, timezone

from isli_core.db import async_session
from isli_core.budget import BudgetEngine, BudgetAlerter
from isli_core.redis_client import get_redis
from isli_core.event_manager import EventManager

logger = structlog.get_logger()

ALERT_INTERVAL_SECONDS = 300  # 5 minutes
ALERT_DEDUP_TTL_SECONDS = 86400  # 24 hours


class BudgetAlertWorker:
    @staticmethod
    async def loop() -> None:
        while True:
            await asyncio.sleep(ALERT_INTERVAL_SECONDS)
            try:
                await BudgetAlertWorker._run_once()
            except Exception as exc:
                logger.error("budget_alerter.error", error=str(exc))

    @staticmethod
    async def _run_once() -> None:
        if async_session is None:
            return

        redis = await get_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        async with async_session() as db:
            from sqlalchemy import select
            from isli_core.models import UserBudget, OrgBudget

            # Check user budgets
            user_result = await db.execute(select(UserBudget))
            for budget in user_result.scalars().all():
                try:
                    status = await BudgetEngine.get_user_budget_status(db, budget.user_id)
                    if not status:
                        continue
                    dedup_key = f"budget_alert:user:{budget.user_id}:{today}"
                    if await redis.get(dedup_key):
                        continue
                    alerted = False
                    if budget.monthly_token_cap:
                        pct = (status["token_used"] / budget.monthly_token_cap) * 100
                        if pct >= budget.alert_threshold_pct:
                            await BudgetAlerter.maybe_alert_user(
                                db, budget.user_id, status["token_used"], status["usd_used"]
                            )
                            alerted = True
                    if budget.monthly_usd_cap:
                        pct = (status["usd_used"] / budget.monthly_usd_cap) * 100
                        if pct >= budget.alert_threshold_pct:
                            await BudgetAlerter.maybe_alert_user(
                                db, budget.user_id, status["token_used"], status["usd_used"]
                            )
                            alerted = True
                    if alerted:
                        await redis.setex(dedup_key, ALERT_DEDUP_TTL_SECONDS, "1")
                        await EventManager.emit("system:alert", {
                            "severity": "warning",
                            "message": (
                                f"Budget threshold {budget.alert_threshold_pct:.0f}% "
                                f"reached for user {budget.user_id}."
                            ),
                            "user_id": budget.user_id,
                            "category": "budget_threshold",
                        })
                except Exception as exc:
                    logger.error("budget_alerter.user_error", user_id=budget.user_id, error=str(exc))

            # Check org budgets
            org_result = await db.execute(select(OrgBudget))
            for budget in org_result.scalars().all():
                try:
                    status = await BudgetEngine.get_org_budget_status(db, budget.org_id)
                    if not status:
                        continue
                    dedup_key = f"budget_alert:org:{budget.org_id}:{today}"
                    if await redis.get(dedup_key):
                        continue
                    alerted = False
                    if budget.monthly_token_cap:
                        pct = (status["token_used"] / budget.monthly_token_cap) * 100
                        if pct >= budget.alert_threshold_pct:
                            await BudgetAlerter.maybe_alert_org(
                                db, budget.org_id, status["token_used"], status["usd_used"]
                            )
                            alerted = True
                    if budget.monthly_usd_cap:
                        pct = (status["usd_used"] / budget.monthly_usd_cap) * 100
                        if pct >= budget.alert_threshold_pct:
                            await BudgetAlerter.maybe_alert_org(
                                db, budget.org_id, status["token_used"], status["usd_used"]
                            )
                            alerted = True
                    if alerted:
                        await redis.setex(dedup_key, ALERT_DEDUP_TTL_SECONDS, "1")
                except Exception as exc:
                    logger.error("budget_alerter.org_error", org_id=budget.org_id, error=str(exc))
