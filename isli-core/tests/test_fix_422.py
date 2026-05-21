import pytest
import respx
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession
from isli_core.models import Agent, Session
from isli_core.main import app
from datetime import datetime, timezone, timedelta
from isli_core.auth import require_internal_auth

# Mock auth dependency
async def mock_require_internal_auth():
    return {"sub": "agent-1"}

@pytest.mark.asyncio
@respx.mock
async def test_reply_to_session_skips_web(client: AsyncClient, db_session: AsyncSession):
    # Setup: Create agent and a 'web' session
    agent = Agent(id="agent-1", name="Test Agent", channels=["web"])
    db_session.add(agent)
    
    session_id = "sess-web-1"
    sess = Session(
        id=session_id,
        agent_id="agent-1",
        channel="web",
        user_id=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(sess)
    await db_session.commit()

    # Apply dependency override
    app.dependency_overrides[require_internal_auth] = mock_require_internal_auth
    
    # Mock external channel service - should NOT be called
    route = respx.post("http://localhost:8002/send").mock(return_value=Response(200))
    
    try:
        resp = await client.post(
            f"/v1/sessions/{session_id}/reply",
            json={"text": "hello from agent"},
        )
        assert resp.status_code == 200
        assert not route.called
    finally:
        del app.dependency_overrides[require_internal_auth]

@pytest.mark.asyncio
@respx.mock
async def test_reply_to_session_calls_external(client: AsyncClient, db_session: AsyncSession):
    # Setup: Create agent and a 'telegram' session
    agent = Agent(id="agent-2", name="Test Agent 2", channels=["telegram"])
    db_session.add(agent)
    
    session_id = "sess-tg-1"
    sess = Session(
        id=session_id,
        agent_id="agent-2",
        channel="telegram",
        user_id="user-tg-1",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(sess)
    await db_session.commit()

    # Mock auth dependency for agent-2
    async def mock_require_internal_auth_2():
        return {"sub": "agent-2"}
    app.dependency_overrides[require_internal_auth] = mock_require_internal_auth_2

    # Mock external channel service - SHOULD be called
    route = respx.post("http://localhost:8002/send").mock(return_value=Response(200))

    try:
        resp = await client.post(
            f"/v1/sessions/{session_id}/reply",
            json={"text": "hello from agent"},
        )
        assert resp.status_code == 200
        assert route.called
        # Verify it was called with the correct JSON
        last_request = route.calls.last.request
        import json
        payload = json.loads(last_request.content)
        assert payload["channel"] == "telegram"
        assert payload["channel_user_id"] == "user-tg-1"
    finally:
        del app.dependency_overrides[require_internal_auth]
