"""Council room business logic.

A Council room is a single thread shared by the user and N agents. Each agent has
its own ``Session`` row linked to the room via ``Session.room_id``. The canonical
room message list is mirrored into every room session so existing context-injection,
journal, and memory workers continue to operate unchanged.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.cost.complexity import TaskComplexityScorer
from isli_core.db import get_db_session_manual
from isli_core.event_manager import EventManager
from isli_core.models import Agent, Room, Session
from isli_core.redis_streams import add_to_stream
from isli_core.rooms.mentions import parse_mentions

logger = structlog.get_logger()

ROOM_EXPIRY_DAYS = 30
MAX_AGENTS_PER_ROOM = 20


def _room_session_id(room_id: str, agent_id: str) -> str:
    """Deterministic session id for an agent inside a room."""
    return f"room:{room_id}:{agent_id}"


def _room_message(
    role: str,
    content: str,
    agent_id: str | None = None,
    agent_name: str | None = None,
    parent_id: str | None = None,
    mentions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "role": role,
        "content": content,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "timestamp": datetime.now(UTC).isoformat(),
        "parent_id": parent_id,
        "mentions": mentions or [],
    }


class RoomService:
    """Persistent operations for Council rooms."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_room(
        self,
        room_id: str,
        user_id: str | None = None,
        active_only: bool = True,
    ) -> Room | None:
        query = select(Room).where(
            Room.id == room_id, Room.deleted_at.is_(None)
        )
        if active_only:
            query = query.where(Room.status == "active")
        if user_id:
            query = query.where(Room.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_rooms(self, user_id: str, limit: int = 100) -> Sequence[Room]:
        result = await self.db.execute(
            select(Room)
            .where(Room.user_id == user_id, Room.deleted_at.is_(None))
            .order_by(Room.last_activity_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def create_room(
        self,
        user_id: str,
        name: str,
        agent_ids: list[str],
        channel: str = "web",
    ) -> Room:
        """Create a room and per-agent sessions for the initial roster."""
        if len(agent_ids) > MAX_AGENTS_PER_ROOM:
            raise ValueError(f"Maximum {MAX_AGENTS_PER_ROOM} agents per room")

        agents = await self._load_agents(agent_ids)
        if len(agents) != len(agent_ids):
            missing = set(agent_ids) - {a.id for a in agents}
            raise ValueError(f"Agents not found: {missing}")

        now = datetime.now(UTC)
        room = Room(
            id=str(uuid4()),
            name=name,
            user_id=user_id,
            channel=channel,
            status="active",
            messages=[],
            agent_ids=list(agent_ids),
            pins=[],
            room_metadata={},
            expires_at=now + timedelta(days=ROOM_EXPIRY_DAYS),
            last_activity_at=now,
            created_at=now,
        )
        self.db.add(room)
        await self.db.flush()  # populate room.id

        for agent in agents:
            await self._ensure_room_session(room, agent, now)

        system_msg = _room_message(
            role="system",
            content=f"Room created. Initial roster: {', '.join(a.name for a in agents)}.",
        )
        room.messages = [system_msg]
        room.last_activity_at = now
        await self._mirror_messages_to_sessions(room)
        await self.db.commit()
        await self.db.refresh(room)
        return room

    async def add_agent(self, room_id: str, user_id: str, agent_id: str) -> Room:
        """Add an agent to an existing room and create its session."""
        room = await self.get_room(room_id, user_id)
        if not room:
            raise ValueError("Room not found")
        if agent_id in (room.agent_ids or []):
            return room
        if len(room.agent_ids or []) >= MAX_AGENTS_PER_ROOM:
            raise ValueError(f"Maximum {MAX_AGENTS_PER_ROOM} agents per room")

        agent = await self.db.get(Agent, agent_id)
        if not agent or agent.deleted_at:
            raise ValueError(f"Agent not found: {agent_id}")

        now = datetime.now(UTC)
        await self._ensure_room_session(room, agent, now)

        room.agent_ids = (room.agent_ids or []) + [agent_id]
        room.messages = (room.messages or []) + [
            _room_message(
                role="system",
                content=f"{agent.name} joined the room.",
                agent_id=agent.id,
                agent_name=agent.name,
            )
        ]
        room.last_activity_at = now
        await self._mirror_messages_to_sessions(room)
        await self.db.commit()
        await self.db.refresh(room)

        await EventManager.emit(
            "room:agent_joined",
            {
                "room_id": room.id,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "picture": agent.picture,
            },
        )
        await EventManager.emit("room:updated", {"room_id": room.id})
        return room

    async def post_message(
        self,
        room_id: str,
        user_id: str,
        text: str,
        addressed_agent_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Room, list[str]]:
        """Append a user message, expand mentions, and dispatch to addressed agents.

        Returns the updated room and the list of agent ids that will respond.
        """
        room = await self.get_room(room_id, user_id)
        if not room:
            raise ValueError("Room not found")

        # Load all available agents for mention resolution
        all_agents_result = await self.db.execute(
            select(Agent).where(Agent.deleted_at.is_(None))
        )
        all_agents = all_agents_result.scalars().all()

        # Mentions in the message text are authoritative when present.
        # They override the sticky "last addressed" set, but explicit UI
        # selections are still honored as an additive override.
        last_addressed = (room.room_metadata or {}).get("last_addressed_agent_ids", [])
        mentioned = parse_mentions(text, all_agents, room.agent_ids or [])

        if mentioned:
            resolved = set(addressed_agent_ids or [])
            resolved.update(mentioned)
        else:
            # No mentions: use explicit selection, then sticky, then whole room.
            resolved = set(addressed_agent_ids or last_addressed or [])

        # Ensure all addressed agents are in the room
        for agent_id in list(resolved):
            if agent_id not in (room.agent_ids or []):
                try:
                    await self.add_agent(room_id, user_id, agent_id)
                except ValueError as exc:
                    logger.warning(
                        "room.add_agent_failed",
                        room_id=room_id,
                        agent_id=agent_id,
                        error=str(exc),
                    )
                    resolved.discard(agent_id)

        if not resolved:
            # Fallback: address every agent in the room if nobody is targeted
            resolved = set(room.agent_ids or [])

        addressed = list(resolved)
        now = datetime.now(UTC)
        parent_id = str(uuid4())
        user_msg = _room_message(
            role="user",
            content=text,
            parent_id=parent_id,
            mentions=mentioned,
        )
        room.messages = (room.messages or []) + [user_msg]
        room.last_activity_at = now

        # Update sticky addressing state
        room.room_metadata = dict(room.room_metadata or {})
        room.room_metadata["last_addressed_agent_ids"] = addressed
        if metadata:
            room.room_metadata.update(metadata)

        await self._mirror_messages_to_sessions(room)
        await self.db.commit()
        await self.db.refresh(room)

        # Dispatch context:requests for each addressed agent
        score, tier = TaskComplexityScorer.score_task_input(text)
        for agent_id in addressed:
            session_id = _room_session_id(room.id, agent_id)
            agent = await self.db.get(Agent, agent_id)
            agent_config = agent.config or {} if agent else {}
            await add_to_stream(
                "context:requests",
                {
                    "type": "session",
                    "id": session_id,
                    "agent_id": agent_id,
                    "task_description": f"Council room {room.name}: {text}",
                    "session_id": session_id,
                    "complexity_score": score,
                    "complexity_tier": tier,
                    "memory_similarity_threshold": agent_config.get(
                        "memory_similarity_threshold", 0.4
                    ),
                    "room_id": room.id,
                },
            )

        await EventManager.emit("room:updated", {"room_id": room.id, "parent_id": parent_id})
        return room, addressed

    async def close_room(self, room_id: str, user_id: str) -> Room:
        room = await self.get_room(room_id, user_id, active_only=False)
        if not room:
            raise ValueError("Room not found")

        if room.status == "closed":
            return room

        room.status = "closed"
        room.last_activity_at = datetime.now(UTC)

        # Close all linked sessions
        result = await self.db.execute(
            select(Session).where(Session.room_id == room_id, Session.deleted_at.is_(None))
        )
        for sess in result.scalars().all():
            sess.status = "closed"
            sess.last_activity_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(room)
        await EventManager.emit("room:updated", {"room_id": room.id, "status": "closed"})
        return room

    async def pin_message(self, room_id: str, user_id: str, message_id: str) -> Room:
        room = await self.get_room(room_id, user_id)
        if not room:
            raise ValueError("Room not found")
        msg = next((m for m in (room.messages or []) if m.get("id") == message_id), None)
        if not msg:
            raise ValueError("Message not found")

        pins = room.pins or []
        if not any(p.get("message_id") == message_id for p in pins):
            preview = msg.get("content", "")[:200]
            pins.append(
                {
                    "message_id": message_id,
                    "agent_id": msg.get("agent_id"),
                    "agent_name": msg.get("agent_name"),
                    "preview": preview,
                    "pinned_at": datetime.now(UTC).isoformat(),
                }
            )
            room.pins = pins
            await self.db.commit()
            await self.db.refresh(room)
            await EventManager.emit("room:updated", {"room_id": room.id})
        return room

    async def unpin_message(self, room_id: str, user_id: str, message_id: str) -> Room:
        room = await self.get_room(room_id, user_id)
        if not room:
            raise ValueError("Room not found")
        pins = [p for p in (room.pins or []) if p.get("message_id") != message_id]
        if len(pins) != len(room.pins or []):
            room.pins = pins
            await self.db.commit()
            await self.db.refresh(room)
            await EventManager.emit("room:updated", {"room_id": room.id})
        return room

    async def export_pins(self, room_id: str, user_id: str) -> str:
        room = await self.get_room(room_id, user_id)
        if not room:
            raise ValueError("Room not found")
        lines = [f"# {room.name} — Pinned Insights\n"]
        msg_map = {m.get("id"): m for m in (room.messages or [])}
        for pin in room.pins or []:
            msg = msg_map.get(pin.get("message_id"))
            if not msg:
                continue
            agent = pin.get("agent_name") or pin.get("agent_id") or "Unknown"
            lines.append(f"## {agent}\n")
            lines.append(f"{msg.get('content', '')}\n")
        return "\n".join(lines)

    async def _load_agents(self, agent_ids: list[str]) -> Sequence[Agent]:
        if not agent_ids:
            return []
        result = await self.db.execute(
            select(Agent).where(Agent.id.in_(agent_ids), Agent.deleted_at.is_(None))
        )
        return result.scalars().all()

    async def _ensure_room_session(
        self, room: Room, agent: Agent, now: datetime
    ) -> Session:
        session_id = _room_session_id(room.id, agent.id)
        sess = await self.db.get(Session, session_id)
        if sess:
            if sess.status == "closed":
                sess.status = "ready"
            return sess

        sess = Session(
            id=session_id,
            agent_id=agent.id,
            user_id=room.user_id,
            channel=room.channel,
            messages=list(room.messages or []),
            status="ready",
            created_at=now,
            expires_at=room.expires_at,
            last_activity_at=now,
            room_id=room.id,
        )
        self.db.add(sess)
        return sess

    async def _mirror_messages_to_sessions(self, room: Room) -> None:
        """Overwrite each room session's message list with the canonical room thread."""
        result = await self.db.execute(
            select(Session).where(Session.room_id == room.id, Session.deleted_at.is_(None))
        )
        for sess in result.scalars().all():
            sess.messages = list(room.messages or [])
            sess.last_activity_at = datetime.now(UTC)
            sess.last_message_at = datetime.now(UTC)


async def mirror_room_reply(
    room_id: str, agent_id: str, assistant_message: dict[str, Any]
) -> Room | None:
    """Append an assistant reply to the room and mirror it to all room sessions.

    Called by ``reply_to_session`` when a room session receives an agent reply.
    Returns the updated room or ``None`` if the room does not exist.
    """
    async with get_db_session_manual() as db:
        room = await db.get(Room, room_id)
        if not room or room.deleted_at or room.status != "active":
            return None

        agent = await db.get(Agent, agent_id)
        msg = _room_message(
            role="assistant",
            content=assistant_message.get("content", ""),
            agent_id=agent_id,
            agent_name=agent.name if agent else agent_id,
            parent_id=assistant_message.get("parent_id"),
        )
        # Preserve optional fields from the runner (components, audio, attachments)
        for key in ("components", "audio_ref", "audio_url", "attachments"):
            if key in assistant_message:
                msg[key] = assistant_message[key]

        room.messages = (room.messages or []) + [msg]
        room.last_activity_at = datetime.now(UTC)

        service = RoomService(db)
        await service._mirror_messages_to_sessions(room)
        await db.commit()
        await db.refresh(room)
        return cast(Room | None, room)
