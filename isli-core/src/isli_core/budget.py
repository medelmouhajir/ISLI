from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
import structlog
from fastapi import HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Agent, CostLedger, UserBudget, OrgBudget
from isli_core.cost.rate_card import CostEstimator

logger = structlog.get_logger()


class BudgetExceededError(HTTPException):
    def __init__(self, agent_id: str, budget: int, used: int):
        super().__init__(
            status_code=429,
            detail=f"Agent {agent_id} token budget exceeded: {used}/{budget}",
        )


class UserBudgetExceededError(HTTPException):
    def __init__(self, user_id: str, cap: float | int, used: float | int, metric: str = "tokens"):
        super().__init__(
            status_code=429,
            detail=f"User {user_id} {metric} budget exceeded: {used}/{cap}",
        )


class OrgBudgetExceededError(HTTPException):
    def __init__(self, org_id: str, cap: float | int, used: float | int, metric: str = "tokens"):
        super().__init__(
            status_code=429,
            detail=f"Org {org_id} {metric} budget exceeded: {used}/{cap}",
        )


async def check_budget(
    session: AsyncSession,
    agent_id: str,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int = 0,
    task_id: str | None = None,
) -> None:
    result = await session.execute(
        select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None))
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Agent-level token budget (input + output + reasoning)
    if agent.token_budget is not None:
        total = agent.token_used + input_tokens + output_tokens + reasoning_tokens
        if total > agent.token_budget:
            await session.execute(
                update(Agent)
                .where(Agent.id == agent_id)
                .values(status="paused", status_reason=f"Budget exceeded: {total}/{agent.token_budget}")
            )
            await session.commit()
            raise BudgetExceededError(agent_id, agent.token_budget, total)

    # Agent-level reasoning budget
    if agent.reasoning_budget is not None and reasoning_tokens > 0:
        # reasoning_tokens are included in token_used already, but check specifically
        current_reasoning = agent.token_used  # approximate; in full impl track separately
        if reasoning_tokens > agent.reasoning_budget:
            raise HTTPException(
                status_code=429,
                detail=f"Agent {agent_id} reasoning budget exceeded: {reasoning_tokens}/{agent.reasoning_budget}",
            )

    # Per-task budgets
    if task_id is not None:
        from isli_core.models import Task
        task_result = await session.execute(
            select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
        )
        task = task_result.scalar_one_or_none()
        if task:
            if task.task_token_budget is not None:
                task_total = input_tokens + output_tokens + reasoning_tokens
                if task_total > task.task_token_budget:
                    task.status = "blocked"
                    task.blocked_reason = f"Task token budget exceeded: {task_total}/{task.task_token_budget}"
                    await session.commit()
                    raise HTTPException(
                        status_code=429,
                        detail=f"Task {task_id} token budget exceeded: {task_total}/{task.task_token_budget}",
                    )
            if task.reasoning_token_budget is not None and reasoning_tokens > 0:
                if reasoning_tokens > task.reasoning_token_budget:
                    task.status = "blocked"
                    task.blocked_reason = f"Task reasoning budget exceeded: {reasoning_tokens}/{task.reasoning_token_budget}"
                    await session.commit()
                    raise HTTPException(
                        status_code=429,
                        detail=f"Task {task_id} reasoning budget exceeded: {reasoning_tokens}/{task.reasoning_token_budget}",
                    )


async def charge_tokens(
    session: AsyncSession,
    agent_id: str,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int = 0,
) -> None:
    await session.execute(
        update(Agent)
        .where(Agent.id == agent_id)
        .values(token_used=Agent.token_used + input_tokens + output_tokens + reasoning_tokens)
    )


class BudgetEngine:
    """Evaluate user-level and org-level budget constraints."""

    @staticmethod
    async def _monthly_agent_spend(session: AsyncSession, agent_id: str) -> tuple[int, float]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        result = await session.execute(
            select(
                func.sum(CostLedger.input_tokens + CostLedger.output_tokens + CostLedger.reasoning_tokens),
                func.sum(CostLedger.cost_usd),
            ).where(
                CostLedger.agent_id == agent_id,
                CostLedger.created_at >= cutoff,
            )
        )
        row = result.one_or_none()
        return (int(row[0] or 0), float(row[1] or 0.0))

    @staticmethod
    async def _monthly_user_spend(session: AsyncSession, user_id: str) -> tuple[int, float]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        agent_ids_result = await session.execute(
            select(Agent.id).where(
                Agent.user_id == user_id,
                Agent.deleted_at.is_(None),
            )
        )
        agent_ids = [r[0] for r in agent_ids_result.all()]
        if not agent_ids:
            return (0, 0.0)
        result = await session.execute(
            select(
                func.sum(CostLedger.input_tokens + CostLedger.output_tokens + CostLedger.reasoning_tokens),
                func.sum(CostLedger.cost_usd),
            ).where(
                CostLedger.agent_id.in_(agent_ids),
                CostLedger.created_at >= cutoff,
            )
        )
        row = result.one_or_none()
        return (int(row[0] or 0), float(row[1] or 0.0))

    @staticmethod
    async def _monthly_org_spend(session: AsyncSession, org_id: str) -> tuple[int, float]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        agent_ids_result = await session.execute(
            select(Agent.id).where(
                Agent.org_id == org_id,
                Agent.deleted_at.is_(None),
            )
        )
        agent_ids = [r[0] for r in agent_ids_result.all()]
        if not agent_ids:
            return (0, 0.0)
        result = await session.execute(
            select(
                func.sum(CostLedger.input_tokens + CostLedger.output_tokens + CostLedger.reasoning_tokens),
                func.sum(CostLedger.cost_usd),
            ).where(
                CostLedger.agent_id.in_(agent_ids),
                CostLedger.created_at >= cutoff,
            )
        )
        row = result.one_or_none()
        return (int(row[0] or 0), float(row[1] or 0.0))

    @staticmethod
    async def check_user_budget(
        session: AsyncSession,
        user_id: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int = 0,
        model_id: str | None = None,
    ) -> None:
        budget_result = await session.execute(
            select(UserBudget).where(UserBudget.user_id == user_id)
        )
        budget = budget_result.scalar_one_or_none()
        if budget is None:
            return

        tokens_used, usd_used = await BudgetEngine._monthly_user_spend(session, user_id)
        projected_tokens = tokens_used + input_tokens + output_tokens + reasoning_tokens

        if budget.monthly_token_cap and projected_tokens > budget.monthly_token_cap:
            raise UserBudgetExceededError(user_id, budget.monthly_token_cap, projected_tokens, "tokens")

        if budget.monthly_usd_cap and model_id:
            projected_usd = usd_used + CostEstimator.estimate_turn(model_id, input_tokens, output_tokens, reasoning_tokens)
            if projected_usd > budget.monthly_usd_cap:
                raise UserBudgetExceededError(user_id, budget.monthly_usd_cap, round(projected_usd, 4), "USD")

    @staticmethod
    async def check_org_budget(
        session: AsyncSession,
        org_id: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int = 0,
        model_id: str | None = None,
    ) -> None:
        budget_result = await session.execute(
            select(OrgBudget).where(OrgBudget.org_id == org_id)
        )
        budget = budget_result.scalar_one_or_none()
        if budget is None:
            return

        tokens_used, usd_used = await BudgetEngine._monthly_org_spend(session, org_id)
        projected_tokens = tokens_used + input_tokens + output_tokens + reasoning_tokens

        if budget.monthly_token_cap and projected_tokens > budget.monthly_token_cap:
            raise OrgBudgetExceededError(org_id, budget.monthly_token_cap, projected_tokens, "tokens")

        if budget.monthly_usd_cap and model_id:
            projected_usd = usd_used + CostEstimator.estimate_turn(model_id, input_tokens, output_tokens, reasoning_tokens)
            if projected_usd > budget.monthly_usd_cap:
                raise OrgBudgetExceededError(org_id, budget.monthly_usd_cap, round(projected_usd, 4), "USD")

    @staticmethod
    async def get_user_budget_status(session: AsyncSession, user_id: str) -> dict[str, Any] | None:
        budget_result = await session.execute(
            select(UserBudget).where(UserBudget.user_id == user_id)
        )
        budget = budget_result.scalar_one_or_none()
        if budget is None:
            return None
        tokens_used, usd_used = await BudgetEngine._monthly_user_spend(session, user_id)
        return {
            "user_id": user_id,
            "monthly_token_cap": budget.monthly_token_cap,
            "monthly_usd_cap": budget.monthly_usd_cap,
            "token_used": tokens_used,
            "usd_used": round(usd_used, 4),
            "alert_threshold_pct": budget.alert_threshold_pct,
            "slack_webhook_url": budget.slack_webhook_url,
        }

    @staticmethod
    async def get_org_budget_status(session: AsyncSession, org_id: str) -> dict[str, Any] | None:
        budget_result = await session.execute(
            select(OrgBudget).where(OrgBudget.org_id == org_id)
        )
        budget = budget_result.scalar_one_or_none()
        if budget is None:
            return None
        tokens_used, usd_used = await BudgetEngine._monthly_org_spend(session, org_id)
        return {
            "org_id": org_id,
            "monthly_token_cap": budget.monthly_token_cap,
            "monthly_usd_cap": budget.monthly_usd_cap,
            "token_used": tokens_used,
            "usd_used": round(usd_used, 4),
            "alert_threshold_pct": budget.alert_threshold_pct,
            "slack_webhook_url": budget.slack_webhook_url,
        }


class BudgetAlerter:
    """Send budget threshold alerts to Slack webhooks."""

    @staticmethod
    async def send_alert(
        webhook_url: str,
        scope: str,
        scope_id: str,
        metric: str,
        used: float,
        cap: float,
        threshold_pct: float,
    ) -> bool:
        try:
            payload = {
                "text": (
                    f"Budget Alert: *{scope}* `{scope_id}` has exceeded "
                    f"{threshold_pct}% of its monthly {metric} budget.\n"
                    f"Used: {used} / Cap: {cap}"
                ),
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*Budget Alert*\n"
                                f"Scope: `{scope}` | ID: `{scope_id}`\n"
                                f"Metric: `{metric}`\n"
                                f"Used: `{used}` / Cap: `{cap}` ({threshold_pct}% threshold)"
                            ),
                        },
                    }
                ],
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json=payload)
                resp.raise_for_status()
            logger.info("budget.alert_sent", scope=scope, scope_id=scope_id, metric=metric)
            return True
        except Exception as exc:
            logger.error("budget.alert_failed", scope=scope, scope_id=scope_id, error=str(exc))
            return False

    @staticmethod
    async def maybe_alert_user(session: AsyncSession, user_id: str, used: int, usd_used: float) -> None:
        budget_result = await session.execute(
            select(UserBudget).where(UserBudget.user_id == user_id)
        )
        budget = budget_result.scalar_one_or_none()
        if budget is None or not budget.slack_webhook_url:
            return
        if budget.monthly_token_cap:
            pct = (used / budget.monthly_token_cap) * 100
            if pct >= budget.alert_threshold_pct:
                await BudgetAlerter.send_alert(
                    budget.slack_webhook_url, "user", user_id, "tokens", used, budget.monthly_token_cap, budget.alert_threshold_pct
                )
        if budget.monthly_usd_cap:
            pct = (usd_used / budget.monthly_usd_cap) * 100
            if pct >= budget.alert_threshold_pct:
                await BudgetAlerter.send_alert(
                    budget.slack_webhook_url, "user", user_id, "USD", round(usd_used, 4), budget.monthly_usd_cap, budget.alert_threshold_pct
                )

    @staticmethod
    async def maybe_alert_org(session: AsyncSession, org_id: str, used: int, usd_used: float) -> None:
        budget_result = await session.execute(
            select(OrgBudget).where(OrgBudget.org_id == org_id)
        )
        budget = budget_result.scalar_one_or_none()
        if budget is None or not budget.slack_webhook_url:
            return
        if budget.monthly_token_cap:
            pct = (used / budget.monthly_token_cap) * 100
            if pct >= budget.alert_threshold_pct:
                await BudgetAlerter.send_alert(
                    budget.slack_webhook_url, "org", org_id, "tokens", used, budget.monthly_token_cap, budget.alert_threshold_pct
                )
        if budget.monthly_usd_cap:
            pct = (usd_used / budget.monthly_usd_cap) * 100
            if pct >= budget.alert_threshold_pct:
                await BudgetAlerter.send_alert(
                    budget.slack_webhook_url, "org", org_id, "USD", round(usd_used, 4), budget.monthly_usd_cap, budget.alert_threshold_pct
                )
