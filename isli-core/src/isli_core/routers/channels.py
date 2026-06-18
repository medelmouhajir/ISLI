import json
from typing import Any
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from isli_core.access import resolve_access
from isli_core.auth import verify_webhook_signature
from isli_core.cost.complexity import TaskComplexityScorer
from isli_core.db import get_db
from isli_core.event_manager import EventManager
from isli_core.models import Agent, ChannelMessage, Task, Session, UserConsent
from isli_core.redis_streams import add_to_stream
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

    # Idempotency check via DB. Use exists() + scalar_one() so multiple rows are safe.
    dedup_key = payload.get("dedup_id") or payload.get("message_id")
    if dedup_key:
        dedup_exists = await db.execute(
            select(
                exists().where(
                    ChannelMessage.raw_payload.cast(JSONB).contains({"dedup_id": dedup_key})
                )
            )
        )
        if dedup_exists.scalar_one():
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
        
        # --- Audio blob handling: detect token and call STT ---
        if msg_text and msg_text.startswith("blob:audio:"):
            from isli_core.config import get_settings
            import httpx
            from isli_core.auth import create_internal_token
            
            settings = get_settings()
            logger.info("channels.webhook_stt_dispatch", blob_key=msg_text, session_id=session_id)
            
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    stt_token = create_internal_token("core", scopes=["audio:stt"], expires_minutes=5)
                    resp = await client.post(
                        f"{settings.audio_url}/stt/transcribe",
                        json={"audio_ref": msg_text},
                        headers={"X-Internal-Auth": stt_token}
                    )
                    resp.raise_for_status()
                    stt_result = resp.json()
                    transcribed_text = stt_result.get("text", "").strip()
                    
                    if transcribed_text:
                        logger.info("channels.webhook_stt_success", session_id=session_id, text_len=len(transcribed_text))
                        msg_text = transcribed_text
                    else:
                        logger.warning("channels.webhook_stt_empty", session_id=session_id)
                        # We keep the blob token as text so the agent knows it was audio, 
                        # but ideally we'd have a fallback.
            except Exception as exc:
                logger.error("channels.webhook_stt_failed", session_id=session_id, error=str(exc))
                # Fallback: keep the token in the text so it's not lost

        # Complexity scoring at ingress for model routing
        score, tier = TaskComplexityScorer.score_task_input(msg_text)
        sess.complexity_score = score
        sess.complexity_tier = tier

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

        # Notify UI and enqueue context injection / agent turn
        await EventManager.emit("session:updated", {"session_id": session_id})
        agent_config = {}
        if agent_id:
            agent_result = await db.execute(
                select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None))
            )
            agent_row = agent_result.scalar_one_or_none()
            if agent_row:
                agent_config = agent_row.config or {}
        await add_to_stream(
            "context:requests",
            {
                "type": "session",
                "id": str(sess.id),
                "agent_id": str(sess.agent_id),
                "task_description": f"Session with {sess.user_id or 'user'}: {msg_text}",
                "session_id": str(sess.id),
                "complexity_score": score,
                "complexity_tier": tier,
                "memory_similarity_threshold": agent_config.get("memory_similarity_threshold", 0.4),
            },
        )

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
