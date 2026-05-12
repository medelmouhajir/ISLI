"""Tests for reasoning model detection, token prediction, and reasoning budgets."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.cost.reasoning_detector import ReasoningDetector
from isli_core.cost.token_predictor import TokenPredictor
from isli_core.cost.rate_card import CostEstimator, RATE_CARD
from isli_core.cost.dashboard import CostDashboard
from isli_core.cost.tiering import ModelTiering
from isli_core.budget import check_budget, charge_tokens, BudgetExceededError
from isli_core.models import Agent, Task, CostLedger


class TestReasoningDetector:
    def test_o1_is_reasoning(self):
        assert ReasoningDetector.is_reasoning_model("o1") is True

    def test_gpt4o_is_not_reasoning(self):
        assert ReasoningDetector.is_reasoning_model("gpt-4o") is False

    def test_multiplier_for_o1(self):
        assert ReasoningDetector.get_multiplier("o1") == 3.0

    def test_multiplier_for_gpt4o(self):
        assert ReasoningDetector.get_multiplier("gpt-4o") == 1.0

    def test_unknown_model_default_multiplier(self):
        assert ReasoningDetector.get_multiplier("unknown") == 1.0


class TestTokenPredictor:
    def test_estimate_simple_prompt(self):
        est = TokenPredictor.estimate("Hello world", "gpt-4o")
        assert est["input_tokens"] > 0
        assert est["reasoning_tokens"] == 0
        assert est["output_tokens"] == TokenPredictor.DEFAULT_MAX_TOKENS

    def test_estimate_reasoning_model(self):
        est = TokenPredictor.estimate("Solve this complex problem", "o1")
        assert est["reasoning_tokens"] > 0
        assert est["total_tokens"] == est["input_tokens"] + est["reasoning_tokens"] + est["output_tokens"]

    def test_estimate_with_history(self):
        est = TokenPredictor.estimate("Follow up", "gpt-4o", history_messages=[{"content": "Previous message"}])
        assert est["input_tokens"] > TokenPredictor.SYSTEM_OVERHEAD

    def test_estimate_with_max_tokens(self):
        est = TokenPredictor.estimate("Short", "gpt-4o", max_tokens=100)
        assert est["output_tokens"] == 100


class TestRateCardReasoning:
    def test_reasoning_model_has_reasoning_rate(self):
        rate = RATE_CARD["o1"]
        assert rate.reasoning_per_1k > 0

    def test_non_reasoning_model_has_zero_reasoning_rate(self):
        rate = RATE_CARD["gpt-4o"]
        assert rate.reasoning_per_1k == 0.0

    def test_estimate_turn_with_reasoning(self):
        cost = CostEstimator.estimate_turn("o1", 1000, 500, reasoning_tokens=2000)
        assert cost > 0
        # reasoning should add cost
        cost_no_reasoning = CostEstimator.estimate_turn("o1", 1000, 500, reasoning_tokens=0)
        assert cost > cost_no_reasoning


class TestBudgetReasoning:
    @pytest.mark.asyncio
    async def test_check_budget_blocks_on_reasoning(self, db_session: AsyncSession):
        agent = Agent(id="agent-reason-1", name="Reason Agent", token_budget=10000, reasoning_budget=100)
        db_session.add(agent)
        await db_session.commit()

        with pytest.raises(Exception) as exc_info:
            await check_budget(db_session, "agent-reason-1", 100, 100, reasoning_tokens=200)
        assert "reasoning budget exceeded" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_check_budget_allows_under_reasoning_cap(self, db_session: AsyncSession):
        agent = Agent(id="agent-reason-2", name="Reason Agent", token_budget=10000, reasoning_budget=500)
        db_session.add(agent)
        await db_session.commit()

        await check_budget(db_session, "agent-reason-2", 100, 100, reasoning_tokens=200)

    @pytest.mark.asyncio
    async def test_task_token_budget_blocks(self, db_session: AsyncSession):
        agent = Agent(id="agent-reason-3", name="Reason Agent", token_budget=10000)
        task = Task(id="task-reason-1", title="Reason Task", type="task", status="doing", agent_id="agent-reason-3", created_by="user-1", task_token_budget=500)
        db_session.add_all([agent, task])
        await db_session.commit()

        with pytest.raises(Exception) as exc_info:
            await check_budget(db_session, "agent-reason-3", 300, 300, reasoning_tokens=0, task_id="task-reason-1")
        assert "token budget exceeded" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_task_reasoning_budget_blocks(self, db_session: AsyncSession):
        agent = Agent(id="agent-reason-4", name="Reason Agent", token_budget=10000)
        task = Task(id="task-reason-2", title="Reason Task", type="task", status="doing", agent_id="agent-reason-4", created_by="user-1", reasoning_token_budget=100)
        db_session.add_all([agent, task])
        await db_session.commit()

        with pytest.raises(Exception) as exc_info:
            await check_budget(db_session, "agent-reason-4", 50, 50, reasoning_tokens=200, task_id="task-reason-2")
        assert "reasoning budget exceeded" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_charge_tokens_includes_reasoning(self, db_session: AsyncSession):
        agent = Agent(id="agent-reason-5", name="Reason Agent", token_used=0)
        db_session.add(agent)
        await db_session.commit()

        await charge_tokens(db_session, "agent-reason-5", 100, 50, reasoning_tokens=25)
        await db_session.commit()

        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(Agent).where(Agent.id == "agent-reason-5")
        )
        updated = result.scalar_one()
        assert updated.token_used == 175


class TestDashboardReasoning:
    @pytest.mark.asyncio
    async def test_record_turn_stores_reasoning_tokens(self, db_session: AsyncSession):
        ledger = await CostDashboard.record_turn(
            db_session, "agent-reason-6", "task-reason-3", "o1",
            input_tokens=100, output_tokens=50, reasoning_tokens=200, tier="premium"
        )
        await db_session.commit()
        assert ledger.reasoning_tokens == 200
        assert ledger.cost_usd > 0

    @pytest.mark.asyncio
    async def test_agent_summary_includes_reasoning(self, db_session: AsyncSession):
        await CostDashboard.record_turn(
            db_session, "agent-reason-7", None, "o1",
            input_tokens=100, output_tokens=50, reasoning_tokens=200
        )
        await db_session.commit()
        summary = await CostDashboard.agent_summary(db_session, "agent-reason-7")
        assert summary["reasoning_tokens"] == 200


class TestTieringReasoning:
    @pytest.mark.asyncio
    async def test_downgrades_on_low_reasoning_budget(self):
        config = {"tier": "premium", "reasoning_budget": 1000}

        async def call_fn(model):
            return {"ok": True}

        result = await ModelTiering.attempt_with_fallback(config, call_fn, budget_remaining=100.0)
        # Should downgrade from premium (claude-opus-4-7-thinking) because reasoning budget is low
        assert result["tier"] == "standard"
        assert result["model"] not in ("o1", "claude-opus-4-7-thinking")
