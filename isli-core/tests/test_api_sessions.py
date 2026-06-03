"""Tests for session lifecycle and checkpoint recovery."""

import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Agent, Task, Session, CheckPoint
from isli_core.session_lifecycle import SessionLifecycleManager
from isli_core.jobs.checkpoint_recovery import CheckpointRecoveryWorker


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_expire_sessions(self, db_session: AsyncSession):
        agent = Agent(id="agent-sess-1", name="Session Agent")
        session = Session(
            id="sess-expired",
            agent_id="agent-sess-1",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            messages=[{"role": "user", "content": "hi"}],
        )
        db_session.add_all([agent, session])
        await db_session.commit()

        count = await SessionLifecycleManager.expire_sessions(db_session)
        assert count == 1
        await db_session.commit()

        # Verify soft delete
        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(Session).where(Session.id == "sess-expired")
        )
        sess = result.scalar_one()
        assert sess.deleted_at is not None
        assert sess.messages == []

    @pytest.mark.asyncio
    async def test_compact_sessions(self, db_session: AsyncSession):
        agent = Agent(id="agent-sess-2", name="Session Agent")
        long_messages = [{"role": "user", "content": f"msg-{i}"} for i in range(30)]
        session = Session(
            id="sess-compact",
            agent_id="agent-sess-2",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            token_count=5000,
            messages=long_messages,
        )
        db_session.add_all([agent, session])
        await db_session.commit()

        count = await SessionLifecycleManager.compact_sessions(db_session, token_threshold=4096, turn_threshold=20)
        assert count == 1
        await db_session.commit()

        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(Session).where(Session.id == "sess-compact")
        )
        sess = result.scalar_one()
        assert len(sess.messages) == 20
        assert sess.compacted_at is not None

    @pytest.mark.asyncio
    async def test_detect_idle_sessions(self, db_session: AsyncSession):
        agent = Agent(id="agent-sess-3", name="Session Agent")
        session = Session(
            id="sess-idle",
            agent_id="agent-sess-3",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            last_activity_at=datetime.now(timezone.utc) - timedelta(hours=1),
            messages=[{"role": "user", "content": "hi"}],
        )
        db_session.add_all([agent, session])
        await db_session.commit()

        count = await SessionLifecycleManager.detect_idle(db_session, idle_timeout_minutes=30)
        assert count == 1
        await db_session.commit()

        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(Session).where(Session.id == "sess-idle")
        )
        sess = result.scalar_one()
        assert sess.deleted_at is not None
        assert sess.messages == []

    @pytest.mark.asyncio
    async def test_heartbeat_updates_last_activity(self, client: AsyncClient, db_session: AsyncSession):
        db_session.add(Agent(id="agent-hb-1", name="HB Agent"))
        db_session.add(Session(
            id="sess-hb-1",
            agent_id="agent-hb-1",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        await db_session.commit()

        resp = await client.post("/v1/agents/agent-hb-1/heartbeat")
        assert resp.status_code == 200

        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(Session).where(Session.id == "sess-hb-1")
        )
        sess = result.scalar_one()
        assert sess.last_activity_at is not None


class TestCheckpointRecovery:
    @pytest.mark.asyncio
    async def test_recovery_resets_stalled_task(self, db_session: AsyncSession):
        agent = Agent(
            id="agent-rec-1",
            name="Recovery Agent",
            heartbeat_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        task = Task(
            id="task-rec-1",
            title="Stalled Task",
            type="task",
            status="doing",
            agent_id="agent-rec-1",
            created_by="user-1",
        )
        cp = CheckPoint(task_id="task-rec-1", turn_number=5, messages=[{"role": "user"}])
        db_session.add_all([agent, task, cp])
        await db_session.commit()

        recovered = await CheckpointRecoveryWorker.run_once(db_session, stale_minutes=10)
        await db_session.commit()

        assert len(recovered) == 1
        assert recovered[0]["task_id"] == "task-rec-1"
        assert recovered[0]["turn_number"] == 5

        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(Task).where(Task.id == "task-rec-1")
        )
        task = result.scalar_one()
        assert task.status == "inbox"
        assert "checkpoint turn 5" in task.blocked_reason
        assert task.retry_count == 1

        cp_result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(CheckPoint).where(CheckPoint.task_id == "task-rec-1")
        )
        cp = cp_result.scalar_one()
        assert cp.recovered_at is not None
        assert cp.recovery_turn_number == 5

    @pytest.mark.asyncio
    async def test_recovery_skips_fresh_tasks(self, db_session: AsyncSession):
        agent = Agent(
            id="agent-rec-2",
            name="Fresh Agent",
            heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        )
        task = Task(
            id="task-rec-2",
            title="Fresh Task",
            type="task",
            status="doing",
            agent_id="agent-rec-2",
            created_by="user-1",
        )
        db_session.add_all([agent, task])
        await db_session.commit()

        recovered = await CheckpointRecoveryWorker.run_once(db_session, stale_minutes=10)
        await db_session.commit()

        assert len(recovered) == 0

        result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(Task).where(Task.id == "task-rec-2")
        )
        task = result.scalar_one()
        assert task.status == "doing"


class TestSessionAPIFilters:
    @pytest.mark.asyncio
    async def test_list_sessions_filter_by_channel(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-filter-1", name="Filter Agent")
        session_web = Session(
            id="sess-web-1",
            agent_id="agent-filter-1",
            user_id="user-1",
            channel="web",
            messages=[{"role": "user", "content": "hi web", "timestamp": datetime.now(timezone.utc).isoformat()}],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session_telegram = Session(
            id="sess-tg-1",
            agent_id="agent-filter-1",
            user_id="user-2",
            channel="telegram",
            messages=[{"role": "user", "content": "hi tg", "timestamp": datetime.now(timezone.utc).isoformat()}],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add_all([agent, session_web, session_telegram])
        await db_session.commit()

        resp = await client.get("/v1/sessions?channel=telegram")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "sess-tg-1"

    @pytest.mark.asyncio
    async def test_list_sessions_include_closed(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-filter-2", name="Filter Agent 2")
        session_open = Session(
            id="sess-open-1",
            agent_id="agent-filter-2",
            channel="telegram",
            messages=[],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session_closed = Session(
            id="sess-closed-1",
            agent_id="agent-filter-2",
            channel="telegram",
            messages=[],
            status="closed",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add_all([agent, session_open, session_closed])
        await db_session.commit()

        resp = await client.get("/v1/sessions?agent_id=agent-filter-2&channel=telegram")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "sess-open-1"

        resp = await client.get("/v1/sessions?agent_id=agent-filter-2&channel=telegram&include_closed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_get_session_history_combines_archived_and_live(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-history-1", name="History Agent")
        session = Session(
            id="sess-history-1",
            agent_id="agent-history-1",
            channel="telegram",
            user_id="user-1",
            archived_messages=[
                {"role": "user", "content": "old msg", "timestamp": "2024-01-01T10:00:00+00:00"}
            ],
            messages=[
                {"role": "assistant", "content": "new msg", "timestamp": "2024-01-01T11:00:00+00:00"}
            ],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add_all([agent, session])
        await db_session.commit()

        resp = await client.get("/v1/sessions/sess-history-1/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-history-1"
        assert len(data["all_messages"]) == 2
        assert data["all_messages"][0]["content"] == "old msg"
        assert data["all_messages"][1]["content"] == "new msg"

    @pytest.mark.asyncio
    async def test_get_session_history_404_deleted(self, client: AsyncClient, db_session: AsyncSession):
        agent = Agent(id="agent-history-2", name="History Agent 2")
        session = Session(
            id="sess-history-2",
            agent_id="agent-history-2",
            channel="telegram",
            messages=[],
            deleted_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add_all([agent, session])
        await db_session.commit()

        resp = await client.get("/v1/sessions/sess-history-2/history")
        assert resp.status_code == 404
