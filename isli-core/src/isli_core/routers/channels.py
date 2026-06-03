import json
from typing import Any
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from isli_core.access import resolve_access
from isli_core.auth import verify_webhook_signature
from isli_core.db import get_db
from isli_core.models import ChannelMessage, Task, Session, UserConsent
from isli_core.schemas import validate_event

logger = structlog.get_logger()
router = APIRouter(prefix="/channels", tags=["channels"])


class WebhookPayload(BaseModel):
    event_type: str
    data: dict[str, Any]


@router.post("/{channel}/webhook")
async def channel_webhook(channel: str, request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    if not verify_webhook_signature(channel, request, body):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Idempotency check via Redis or DB (simplified: check dedup key in payload)
    dedup_key = payload.get("dedup_id") or payload.get("message_id")
    if dedup_key:
        existing = await db.execute(
            select(ChannelMessage).where(
                ChannelMessage.raw_payload.cast(JSONB).contains({"dedup_id": dedup_key})
            )
        )
        if existing.scalar_one_or_none():
            logger.info("channels.dedup_drop", channel=channel, dedup_id=dedup_key)
            return {"status": "deduplicated"}

    user_id = payload.get("user_id")
    if user_id is not None:
        user_id = str(user_id)

    agent_id = payload.get("agent_id")

    # Mode-aware access control (opt_in / open / whitelist / closed / scheduled)
    if agent_id:
        await resolve_access(db, agent_id, user_id, channel)
    else:
        # Fallback path: simple consent gate for non-session messages
        if user_id is not None:
            consent = await db.execute(
                select(UserConsent).where(
                    UserConsent.user_id == user_id,
                    UserConsent.channel == channel,
                    UserConsent.granted == True,
                )
            )
            if not consent.scalar_one_or_none():
                logger.warning("channels.consent_missing", channel=channel, user_id=user_id)
                raise HTTPException(status_code=403, detail="consent_required")

    if agent_id:
        # Session conversation path: direct 1:1 chat with the agent
        session_id = payload.get("session_id") or f"sess_{channel}_{agent_id}_{user_id or 'unknown'}"
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.deleted_at.is_(None)
            )
        )
        sess = result.scalar_one_or_none()

        if not sess:
            # Check for a soft-deleted session and revive it instead of creating a duplicate PK
            soft_deleted_result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            soft_deleted = soft_deleted_result.scalar_one_or_none()
            if soft_deleted:
                soft_deleted.deleted_at = None
                soft_deleted.status = "pending_context"
                soft_deleted.expires_at = now + timedelta(hours=24)
                soft_deleted.last_activity_at = now
                sess = soft_deleted
                logger.info("channels.session_revived", session_id=session_id, agent_id=agent_id)
            else:
                sess = Session(
                    id=session_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    channel=channel,
                    messages=[],
                    consent_given=True,
                    consent_at=now,
                    expires_at=now + timedelta(hours=24),
                    status="pending_context",
                )
                db.add(sess)
        else:
            sess.status = "pending_context"
            sess.expires_at = now + timedelta(hours=24)

        # Append inbound message
        msg_text = payload.get("text", "")
        sess.messages = (sess.messages or []) + [
            {"role": "user", "content": msg_text, "timestamp": now.isoformat()}
        ]
        sess.last_activity_at = now
        sess.last_message_at = now
        sess.token_count = len(str(sess.messages)) // 4

        await db.commit()
        await db.refresh(sess)

        # Store raw channel message for audit
        msg = ChannelMessage(
            session_id=session_id,
            sequence_number=len(sess.messages),
            channel=channel,
            direction="inbound",
            content=msg_text,
            raw_payload=payload,
        )
        db.add(msg)
        await db.commit()

        logger.info("channels.session_ingested", channel=channel, session_id=sess.id, agent_id=agent_id)
        return {"status": "ok", "session_id": sess.id}
    else:
        # Fallback: create a Kanban Task (agent-to-agent or unassigned message)
        task = Task(
            title=f"{channel} message",
            type="channel_message",
            status="inbox",
            created_by=user_id or "system",
            input=payload.get("text", ""),
            channel=channel,
            session_id=payload.get("session_id"),
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        # Store raw channel message
        msg = ChannelMessage(
            session_id=payload.get("session_id", "unknown"),
            sequence_number=payload.get("sequence_number", 0),
            channel=channel,
            direction="inbound",
            content=payload.get("text", ""),
            raw_payload=payload,
        )
        db.add(msg)
        await db.commit()

        logger.info("channels.webhook_ingested", channel=channel, task_id=task.id)
        return {"status": "ok", "task_id": task.id}
