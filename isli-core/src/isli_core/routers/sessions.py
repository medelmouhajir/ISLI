from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

import base64
import json
import structlog
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from isli_core.auth import create_internal_token

from isli_core.db import get_db
from isli_core.redis_client import get_redis
from isli_core.models import Session, ChannelMessage, ChannelIdentity
from isli_core.config import get_settings
from isli_core.auth import require_internal_auth, require_admin_auth
from isli_core.retry import exponential_backoff
from isli_core.event_manager import EventManager
from isli_core.redis_streams import add_to_stream
from isli_core.cost.complexity import TaskComplexityScorer
from isli_core.memory.context_cache import ContextCache
from isli_core.utils.tokens import count_message_tokens

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
    complexity_score: int | None
    complexity_tier: str | None
    routed_model_provider: str | None
    routed_model_id: str | None
    routed_model_reason: str | None
    session_metadata: dict[str, Any] | None


class SessionCreateIn(BaseModel):
    agent_id: str
    user_id: str | None = None
    channel: str = "web"


class ComponentPayload(BaseModel):
    component_type: str
    props: dict[str, Any]
    action_id: str | None = None
    text_fallback: str | None = None


class SessionReplyIn(BaseModel):
    text: str
    components: list[ComponentPayload] = []
    metadata: dict[str, Any] = {}
    audio_b64: str | None = None
    audio_voice: str | None = None
    voice_mode_enabled: bool = False


class SessionActionIn(BaseModel):
    action_id: str
    action_type: str
    payload: dict[str, Any] = {}


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    agent_id: str | None = None,
    channel: str | None = None,
    user_id: str | None = None,
    include_closed: bool = False,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    query = select(Session).where(Session.deleted_at.is_(None))
    if not include_closed:
        query = query.where(Session.status != "closed")
    if agent_id:
        query = query.where(Session.agent_id == agent_id)
    if channel:
        query = query.where(Session.channel == channel)
    if user_id:
        query = query.where(Session.user_id == user_id)

    query = query.order_by(Session.last_activity_at.desc()).limit(limit)
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


class SessionHistoryOut(BaseModel):
    model_config = {"from_attributes": True}

    session_id: str
    agent_id: str
    user_id: str | None
    channel: str | None
    all_messages: list[dict[str, Any]]
    created_at: datetime
    last_activity_at: datetime | None


@router.get("/{session_id}/history", response_model=SessionHistoryOut)
async def get_session_history(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None))
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    all_messages = (sess.archived_messages or []) + (sess.messages or [])
    all_messages.sort(key=lambda m: m.get("timestamp", ""))

    return SessionHistoryOut(
        session_id=sess.id,
        agent_id=sess.agent_id,
        user_id=sess.user_id,
        channel=sess.channel,
        all_messages=all_messages,
        created_at=sess.created_at,
        last_activity_at=sess.last_activity_at,
    )


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
    # Store per-session metadata override (e.g., streaming_mode, voice_mode)
    if payload.metadata:
        current_metadata = sess.session_metadata or {}
        current_metadata.update(payload.metadata)
        sess.session_metadata = current_metadata
    # Persist voice_mode toggle from UI
    if payload.voice_mode_enabled is not None:
        current_metadata = sess.session_metadata or {}
        current_metadata["voice_mode_enabled"] = payload.voice_mode_enabled
        sess.session_metadata = current_metadata

    # --- Channel identity upsert (moved from worker to ingress) ---
    if sess.user_id and sess.channel and sess.channel != "web":
        from isli_core.models import Agent
        agent_result = await db.execute(
            select(Agent).where(Agent.id == sess.agent_id, Agent.deleted_at.is_(None))
        )
        agent_row = agent_result.scalar_one_or_none()
        if agent_row and agent_row.user_id:
            existing = await db.execute(
                select(ChannelIdentity).where(
                    ChannelIdentity.channel == sess.channel,
                    ChannelIdentity.channel_user_id == sess.user_id,
                    ChannelIdentity.agent_id == sess.agent_id,
                )
            )
            if not existing.scalar_one_or_none():
                identity = ChannelIdentity(
                    channel=sess.channel,
                    channel_user_id=sess.user_id,
                    board_user_id=agent_row.user_id,
                    agent_id=sess.agent_id,
                )
                db.add(identity)
                logger.info(
                    "channel_identity.created",
                    channel=sess.channel,
                    channel_user_id=sess.user_id,
                    board_user_id=agent_row.user_id,
                    agent_id=sess.agent_id,
                )

    # Complexity scoring at ingress
    score, tier = TaskComplexityScorer.score_task_input(payload.text)
    sess.complexity_score = score
    sess.complexity_tier = tier

    # Mark as pending context so the ContextWorker picks it up
    # NOTE: kept during transition window for rollback compatibility
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

    # Push to Redis Stream for unified ContextWorker
    try:
        agent_config = agent_row.config if agent_row and agent_row.config else {}
    except NameError:
        agent_config = {}
    await add_to_stream(
        "context:requests",
        {
            "type": "session",
            "id": str(sess.id),
            "agent_id": str(sess.agent_id),
            "task_description": f"Session with {sess.user_id or 'user'}: {payload.text}",
            "session_id": str(sess.id),
            "complexity_score": score,
            "complexity_tier": tier,
            "memory_similarity_threshold": agent_config.get("memory_similarity_threshold", 0.4),
        },
    )

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

    # --- Audio handling ---
    audio_url: str | None = None
    audio_b64_for_channels: str | None = payload.audio_b64

    # Phase 2: Auto-TTS when voice_mode is enabled and no explicit audio provided
    if not audio_b64_for_channels and sess.session_metadata and sess.session_metadata.get("voice_mode_enabled"):
        try:
            settings = get_settings()
            async with httpx.AsyncClient(timeout=30.0) as client:
                tts_resp = await client.post(
                    f"{settings.audio_url}/tts/synthesize",
                    json={
                        "text": payload.text,
                        "voice": payload.audio_voice or sess.session_metadata.get("voice_preference"),
                    },
                    headers={"X-Internal-Auth": create_internal_token("core-api", scopes=["audio:tts"], expires_minutes=1)},
                )
                tts_resp.raise_for_status()
                tts_data = tts_resp.json()
                audio_b64_for_channels = tts_data.get("audio_b64")
                logger.info(
                    "sessions.auto_tts_synthesized",
                    session_id=session_id,
                    voice=tts_data.get("voice"),
                    duration_ms=tts_data.get("duration_ms"),
                )
        except Exception as exc:
            logger.warning("sessions.auto_tts_failed", session_id=session_id, error=str(exc))
            # Best-effort: continue with text-only reply

    # If audio is provided (explicit or auto-TTS), decode, validate size, upload to workspace
    if audio_b64_for_channels:
        try:
            # Secondary size guard: decoded bytes must be <= 5 MB
            MAX_AUDIO_BYTES = 5 * 1024 * 1024
            audio_bytes = base64.b64decode(audio_b64_for_channels)
            if len(audio_bytes) > MAX_AUDIO_BYTES:
                logger.warning(
                    "sessions.audio_too_large",
                    session_id=session_id,
                    size=len(audio_bytes),
                    max=MAX_AUDIO_BYTES,
                )
                audio_b64_for_channels = None
            else:
                from isli_core.routers.workspaces import upload_bytes_to_workspace
                audio_filename = f"{uuid4()}.wav"
                workspace_path = f"_attachments/audio/{session_id}/{audio_filename}"
                await upload_bytes_to_workspace(
                    agent_id=sess.agent_id,
                    path=workspace_path,
                    data=audio_bytes,
                    scope="attachment",
                    scope_id=session_id,
                )
                audio_url = f"/v1/sessions/{session_id}/audio/{audio_filename}"
                logger.info(
                    "sessions.audio_uploaded",
                    session_id=session_id,
                    filename=audio_filename,
                    size=len(audio_bytes),
                )
        except Exception as exc:
            logger.warning("sessions.audio_upload_failed", session_id=session_id, error=str(exc))
            audio_b64_for_channels = None
            audio_url = None

    # Append assistant reply to session messages, including inline components and audio
    msg = {"role": "assistant", "content": payload.text, "timestamp": now.isoformat()}
    if payload.components:
        msg["components"] = [c.model_dump() for c in payload.components]
    if audio_url:
        msg["audio_url"] = audio_url
    sess.messages = (sess.messages or []) + [msg]
    sess.last_activity_at = now
    sess.last_message_at = now
    sess.token_count = count_message_tokens(sess.messages)
    sess.status = "ready"
    await db.commit()

    # Determine text to send to external channels (text_fallback if available)
    channel_text = payload.text
    if payload.components and payload.components[0].text_fallback:
        channel_text = payload.components[0].text_fallback

    # Store outbound channel message for audit
    msg_audit = ChannelMessage(
        session_id=session_id,
        sequence_number=len(sess.messages),
        channel=sess.channel or "unknown",
        direction="outbound",
        content=channel_text,
        raw_payload={
            "source": "agent_reply",
            "agent_id": sess.agent_id,
            "components": msg.get("components", []),
        },
    )
    db.add(msg_audit)
    await db.commit()

    # Emit update event for UI
    await EventManager.emit("session:updated", {"session_id": session_id})

    # Clear streaming draft and debug trace keys
    try:
        redis = await get_redis()
        await redis.delete(f"session:{session_id}:draft")
        await redis.delete(f"session:{session_id}:debug_trace")
    except Exception as exc:
        logger.warning("sessions.clear_draft_failed", session_id=session_id, error=str(exc))

    # Forward reply to user via channels service (only for external channels)
    if sess.channel and sess.channel != "web" and sess.user_id:
        settings = get_settings()
        async def _send_to_channels():
            payload_channels = {
                "channel": sess.channel,
                "channel_user_id": sess.user_id,
                "text": channel_text,
                "agent_id": sess.agent_id,
            }
            if audio_b64_for_channels:
                payload_channels["audio_b64"] = audio_b64_for_channels
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.channels_url}/send",
                    json=payload_channels,
                    headers={"X-Internal-Auth": create_internal_token("core", scopes=["channels:send"], expires_minutes=5)},
                    timeout=10.0,
                )
                resp.raise_for_status()

        try:
            from isli_core.dynamic_config import get_setting
            max_retries = await get_setting(db, "default_max_retries", scope="general", default=3)
            base_delay = await get_setting(db, "default_base_delay_seconds", scope="general", default=1.0)
            max_delay = await get_setting(db, "default_max_delay_seconds", scope="general", default=10.0)
            await exponential_backoff(
                _send_to_channels,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
            )
        except Exception as exc:
            logger.error("sessions.reply_send_failed", session_id=session_id, error=str(exc))
            # We still return success because the message is persisted in the DB;
            # the channels delivery can be retried later.
    else:
        logger.debug("sessions.skip_external_forward", session_id=session_id, channel=sess.channel)

    return {"status": "sent", "session_id": session_id}


@router.get("/{session_id}/draft")
async def get_session_draft(session_id: str):
    redis = await get_redis()
    draft = await redis.get(f"session:{session_id}:draft")
    return {"session_id": session_id, "draft": draft or ""}


@router.get("/{session_id}/debug-trace")
async def get_session_debug_trace(
    session_id: str,
    admin: str = Depends(require_admin_auth),
):
    redis = await get_redis()
    trace_key = f"session:{session_id}:debug_trace"
    raw = await redis.lrange(trace_key, 0, -1)
    events = [json.loads(r) for r in raw]
    return {"session_id": session_id, "events": list(reversed(events))}


@router.post("/{session_id}/action")
async def session_action(
    session_id: str,
    payload: SessionActionIn,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.deleted_at.is_(None),
            Session.status != "closed",
        )
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(timezone.utc)

    # Optional deduplication: skip identical action within 1 second window
    existing = sess.messages or []
    if existing:
        last = existing[-1]
        if (
            last.get("role") == "user"
            and last.get("type") == "action"
            and last.get("action_id") == payload.action_id
            and last.get("action_type") == payload.action_type
            and last.get("payload") == payload.payload
        ):
            last_ts_str = last.get("timestamp", "")
            try:
                from datetime import datetime as _dt
                last_ts = _dt.fromisoformat(last_ts_str.replace("Z", "+00:00"))
                if (now - last_ts).total_seconds() < 1.0:
                    return {"status": "deduplicated", "session_id": session_id}
            except Exception:
                pass

    import json as _json

    action_content = f"User action: {payload.action_type} on {payload.action_id}"
    if payload.payload:
        action_content += f"\nPayload: {_json.dumps(payload.payload)}"

    sess.messages = existing + [
        {
            "role": "user",
            "type": "action",
            "content": action_content,
            "action_id": payload.action_id,
            "action_type": payload.action_type,
            "payload": payload.payload,
            "timestamp": now.isoformat(),
        }
    ]
    sess.last_activity_at = now

    # Complexity scoring at ingress
    score, tier = TaskComplexityScorer.score_task_input(action_content)
    sess.complexity_score = score
    sess.complexity_tier = tier

    sess.status = "pending_context"
    await db.commit()

    # Push to Redis Stream for unified ContextWorker
    await add_to_stream(
        "context:requests",
        {
            "type": "session",
            "id": str(sess.id),
            "agent_id": str(sess.agent_id),
            "task_description": f"Session with {sess.user_id or 'user'}: {action_content}",
            "session_id": str(sess.id),
            "complexity_score": score,
            "complexity_tier": tier,
            "memory_similarity_threshold": 0.4,
        },
    )

    await EventManager.emit("session:updated", {"session_id": sess.id})
    return {"status": "queued", "session_id": session_id}


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


@router.get("/{session_id}/audio/{filename}")
async def download_session_audio(
    session_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_internal_auth),
):
    """Serve an audio attachment uploaded for a session reply.

    Proxies to the workspace service with internal auth so the browser
    can play the file without needing admin credentials.
    """
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None))
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    # Allow either the session's agent or a board/admin token
    caller = auth.get("sub")
    if caller != sess.agent_id and auth.get("scopes", []) != ["agent"]:
        # Non-agent tokens (board/admin) are always allowed
        pass
    elif caller != sess.agent_id:
        raise HTTPException(status_code=403, detail="Not authorized for this session")

    settings = get_settings()
    workspace_path = f"_attachments/audio/{session_id}/{filename}"
    token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=1)

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{settings.workspace_url}/download",
            params={
                "agent_id": sess.agent_id,
                "path": workspace_path,
                "scope": "attachment",
                "scope_id": session_id,
            },
            headers={"X-Internal-Auth": f"Bearer {token}"},
        )
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Audio file not found")
    resp.raise_for_status()

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        resp.aiter_bytes(),
        media_type=resp.headers.get("content-type", "audio/wav"),
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
