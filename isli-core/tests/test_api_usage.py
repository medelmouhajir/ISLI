"""API tests for the agent usage reporting endpoint."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Agent, UserBudget, OrgBudget, CostLedger
from isli_core.budget import BudgetExceededError
from isli_core.auth import create_internal_token


def _agent_token(agent_id: str) -> str:
    return create_internal_token(agent_id, scopes=["agent"])


class TestUsageEndpoint:
    @pytest.mark.asyncio
    async def test_record_usage_happy_path(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-usage-1", name="Usage Agent")
        db_session.add(agent)
        await db_session.commit()

        resp = await client.post("/v1/agents/agent-usage-1/usage", json={
            "input_tokens": 100,
            "output_tokens": 50,
            "reasoning_tokens": 0,
            "model_id": "gpt-4o",
            "task_id": None,
            "tier": "standard",
        }, headers={"Authorization": f"Bearer {_agent_token('agent-usage-1')}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "recorded"
        assert data["agent_id"] == "agent-usage-1"
        assert data["cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_record_usage_updates_token_used(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-usage-2", name="Usage Agent", token_used=10)
        db_session.add(agent)
        await db_session.commit()

        resp = await client.post("/v1/agents/agent-usage-2/usage", json={
            "input_tokens": 20,
            "output_tokens": 10,
            "reasoning_tokens": 0,
            "model_id": "gpt-4o",
        }, headers={"Authorization": f"Bearer {_agent_token('agent-usage-2')}"})
        assert resp.status_code == 200

        # Re-fetch agent to verify token_used incremented
        from sqlalchemy import select
        result = await db_session.execute(select(Agent).where(Agent.id == "agent-usage-2"))
        updated = result.scalar_one()
        await db_session.refresh(updated)
        assert updated.token_used == 40  # 10 + 20 + 10

    @pytest.mark.asyncio
    async def test_record_usage_creates_ledger_entry(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-usage-3", name="Usage Agent")
        db_session.add(agent)
        await db_session.commit()

        resp = await client.post("/v1/agents/agent-usage-3/usage", json={
            "input_tokens": 1000,
            "output_tokens": 500,
            "reasoning_tokens": 0,
            "model_id": "gpt-4o",
            "task_id": "task-123",
        }, headers={"Authorization": f"Bearer {_agent_token('agent-usage-3')}"})
        assert resp.status_code == 200

        from sqlalchemy import select
        result = await db_session.execute(
            select(CostLedger).where(CostLedger.agent_id == "agent-usage-3")
        )
        ledger = result.scalar_one()
        assert ledger.input_tokens == 1000
        assert ledger.output_tokens == 500
        assert ledger.model_id == "gpt-4o"
        assert ledger.task_id == "task-123"
        assert ledger.cost_usd > 0

    @pytest.mark.asyncio
    async def test_record_usage_unknown_model_zero_cost(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-usage-4", name="Usage Agent")
        db_session.add(agent)
        await db_session.commit()

        resp = await client.post("/v1/agents/agent-usage-4/usage", json={
            "input_tokens": 100,
            "output_tokens": 50,
            "model_id": "unknown-model-x",
        }, headers={"Authorization": f"Bearer {_agent_token('agent-usage-4')}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_record_usage_exceeds_agent_budget(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-usage-5", name="Usage Agent", token_budget=50, token_used=10)
        db_session.add(agent)
        await db_session.commit()

        resp = await client.post("/v1/agents/agent-usage-5/usage", json={
            "input_tokens": 30,
            "output_tokens": 20,
            "model_id": "gpt-4o",
        }, headers={"Authorization": f"Bearer {_agent_token('agent-usage-5')}"})
        assert resp.status_code == 429
        data = resp.json()
        assert "budget exceeded" in data["detail"].lower()

        # Verify agent was paused
        from sqlalchemy import select
        result = await db_session.execute(select(Agent).where(Agent.id == "agent-usage-5"))
        updated = result.scalar_one()
        await db_session.refresh(updated)
        assert updated.status == "paused"

    @pytest.mark.asyncio
    async def test_record_usage_exceeds_user_budget(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-usage-6", name="Usage Agent", user_id="user-over")
        budget = UserBudget(user_id="user-over", monthly_token_cap=100)
        db_session.add_all([agent, budget])
        await db_session.commit()

        resp = await client.post("/v1/agents/agent-usage-6/usage", json={
            "input_tokens": 60,
            "output_tokens": 50,
            "model_id": "gpt-4o",
        }, headers={"Authorization": f"Bearer {_agent_token('agent-usage-6')}"})
        assert resp.status_code == 429
        data = resp.json()
        assert "user" in data["detail"].lower() or "budget exceeded" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_record_usage_exceeds_org_budget(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-usage-7", name="Usage Agent", org_id="org-over")
        budget = OrgBudget(org_id="org-over", monthly_token_cap=100)
        db_session.add_all([agent, budget])
        await db_session.commit()

        resp = await client.post("/v1/agents/agent-usage-7/usage", json={
            "input_tokens": 60,
            "output_tokens": 50,
            "model_id": "gpt-4o",
        }, headers={"Authorization": f"Bearer {_agent_token('agent-usage-7')}"})
        assert resp.status_code == 429
        data = resp.json()
        assert "org" in data["detail"].lower() or "budget exceeded" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_record_usage_wrong_agent_auth(self, client: AsyncClient, db_session: AsyncSession):
        agent_a = Agent(id="agent-usage-8a", name="Agent A")
        agent_b = Agent(id="agent-usage-8b", name="Agent B")
        db_session.add_all([agent_a, agent_b])
        await db_session.commit()

        # Get token for agent_b, then try to report usage for agent_a
        from isli_core.auth import create_internal_token
        token = create_internal_token("agent-usage-8b", scopes=["agent"])

        resp = await client.post(
            "/v1/agents/agent-usage-8a/usage",
            json={"input_tokens": 10, "output_tokens": 5, "model_id": "gpt-4o"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cost_history_endpoint(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-history-1", name="History Agent")
        ledger = CostLedger(
            agent_id="agent-history-1",
            model_id="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            cost_usd=1.25,
        )
        db_session.add_all([agent, ledger])
        await db_session.commit()

        resp = await client.get("/v1/system/cost/history?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["cost_usd"] >= 1.25

    @pytest.mark.asyncio
    async def test_cost_by_tier_endpoint(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-tier-1", name="Tier Agent")
        ledger = CostLedger(
            agent_id="agent-tier-1",
            model_id="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            cost_usd=1.25,
            tier="premium",
        )
        db_session.add_all([agent, ledger])
        await db_session.commit()

        resp = await client.get("/v1/system/cost/by-tier")
        assert resp.status_code == 200
        data = resp.json()
        premium = [d for d in data if d["tier"] == "premium"]
        assert len(premium) >= 1
        assert premium[0]["cost_usd"] >= 1.25
        assert premium[0]["turns"] >= 1
