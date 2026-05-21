from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import structlog

from isli_core.db import get_db
from isli_core.models import Session, ChannelMessage
from isli_core.config import get_settings
from isli_core.auth import require_internal_auth
from isli_core.retry import exponential_backoff
from isli_core.event_manager import EventManager

logger = structlog.get_logger()
router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    agent_id: str
    user_id: str | None
    channel: str | None
    messages: list[dict[str, Any]]
    token_count: int
    consent_given: bool
    status: str
    context_summary: str | None
    created_at: datetime
    expires_at: datetime
    last_activity_at: datetime | None
    compacted_at: datetime | None
    journal: str | None


class SessionCreateIn(BaseModel):
    agent_id: str
    user_id: str | None = None
    channel: str = "web"


class SessionReplyIn(BaseModel):
    text: str


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Session).where(Session.deleted_at.is_(None), Session.status != "closed")
    if agent_id:
        query = query.where(Session.agent_id == agent_id)
    
    query = query.order_by(Session.last_activity_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None), Session.status != "closed")
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess


@router.post("", response_model=SessionOut)
async def create_session(
    payload: SessionCreateIn,
    db: AsyncSession = Depends(get_db),
):
    from isli_core.models import Agent
    agent_check = await db.execute(select(Agent).where(Agent.id == payload.agent_id, Agent.deleted_at.is_(None)))
    if not agent_check.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Agent '{payload.agent_id}' not found or deleted")

    now = datetime.now(timezone.utc)
    sess = Session(
        id=str(uuid4()),
        agent_id=payload.agent_id,
        user_id=payload.user_id,
        channel=payload.channel,
        messages=[],
        status="ready",
        created_at=now,
        expires_at=now + timedelta(hours=24),
        last_activity_at=now,
    )
    db.add(sess)
    await db.commit()
    await db.refresh(sess)
    return sess


@router.post("/{session_id}/message")
async def send_human_message(
    session_id: str,
    payload: SessionReplyIn,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None), Session.status != "closed")
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(timezone.utc)

    # Append human message
    sess.messages = (sess.messages or []) + [
        {"role": "user", "content": payload.text, "timestamp": now.isoformat()}
    ]
    sess.last_activity_at = now
    sess.last_message_at = now
    # Mark as pending context so the InjectorWorker picks it up and emits session:message to agent
    sess.status = "pending_context"
    
    await db.commit()

    # Store inbound channel message for audit
    msg = ChannelMessage(
        session_id=session_id,
        sequence_number=len(sess.messages),
        channel=sess.channel or "web",
        direction="inbound",
        content=payload.text,
        raw_payload={"source": "ui_chat"},
    )
    db.add(msg)
    await db.commit()

    # Emit update event for UI
    await EventManager.emit("session:updated", {"session_id": session_id})

    return {"status": "queued", "session_id": session_id}


@router.post("/{session_id}/reply")
async def reply_to_session(
    session_id: str,
    payload: SessionReplyIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_internal_auth),
):
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None), Session.status != "closed")
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if auth.get("sub") != sess.agent_id:
        raise HTTPException(status_code=403, detail="Not authorized to reply to this session")

    now = datetime.now(timezone.utc)

    # Append assistant reply to session messages
    sess.messages = (sess.messages or []) + [
        {"role": "assistant", "content": payload.text, "timestamp": now.isoformat()}
    ]
    sess.last_activity_at = now
    sess.last_message_at = now
    sess.token_count = len(str(sess.messages)) // 4
    sess.status = "ready"
    await db.commit()

    # Store outbound channel message for audit
    msg = ChannelMessage(
        session_id=session_id,
        sequence_number=len(sess.messages),
        channel=sess.channel or "unknown",
        direction="outbound",
        content=payload.text,
        raw_payload={"source": "agent_reply", "agent_id": sess.agent_id},
    )
    db.add(msg)
    await db.commit()

    # Emit update event for UI
    await EventManager.emit("session:updated", {"session_id": session_id})

    # Forward reply to user via channels service (only for external channels)
    if sess.channel and sess.channel != "web" and sess.user_id:
        settings = get_settings()
        async def _send_to_channels():
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.channels_url}/send",
                    json={
                        "channel": sess.channel,
                        "channel_user_id": sess.user_id,
                        "text": payload.text,
                        "agent_id": sess.agent_id,
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()

        try:
            await exponential_backoff(_send_to_channels, max_retries=3, base_delay=1.0, max_delay=10.0)
        except Exception as exc:
            logger.error("sessions.reply_send_failed", session_id=session_id, error=str(exc))
            # We still return success because the message is persisted in the DB;
            # the channels delivery can be retried later.
    else:
        logger.debug("sessions.skip_external_forward", session_id=session_id, channel=sess.channel)

    return {"status": "sent", "session_id": session_id}


@router.post("/{session_id}/close")
async def close_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None), Session.status != "closed")
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    sess.status = "closed"
    await db.commit()
    await EventManager.emit("session:updated", {"session_id": session_id})
    return {"status": "closed", "session_id": session_id}


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None))
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.execute(
        delete(ChannelMessage).where(ChannelMessage.session_id == session_id)
    )
    await db.delete(sess)
    await db.commit()
    await EventManager.emit("session:updated", {"session_id": session_id})
    return None
