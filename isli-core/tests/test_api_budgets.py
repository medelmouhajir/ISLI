"""API tests for budget engine and system budget endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Agent, UserBudget, OrgBudget, CostLedger
from isli_core.budget import BudgetEngine, BudgetAlerter, UserBudgetExceededError, OrgBudgetExceededError


class TestBudgetEngine:
    @pytest.mark.asyncio
    async def test_user_budget_blocks_when_exceeded(self, db_session: AsyncSession):
        agent = Agent(id="agent-budget-block", name="Test Agent", user_id="user-block", token_budget=None)
        budget = UserBudget(user_id="user-block", monthly_token_cap=100)
        db_session.add_all([agent, budget])
        await db_session.commit()

        with pytest.raises(UserBudgetExceededError):
            await BudgetEngine.check_user_budget(db_session, "user-block", 60, 50)

    @pytest.mark.asyncio
    async def test_user_budget_allows_when_under(self, db_session: AsyncSession):
        agent = Agent(id="agent-budget-allow", name="Test Agent", user_id="user-allow", token_budget=None)
        budget = UserBudget(user_id="user-allow", monthly_token_cap=1000)
        db_session.add_all([agent, budget])
        await db_session.commit()

        await BudgetEngine.check_user_budget(db_session, "user-allow", 10, 20)

    @pytest.mark.asyncio
    async def test_user_budget_considers_cost_ledger(self, db_session: AsyncSession):
        agent = Agent(id="agent-budget-ledger", name="Test Agent", user_id="user-ledger")
        budget = UserBudget(user_id="user-ledger", monthly_token_cap=100)
        ledger = CostLedger(agent_id="agent-budget-ledger", model_id="gpt-4o", input_tokens=80, output_tokens=10, cost_usd=0.1)
        db_session.add_all([agent, budget, ledger])
        await db_session.commit()

        with pytest.raises(UserBudgetExceededError):
            await BudgetEngine.check_user_budget(db_session, "user-ledger", 5, 10)

    @pytest.mark.asyncio
    async def test_org_budget_blocks_when_exceeded(self, db_session: AsyncSession):
        agent = Agent(id="agent-org-block", name="Test Agent", org_id="org-block")
        budget = OrgBudget(org_id="org-block", monthly_token_cap=50)
        db_session.add_all([agent, budget])
        await db_session.commit()

        with pytest.raises(OrgBudgetExceededError):
            await BudgetEngine.check_org_budget(db_session, "org-block", 30, 25)

    @pytest.mark.asyncio
    async def test_budget_status_returns_correct_usage(self, db_session: AsyncSession):
        agent = Agent(id="agent-status", name="Test Agent", user_id="user-status")
        budget = UserBudget(user_id="user-status", monthly_token_cap=1000, monthly_usd_cap=10.0)
        ledger = CostLedger(agent_id="agent-status", model_id="gpt-4o", input_tokens=100, output_tokens=50, cost_usd=0.5)
        db_session.add_all([agent, budget, ledger])
        await db_session.commit()

        status = await BudgetEngine.get_user_budget_status(db_session, "user-status")
        assert status is not None
        assert status["token_used"] == 150
        assert status["usd_used"] == 0.5


class TestBudgetAPI:
    @pytest.mark.asyncio
    async def test_create_user_budget(self, client: AsyncClient):
        resp = await client.post("/v1/system/budgets/user", json={
            "user_id": "user-api-1",
            "monthly_token_cap": 1000,
            "monthly_usd_cap": 5.0,
            "alert_threshold_pct": 75.0,
            "slack_webhook_url": "https://hooks.slack.com/services/test",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["user_id"] == "user-api-1"
        assert data["monthly_token_cap"] == 1000
        assert data["alert_threshold_pct"] == 75.0

    @pytest.mark.asyncio
    async def test_create_org_budget(self, client: AsyncClient):
        resp = await client.post("/v1/system/budgets/org", json={
            "org_id": "org-api-1",
            "monthly_token_cap": 5000,
            "slack_webhook_url": "https://hooks.slack.com/services/org-test",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["org_id"] == "org-api-1"
        assert data["monthly_token_cap"] == 5000

    @pytest.mark.asyncio
    async def test_list_budgets(self, client: AsyncClient, db_session: AsyncSession):
        db_session.add(UserBudget(user_id="user-list-a", monthly_token_cap=100))
        db_session.add(OrgBudget(org_id="org-list-a", monthly_token_cap=200))
        await db_session.commit()

        resp = await client.get("/v1/system/budgets")
        assert resp.status_code == 200
        data = resp.json()
        user_entries = [d for d in data if d["scope"] == "user" and d["scope_id"].startswith("user-list")]
        org_entries = [d for d in data if d["scope"] == "org" and d["scope_id"].startswith("org-list")]
        assert len(user_entries) >= 1
        assert len(org_entries) >= 1

    @pytest.mark.asyncio
    async def test_get_user_budget(self, client: AsyncClient, db_session: AsyncSession):
        db_session.add(UserBudget(user_id="user-get-b", monthly_token_cap=300, alert_threshold_pct=90.0))
        await db_session.commit()

        resp = await client.get("/v1/system/budgets/user/user-get-b")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope"] == "user"
        assert data["scope_id"] == "user-get-b"
        assert data["monthly_token_cap"] == 300
        assert data["alert_threshold_pct"] == 90.0

    @pytest.mark.asyncio
    async def test_get_budget_not_found(self, client: AsyncClient):
        resp = await client.get("/v1/system/budgets/user/unknown-user")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_user_budget_duplicate(self, client: AsyncClient):
        await client.post("/v1/system/budgets/user", json={"user_id": "user-dup-x", "monthly_token_cap": 100})
        resp = await client.post("/v1/system/budgets/user", json={"user_id": "user-dup-x", "monthly_token_cap": 200})
        assert resp.status_code == 409


class TestBudgetAlerter:
    @pytest.mark.asyncio
    async def test_alert_payload_format(self):
        sent = await BudgetAlerter.send_alert(
            webhook_url="https://hooks.slack.com/services/fake",
            scope="user",
            scope_id="u-1",
            metric="tokens",
            used=850,
            cap=1000,
            threshold_pct=80.0,
        )
        assert sent is False

    @pytest.mark.asyncio
    async def test_maybe_alert_user_triggers(self, db_session: AsyncSession):
        budget = UserBudget(user_id="user-alert-x", monthly_token_cap=100, alert_threshold_pct=50.0, slack_webhook_url="https://hooks.slack.com/services/fake")
        agent = Agent(id="agent-alert-x", name="Alert Agent", user_id="user-alert-x")
        ledger = CostLedger(agent_id="agent-alert-x", model_id="gpt-4o", input_tokens=60, output_tokens=0, cost_usd=0.1)
        db_session.add_all([budget, agent, ledger])
        await db_session.commit()

        await BudgetAlerter.maybe_alert_user(db_session, "user-alert-x", 60, 0.1)

    @pytest.mark.asyncio
    async def test_maybe_alert_user_no_budget(self, db_session: AsyncSession):
        await BudgetAlerter.maybe_alert_user(db_session, "user-none-x", 0, 0.0)

    @pytest.mark.asyncio
    async def test_maybe_alert_user_below_threshold(self, db_session: AsyncSession):
        budget = UserBudget(user_id="user-low-x", monthly_token_cap=1000, alert_threshold_pct=90.0, slack_webhook_url="https://hooks.slack.com/services/fake")
        db_session.add(budget)
        await db_session.commit()

        await BudgetAlerter.maybe_alert_user(db_session, "user-low-x", 50, 0.1)


class TestAgentBudgetWiring:
    @pytest.mark.asyncio
    async def test_create_agent_with_user_org(self, client: AsyncClient):
        resp = await client.post("/v1/agents", json={
            "id": "agent-budget-99",
            "name": "Budget Agent",
            "user_id": "user-99",
            "org_id": "org-99",
            "token_budget": 5000,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["user_id"] == "user-99"
        assert data["org_id"] == "org-99"
        assert data["token_budget"] == 5000

    @pytest.mark.asyncio
    async def test_update_agent_user_id(self, client: AsyncClient):
        await client.post("/v1/agents", json={"id": "agent-budget-98", "name": "Budget Agent 2"})
        resp = await client.put("/v1/agents/agent-budget-98", json={"user_id": "user-new-98"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "user-new-98"
