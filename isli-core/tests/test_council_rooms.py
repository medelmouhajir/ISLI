"""Tests for the Council room feature."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Agent, Session
from isli_core.rooms.mentions import parse_mentions
from isli_core.rooms.service import (
    MAX_AGENTS_PER_ROOM,
    RoomService,
    _room_session_id,
    mirror_room_reply,
)
from isli_core.session_lifecycle import SessionLifecycleManager


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


class TestMentionParser:
    def test_parse_agent_id_mention(self):
        agents = [
            Agent(id="alpha", name="Alpha One"),
            Agent(id="beta", name="Beta Two"),
        ]
        assert parse_mentions("@alpha what do you think?", agents) == ["alpha"]

    def test_parse_name_mention(self):
        agents = [
            Agent(id="alpha", name="Alpha One"),
        ]
        assert parse_mentions("hey @Alpha, help me", agents) == ["alpha"]

    def test_parse_all_expands_roster(self):
        agents = [
            Agent(id="alpha", name="Alpha"),
            Agent(id="beta", name="Beta"),
        ]
        assert parse_mentions("@all sync up", agents, ["beta", "alpha"]) == ["beta", "alpha"]

    def test_parse_everyone_same_as_all(self):
        agents = [Agent(id="alpha", name="Alpha")]
        assert parse_mentions("@everyone", agents, ["alpha"]) == ["alpha"]

    def test_unknown_mentions_ignored(self):
        agents = [Agent(id="alpha", name="Alpha")]
        assert parse_mentions("@unknown text", agents) == []

    def test_case_insensitive(self):
        agents = [Agent(id="AlphaBot", name="Alpha Bot")]
        assert parse_mentions("@alphabot", agents) == ["AlphaBot"]
        assert parse_mentions("@alpha", agents) == ["AlphaBot"]


class TestRoomService:
    @pytest.mark.asyncio
    async def test_create_room_and_sessions(self, db_session: AsyncSession):
        a1, a2 = _uid("svc-a"), _uid("svc-b")
        db_session.add_all([Agent(id=a1, name="A"), Agent(id=a2, name="B")])
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="War Room", agent_ids=[a1, a2])

        assert room.name == "War Room"
        assert set(room.agent_ids) == {a1, a2}
        assert len(room.messages) == 1
        assert room.messages[0]["role"] == "system"

        for agent_id in (a1, a2):
            sess_id = _room_session_id(room.id, agent_id)
            sess = await db_session.get(Session, sess_id)
            assert sess is not None
            assert sess.room_id == room.id
            assert sess.messages == room.messages

    @pytest.mark.asyncio
    async def test_post_message_with_mention(self, db_session: AsyncSession):
        a1, a2 = _uid("svc-a"), _uid("svc-b")
        db_session.add_all([Agent(id=a1, name="A"), Agent(id=a2, name="B")])
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="Room", agent_ids=[a1, a2])

        room, addressed = await svc.post_message(
            room.id, "user-1", f"@{a2} please review this"
        )
        assert addressed == [a2]
        assert len(room.messages) == 2
        assert room.messages[1]["role"] == "user"
        assert room.messages[1]["mentions"] == [a2]

    @pytest.mark.asyncio
    async def test_post_message_fallback_to_all(self, db_session: AsyncSession):
        a1, a2 = _uid("svc-a"), _uid("svc-b")
        db_session.add_all([Agent(id=a1, name="A"), Agent(id=a2, name="B")])
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="Room", agent_ids=[a1, a2])

        room, addressed = await svc.post_message(room.id, "user-1", "hello")
        assert set(addressed) == {a1, a2}

    @pytest.mark.asyncio
    async def test_mentions_override_last_addressed(self, db_session: AsyncSession):
        """Typing @agent2 in a room with sticky [agent1, agent2] should address only agent2."""
        a1, a2 = _uid("svc-a"), _uid("svc-b")
        db_session.add_all([Agent(id=a1, name="A"), Agent(id=a2, name="B")])
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="Room", agent_ids=[a1, a2])
        # Establish sticky last_addressed set of both agents
        await svc.post_message(room.id, "user-1", "first", addressed_agent_ids=[a1, a2])

        # Now send a follow-up that only mentions a2
        room, addressed = await svc.post_message(room.id, "user-1", f"@{a2} follow up")
        assert addressed == [a2]

    @pytest.mark.asyncio
    async def test_explicit_selection_plus_mentions(self, db_session: AsyncSession):
        """UI selection plus @mentions should union, without pulling in sticky set."""
        a1, a2 = _uid("svc-a"), _uid("svc-b")
        db_session.add_all([Agent(id=a1, name="A"), Agent(id=a2, name="B")])
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="Room", agent_ids=[a1, a2])
        await svc.post_message(room.id, "user-1", "first", addressed_agent_ids=[a1, a2])

        # UI already selected a1; text mentions a2
        room, addressed = await svc.post_message(
            room.id, "user-1", f"@{a2} check this", addressed_agent_ids=[a1]
        )
        assert set(addressed) == {a1, a2}

    @pytest.mark.asyncio
    async def test_no_mentions_uses_last_addressed(self, db_session: AsyncSession):
        """Empty UI selection + no mentions should fall back to sticky set."""
        a1, a2 = _uid("svc-a"), _uid("svc-b")
        db_session.add_all([Agent(id=a1, name="A"), Agent(id=a2, name="B")])
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="Room", agent_ids=[a1, a2])
        await svc.post_message(room.id, "user-1", "first", addressed_agent_ids=[a1])

        room, addressed = await svc.post_message(
            room.id, "user-1", "hello", addressed_agent_ids=[]
        )
        assert addressed == [a1]

    @pytest.mark.asyncio
    async def test_all_mention_expands_to_roster(self, db_session: AsyncSession):
        a1, a2 = _uid("svc-a"), _uid("svc-b")
        db_session.add_all([Agent(id=a1, name="A"), Agent(id=a2, name="B")])
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="Room", agent_ids=[a1, a2])
        await svc.post_message(room.id, "user-1", "first", addressed_agent_ids=[a1])

        room, addressed = await svc.post_message(room.id, "user-1", "@all sync up")
        assert set(addressed) == {a1, a2}

    @pytest.mark.asyncio
    async def test_unknown_mention_ignored(self, db_session: AsyncSession):
        """@unknown should not affect addressing and should fall back to sticky."""
        a1 = _uid("svc-a")
        db_session.add(Agent(id=a1, name="A"))
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="Room", agent_ids=[a1])
        await svc.post_message(room.id, "user-1", "first", addressed_agent_ids=[a1])

        room, addressed = await svc.post_message(
            room.id, "user-1", "@unknown hello", addressed_agent_ids=[]
        )
        assert addressed == [a1]

    @pytest.mark.asyncio
    async def test_add_agent_enforces_cap(self, db_session: AsyncSession):
        agents = [Agent(id=_uid(f"cap-{i}"), name=f"Agent {i}") for i in range(MAX_AGENTS_PER_ROOM)]
        db_session.add_all(agents)
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(
            user_id="user-1", name="Room", agent_ids=[a.id for a in agents]
        )

        extra = Agent(id=_uid("extra"), name="Extra")
        db_session.add(extra)
        await db_session.commit()

        with pytest.raises(ValueError, match="Maximum"):
            await svc.add_agent(room.id, "user-1", extra.id)

    @pytest.mark.asyncio
    async def test_pin_and_export(self, db_session: AsyncSession):
        a1 = _uid("pin-a")
        db_session.add(Agent(id=a1, name="A"))
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="Room", agent_ids=[a1])
        room, _ = await svc.post_message(room.id, "user-1", "insight one")
        msg_id = room.messages[-1]["id"]

        room = await svc.pin_message(room.id, "user-1", msg_id)
        assert len(room.pins) == 1
        assert room.pins[0]["message_id"] == msg_id

        markdown = await svc.export_pins(room.id, "user-1")
        assert "Pinned Insights" in markdown
        assert "insight one" in markdown

    @pytest.mark.asyncio
    async def test_close_room_closes_sessions(self, db_session: AsyncSession):
        a1 = _uid("close-a")
        db_session.add(Agent(id=a1, name="A"))
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="Room", agent_ids=[a1])
        room = await svc.close_room(room.id, "user-1")
        assert room.status == "closed"

        sess_id = _room_session_id(room.id, a1)
        sess = await db_session.get(Session, sess_id)
        assert sess.status == "closed"


class TestMirrorRoomReply:
    @pytest.mark.asyncio
    async def test_mirror_reply_to_room_and_sessions(self, db_session: AsyncSession):
        a1 = _uid("mirror-a")
        db_session.add(Agent(id=a1, name="A"))
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="Room", agent_ids=[a1])
        room, _ = await svc.post_message(room.id, "user-1", "question")
        parent_id = room.messages[-1]["id"]

        updated = await mirror_room_reply(
            room.id,
            a1,
            {"content": "answer", "parent_id": parent_id},
        )
        assert updated is not None
        assert len(updated.messages) == 3
        assistant_msg = updated.messages[-1]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["agent_id"] == a1
        assert assistant_msg["parent_id"] == parent_id

        sess_id = _room_session_id(room.id, a1)
        sess = await db_session.get(Session, sess_id)
        assert sess.messages[-1]["content"] == "answer"


class TestRoomSessionLifecycle:
    @pytest.mark.asyncio
    async def test_detect_idle_skips_room_sessions(self, db_session: AsyncSession):
        a1 = _uid("idle-a")
        db_session.add(Agent(id=a1, name="A"))
        await db_session.commit()

        svc = RoomService(db_session)
        room = await svc.create_room(user_id="user-1", name="Room", agent_ids=[a1])

        sess_id = _room_session_id(room.id, a1)
        sess = await db_session.get(Session, sess_id)
        sess.last_activity_at = datetime.now(UTC) - timedelta(hours=1)

        normal = Session(
            id=_uid("normal"),
            agent_id=a1,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            last_activity_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db_session.add(normal)
        await db_session.commit()

        count = await SessionLifecycleManager.detect_idle(db_session, idle_timeout_minutes=30)
        assert count == 1

        room_sess = await db_session.get(Session, sess_id)
        assert room_sess.deleted_at is None

        normal = await db_session.get(Session, normal.id)
        assert normal.deleted_at is not None


class TestRoomApi:
    @pytest.mark.asyncio
    async def test_create_room_via_api(self, client: AsyncClient, db_session: AsyncSession):
        a1, a2 = _uid("api-a"), _uid("api-b")
        db_session.add_all([Agent(id=a1, name="A"), Agent(id=a2, name="B")])
        await db_session.commit()

        resp = await client.post(
            "/v1/rooms",
            json={"name": "API Room", "agent_ids": [a1, a2], "user_id": "user-api"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "API Room"
        assert set(body["agent_ids"]) == {a1, a2}

        for agent_id in (a1, a2):
            sess_id = _room_session_id(body["id"], agent_id)
            assert await db_session.get(Session, sess_id) is not None

    @pytest.mark.asyncio
    async def test_post_message_via_api(self, client: AsyncClient, db_session: AsyncSession):
        a1, a2 = _uid("api-a"), _uid("api-b")
        db_session.add_all([Agent(id=a1, name="A"), Agent(id=a2, name="B")])
        await db_session.commit()

        create_resp = await client.post(
            "/v1/rooms",
            json={"name": "API Room 2", "agent_ids": [a1, a2], "user_id": "user-api"},
        )
        room_id = create_resp.json()["id"]

        resp = await client.post(
            f"/v1/rooms/{room_id}/message",
            json={
                "text": f"@{a1} thoughts?",
                "user_id": "user-api",
                "addressed_agent_ids": [a1],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["messages"]) == 2
        assert body["messages"][-1]["mentions"] == [a1]
        assert body["room_metadata"]["last_addressed_agent_ids"] == [a1]

    @pytest.mark.asyncio
    async def test_export_pins_via_api(self, client: AsyncClient, db_session: AsyncSession):
        a1 = _uid("api-a")
        db_session.add(Agent(id=a1, name="A"))
        await db_session.commit()

        create_resp = await client.post(
            "/v1/rooms",
            json={"name": "Pin Room", "agent_ids": [a1], "user_id": "user-api"},
        )
        room_id = create_resp.json()["id"]

        msg_resp = await client.post(
            f"/v1/rooms/{room_id}/message",
            json={"text": "pin this", "user_id": "user-api"},
        )
        msg_id = msg_resp.json()["messages"][-1]["id"]

        pin_resp = await client.post(
            f"/v1/rooms/{room_id}/pin",
            json={"message_id": msg_id, "user_id": "user-api"},
        )
        assert pin_resp.status_code == 200

        export_resp = await client.post(
            f"/v1/rooms/{room_id}/export-pins",
            params={"user_id": "user-api"},
        )
        assert export_resp.status_code == 200
        assert "pin this" in export_resp.json()["markdown"]

    @pytest.mark.asyncio
    async def test_close_room_via_api(self, client: AsyncClient, db_session: AsyncSession):
        a1 = _uid("api-a")
        db_session.add(Agent(id=a1, name="A"))
        await db_session.commit()

        create_resp = await client.post(
            "/v1/rooms",
            json={"name": "Close Room", "agent_ids": [a1], "user_id": "user-api"},
        )
        room_id = create_resp.json()["id"]

        resp = await client.post(
            f"/v1/rooms/{room_id}/close",
            params={"user_id": "user-api"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"
