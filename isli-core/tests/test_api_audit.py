"""Tests for audit trail and transparency."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Agent, Task, CostLedger, CheckPoint, AuditLog
from isli_core.audit_writer import AuditWriter
from isli_core.compliance.audit_integrity import AuditIntegrity


class TestAuditWriter:
    @pytest.mark.asyncio
    async def test_audit_row_has_chain_hash(self, db_session: AsyncSession):
        log = await AuditWriter.write(
            db_session,
            actor_type="user",
            actor_id="user-1",
            action="create_agent",
            target_type="agent",
            target_id="agent-audit-1",
            payload={"name": "Test"},
        )
        assert log.chain_hash is not None
        assert len(log.chain_hash) == 64

    @pytest.mark.asyncio
    async def test_audit_chain_links(self, db_session: AsyncSession):
        log1 = await AuditWriter.write(db_session, actor_type="user", actor_id="u1", action="a", target_type="agent", target_id="a1")
        log2 = await AuditWriter.write(db_session, actor_type="user", actor_id="u1", action="b", target_type="agent", target_id="a1")
        assert log1.chain_hash != log2.chain_hash

    @pytest.mark.asyncio
    async def test_audit_integrity_verifies(self, db_session: AsyncSession):
        await AuditWriter.write(db_session, actor_type="user", actor_id="u1", action="a", target_type="agent", target_id="a1")
        result = await AuditIntegrity.verify_chain(db_session)
        assert result["verified"] is True
        assert result["tampered_rows"] == []

    @pytest.mark.asyncio
    async def test_audit_integrity_detects_tamper(self, db_session: AsyncSession):
        log = await AuditWriter.write(db_session, actor_type="user", actor_id="u1", action="a", target_type="agent", target_id="a1")
        # Tamper with the row
        log.action = "tampered"
        await db_session.commit()

        result = await AuditIntegrity.verify_chain(db_session)
        assert result["verified"] is False
        assert len(result["tampered_rows"]) >= 1


class TestAuditAPI:
    @pytest.mark.asyncio
    async def test_create_agent_writes_audit(self, client: AsyncClient, db_session: AsyncSession):
        resp = await client.post("/v1/agents", json={"id": "agent-audit-api-1", "name": "Audit Agent"})
        assert resp.status_code == 201

        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(AuditLog).where(AuditLog.target_id == "agent-audit-api-1")
        )
        logs = list(result.scalars().all())
        assert len(logs) >= 1
        assert logs[0].chain_hash is not None

    @pytest.mark.asyncio
    async def test_update_agent_writes_audit(self, client: AsyncClient, db_session: AsyncSession):
        await client.post("/v1/agents", json={"id": "agent-audit-api-2", "name": "Audit Agent"})
        resp = await client.put("/v1/agents/agent-audit-api-2", json={"name": "Updated"})
        assert resp.status_code == 200

        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(AuditLog).where(
                AuditLog.target_id == "agent-audit-api-2",
                AuditLog.action == "update_agent",
            )
        )
        logs = list(result.scalars().all())
        assert len(logs) >= 1

    @pytest.mark.asyncio
    async def test_create_task_writes_audit(self, client: AsyncClient, db_session: AsyncSession):
        resp = await client.post("/v1/tasks", json={"title": "Audit Task", "created_by": "user-1"})
        assert resp.status_code == 201
        task_id = resp.json()["id"]

        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(AuditLog).where(AuditLog.target_id == task_id)
        )
        logs = list(result.scalars().all())
        assert len(logs) >= 1
        assert logs[0].action == "create_task"

    @pytest.mark.asyncio
    async def test_audit_logs_endpoint(self, client: AsyncClient):
        resp = await client.get("/v1/system/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_audit_integrity_endpoint(self, client: AsyncClient):
        resp = await client.get("/v1/system/audit-integrity")
        assert resp.status_code == 200
        data = resp.json()
        assert "verified" in data
        assert "tampered_rows" in data


class TestTransparencyAPI:
    @pytest.mark.asyncio
    async def test_transparency_returns_report(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-trans-1", name="Trans Agent")
        task = Task(id="task-trans-1", title="Trans Task", type="task", status="doing", agent_id="agent-trans-1", created_by="user-1")
        cp = CheckPoint(task_id="task-trans-1", turn_number=1, messages=[{"role": "user"}])
        ledger = CostLedger(agent_id="agent-trans-1", task_id="task-trans-1", model_id="gpt-4o", input_tokens=10, output_tokens=5, cost_usd=0.05)
        db_session.add_all([agent, task, cp, ledger])
        await db_session.commit()

        resp = await client.get("/v1/tasks/task-trans-1/transparency")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-trans-1"
        assert "turns" in data
        assert len(data["turns"]) >= 1
        assert data["turns"][0]["model_id"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_transparency_not_found(self, client: AsyncClient):
        resp = await client.get("/v1/tasks/nonexistent/transparency")
        assert resp.status_code == 404
