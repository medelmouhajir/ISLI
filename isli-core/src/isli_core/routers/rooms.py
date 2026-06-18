"""Council room API.

All endpoints are scoped to a ``user_id`` supplied by the caller (the Board UI).
Authentication is expected at the API gateway / session-token layer, consistent with
``routers/sessions.py``.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.db import get_db
from isli_core.event_manager import EventManager
from isli_core.models import Room
from isli_core.rooms.service import RoomService

DBSession = Annotated[AsyncSession, Depends(get_db)]

logger = structlog.get_logger()
router = APIRouter(prefix="/rooms", tags=["rooms"])


class RoomOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    user_id: str
    channel: str
    status: str
    messages: list[dict[str, Any]]
    agent_ids: list[str]
    pins: list[dict[str, Any]]
    room_metadata: dict[str, Any]
    expires_at: datetime
    last_activity_at: datetime | None
    created_at: datetime
    deleted_at: datetime | None


class RoomCreateIn(BaseModel):
    name: str
    agent_ids: list[str]
    user_id: str
    channel: str = "web"
    metadata: dict[str, Any] = {}


class RoomMessageIn(BaseModel):
    text: str
    user_id: str
    addressed_agent_ids: list[str] | None = None
    metadata: dict[str, Any] = {}


class RoomAgentIn(BaseModel):
    agent_id: str
    user_id: str


class RoomPinIn(BaseModel):
    message_id: str
    user_id: str


@router.get("", response_model=list[RoomOut])
async def list_rooms(
    db: DBSession,
    user_id: str,
    limit: int = 100,
) -> Sequence[Room]:
    svc = RoomService(db)
    rooms = await svc.list_rooms(user_id, limit=limit)
    return rooms


@router.post("", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
async def create_room(payload: RoomCreateIn, db: DBSession) -> Room:
    svc = RoomService(db)
    try:
        room = await svc.create_room(
            user_id=payload.user_id,
            name=payload.name,
            agent_ids=payload.agent_ids,
            channel=payload.channel,
        )
        if payload.metadata:
            room.room_metadata = payload.metadata
            await db.commit()
            await db.refresh(room)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await EventManager.emit("room:updated", {"room_id": room.id})
    return room


@router.get("/{room_id}", response_model=RoomOut)
async def get_room(room_id: str, user_id: str, db: DBSession) -> Room:
    svc = RoomService(db)
    room = await svc.get_room(room_id, user_id, active_only=False)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.get("/{room_id}/history")
async def get_room_history(room_id: str, user_id: str, db: DBSession) -> dict[str, Any]:
    svc = RoomService(db)
    room = await svc.get_room(room_id, user_id, active_only=False)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return {
        "room_id": room.id,
        "name": room.name,
        "agent_ids": room.agent_ids or [],
        "messages": room.messages or [],
        "pins": room.pins or [],
    }


@router.post("/{room_id}/message", response_model=RoomOut)
async def post_room_message(
    room_id: str,
    payload: RoomMessageIn,
    db: DBSession,
) -> Room:
    svc = RoomService(db)
    try:
        room, addressed = await svc.post_message(
            room_id=room_id,
            user_id=payload.user_id,
            text=payload.text,
            addressed_agent_ids=payload.addressed_agent_ids,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return room


@router.post("/{room_id}/agents", response_model=RoomOut)
async def add_room_agent(
    room_id: str,
    payload: RoomAgentIn,
    db: DBSession,
) -> Room:
    svc = RoomService(db)
    try:
        room = await svc.add_agent(room_id, payload.user_id, payload.agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room


@router.post("/{room_id}/close", response_model=RoomOut)
async def close_room(room_id: str, user_id: str, db: DBSession) -> Room:
    svc = RoomService(db)
    try:
        room = await svc.close_room(room_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room


@router.post("/{room_id}/pin", response_model=RoomOut)
async def pin_message(
    room_id: str,
    payload: RoomPinIn,
    db: DBSession,
) -> Room:
    svc = RoomService(db)
    try:
        room = await svc.pin_message(room_id, payload.user_id, payload.message_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room


@router.delete("/{room_id}/pin/{message_id}")
async def unpin_message(
    room_id: str,
    message_id: str,
    user_id: str,
    db: DBSession,
) -> dict[str, Any]:
    svc = RoomService(db)
    try:
        await svc.unpin_message(room_id, user_id, message_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "unpinned", "room_id": room_id, "message_id": message_id}


@router.post("/{room_id}/export-pins")
async def export_pins(room_id: str, user_id: str, db: DBSession) -> dict[str, Any]:
    svc = RoomService(db)
    try:
        markdown = await svc.export_pins(room_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"room_id": room_id, "markdown": markdown}
