"""Tests for session reply file attachments."""

from datetime import UTC, datetime, timedelta

import pytest
import respx
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.auth import require_internal_auth
from isli_core.main import app
from isli_core.models import Agent, Session


def _mock_auth(agent_id: str = "agent-1"):
    async def _auth():
        return {"sub": agent_id}
    return _auth


@pytest.mark.asyncio
@respx.mock
async def test_reply_with_attachment_returns_signed_url(
    client: AsyncClient, db_session: AsyncSession
):
    """Web reply returns a signed download URL and persists metadata only."""
    agent = Agent(id="agent-1", name="Test Agent", channels=["web"])
    db_session.add(agent)
    session_id = "sess-att-web"
    sess = Session(
        id=session_id,
        agent_id="agent-1",
        channel="web",
        user_id=None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(sess)
    await db_session.commit()

    app.dependency_overrides[require_internal_auth] = _mock_auth("agent-1")

    # Mock workspace metadata endpoint
    meta_route = respx.post("http://localhost:8300/metadata").mock(
        return_value=Response(
            200,
            json={
                "status": "ok",
                "path": "report.pdf",
                "filename": "report.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 12345,
                "modified_at": datetime.now(UTC).isoformat(),
            },
        )
    )

    # Ensure channels service is not called for web
    channels_route = respx.post("http://localhost:8002/send").mock(return_value=Response(200))

    try:
        resp = await client.post(
            f"/v1/sessions/{session_id}/reply",
            json={
                "text": "Here is your report.",
                "attachments": [{"path": "report.pdf", "caption": "Monthly report"}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "sent"
        msg = data["message"]
        assert len(msg["attachments"]) == 1
        att = msg["attachments"][0]
        assert att["filename"] == "report.pdf"
        assert att["mime_type"] == "application/pdf"
        assert att["size_bytes"] == 12345
        assert att["caption"] == "Monthly report"
        assert "/v1/internal/files/download?token=" in att["download_url"]
        assert "expires_at" in att
        # Metadata persisted; no signed URL stored
        assert msg["attachments"][0].get("path") == "report.pdf"
        assert not channels_route.called
        assert meta_route.called
    finally:
        del app.dependency_overrides[require_internal_auth]


@pytest.mark.asyncio
@respx.mock
async def test_reply_with_attachment_forwards_to_channels(
    client: AsyncClient, db_session: AsyncSession
):
    """Telegram reply forwards attachments with fresh signed URLs to channels."""
    agent = Agent(id="agent-2", name="Test Agent", channels=["telegram"])
    db_session.add(agent)
    session_id = "sess-att-tg"
    sess = Session(
        id=session_id,
        agent_id="agent-2",
        channel="telegram",
        user_id="user-tg-1",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(sess)
    await db_session.commit()

    app.dependency_overrides[require_internal_auth] = _mock_auth("agent-2")

    respx.post("http://localhost:8300/metadata").mock(
        return_value=Response(
            200,
            json={
                "status": "ok",
                "path": "chart.png",
                "filename": "chart.png",
                "mime_type": "image/png",
                "size_bytes": 4096,
                "modified_at": datetime.now(UTC).isoformat(),
            },
        )
    )

    channels_route = respx.post("http://localhost:8002/send").mock(return_value=Response(200))

    try:
        resp = await client.post(
            f"/v1/sessions/{session_id}/reply",
            json={
                "text": "See attached chart.",
                "attachments": [{"path": "chart.png"}],
            },
        )
        assert resp.status_code == 200
        assert channels_route.called
        last_request = channels_route.calls.last.request
        import json
        payload = json.loads(last_request.content)
        assert payload["channel"] == "telegram"
        assert payload["channel_user_id"] == "user-tg-1"
        assert len(payload["attachments"]) == 1
        att = payload["attachments"][0]
        assert att["filename"] == "chart.png"
        assert att["media_type"] == "image"
        assert "/v1/internal/files/download?token=" in att["download_url"]
    finally:
        del app.dependency_overrides[require_internal_auth]


@pytest.mark.asyncio
@respx.mock
async def test_reply_attachment_max_five(
    client: AsyncClient, db_session: AsyncSession
):
    """Only the first 5 attachments are kept."""
    agent = Agent(id="agent-3", name="Test Agent", channels=["web"])
    db_session.add(agent)
    session_id = "sess-att-max"
    sess = Session(
        id=session_id,
        agent_id="agent-3",
        channel="web",
        user_id=None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(sess)
    await db_session.commit()

    app.dependency_overrides[require_internal_auth] = _mock_auth("agent-3")

    def _meta_response(request):
        body = request.content and json.loads(request.content)
        return Response(
            200,
            json={
                "status": "ok",
                "path": body.get("path", "file.bin"),
                "filename": body.get("path", "file.bin"),
                "mime_type": "application/octet-stream",
                "size_bytes": 100,
                "modified_at": datetime.now(UTC).isoformat(),
            },
        )

    import json
    respx.post("http://localhost:8300/metadata").mock(side_effect=_meta_response)

    try:
        resp = await client.post(
            f"/v1/sessions/{session_id}/reply",
            json={
                "text": "Many files.",
                "attachments": [{"path": f"file{i}.bin"} for i in range(7)],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["message"]["attachments"]) == 5
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@respx.mock
async def test_reply_attachment_invalid_path(
    client: AsyncClient, db_session: AsyncSession
):
    """An attachment path outside the workspace is rejected."""
    agent = Agent(id="agent-4", name="Test Agent", channels=["web"])
    db_session.add(agent)
    session_id = "sess-att-bad"
    sess = Session(
        id=session_id,
        agent_id="agent-4",
        channel="web",
        user_id=None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(sess)
    await db_session.commit()

    app.dependency_overrides[require_internal_auth] = _mock_auth("agent-4")

    try:
        resp = await client.post(
            f"/v1/sessions/{session_id}/reply",
            json={"text": "Bad file.", "attachments": [{"path": "../etc/passwd"}]},
        )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()
