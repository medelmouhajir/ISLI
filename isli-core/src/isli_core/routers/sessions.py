import base64
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.auth import create_internal_token, require_admin_auth, require_internal_auth
from isli_core.config import get_settings
from isli_core.cost.complexity import TaskComplexityScorer
from isli_core.db import get_db
from isli_core.event_manager import EventManager
from isli_core.jobs.journal_worker import update_session_journal
from isli_core.models import Agent, ChannelIdentity, ChannelMessage, Session, SharedWorkspace
from isli_core.redis_client import get_redis
from isli_core.redis_streams import add_to_stream
from isli_core.retry import exponential_backoff
from isli_core.routers.workspaces import (
    _create_file_download_token,
    _validate_path,
    fetch_file_metadata,
)

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
    journal_updated_at: datetime | None
    complexity_score: int | None
    complexity_tier: str | None
    routed_model_provider: str | None
    routed_model_id: str | None
    routed_model_reason: str | None
    session_metadata: dict[str, Any] | None
    room_id: str | None
    deleted_at: datetime | None


class JournalUpdateIn(BaseModel):
    journal: str | None


class SessionCreateIn(BaseModel):
    agent_id: str
    user_id: str | None = None
    channel: str = "web"


class ComponentPayload(BaseModel):
    component_type: str
    props: dict[str, Any]
    action_id: str | None = None
    text_fallback: str | None = None


class AttachmentIn(BaseModel):
    path: str
    workspace_id: str | None = None
    caption: str | None = None


class SessionReplyIn(BaseModel):
    text: str
    components: list[ComponentPayload] = []
    metadata: dict[str, Any] = {}
    audio_b64: str | None = None
    audio_voice: str | None = None
    voice_mode_enabled: bool = False
    attachments: list[AttachmentIn] = []


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
    archived: bool = False,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    if archived:
        query = select(Session).where(
            (Session.status == "closed") | (Session.deleted_at.is_not(None))
        )
    else:
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
        select(Session).where(
            Session.id == session_id,
            Session.deleted_at.is_(None),
            Session.status != "closed",
        )
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    # Enrich persisted attachment metadata with fresh signed URLs for the UI.
    if sess.messages:
        sess.messages = [
            _enrich_message_attachments(msg) for msg in sess.messages
        ]
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
    result = await db.execute(select(Session).where(Session.id == session_id))
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    all_messages = (sess.archived_messages or []) + (sess.messages or [])
    all_messages.sort(key=lambda m: m.get("timestamp", ""))
    all_messages = [_enrich_message_attachments(msg) for msg in all_messages]

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
    agent_check = await db.execute(
        select(Agent).where(Agent.id == payload.agent_id, Agent.deleted_at.is_(None))
    )
    if not agent_check.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{payload.agent_id}' not found or deleted",
        )

    now = datetime.now(UTC)
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
        select(Session).where(
            Session.id == session_id,
            Session.deleted_at.is_(None),
            Session.status != "closed",
        )
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(UTC)

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


MAX_REPLY_ATTACHMENTS = 5

_CHANNEL_ATTACHMENT_LIMITS: dict[str, dict[str, Any]] = {
    "telegram": {
        "max_size_bytes": 20 * 1024 * 1024,
        "allowed_types": {"image", "video", "audio", "document", "voice"},
    },
    "whatsapp": {
        "max_size_bytes": 16 * 1024 * 1024,
        "allowed_types": {"image", "video", "audio", "document"},
    },
    "email": {
        "max_size_bytes": 25 * 1024 * 1024,
        "allowed_types": {"image", "video", "audio", "document"},
    },
    "web": {
        "max_size_bytes": 100 * 1024 * 1024,
        "allowed_types": {"image", "video", "audio", "document"},
    },
}


def _media_category_from_mime(mime_type: str) -> str:
    mime = mime_type.lower().strip()
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "document"


def _attachment_fits_channel(attachment: dict[str, Any], channel: str | None) -> tuple[bool, str]:
    if not channel or channel == "web":
        return True, ""
    limits = _CHANNEL_ATTACHMENT_LIMITS.get(channel, _CHANNEL_ATTACHMENT_LIMITS["web"])
    cat = _media_category_from_mime(attachment.get("mime_type", "application/octet-stream"))
    if cat not in limits["allowed_types"]:
        return False, f"media type '{cat}' not allowed on {channel}"
    size = attachment.get("size_bytes", 0) or 0
    if size > limits["max_size_bytes"]:
        return False, f"{size / (1024 * 1024):.1f}MB exceeds {channel} limit"
    return True, ""


async def _resolve_attachment_scope(
    attachment: AttachmentIn,
    agent_id: str,
    db: AsyncSession,
) -> tuple[str, str]:
    """Return (scope, scope_id) for an attachment, validating shared workspace membership."""
    if attachment.workspace_id:
        scope_id = attachment.workspace_id
        result = await db.execute(
            select(SharedWorkspace).where(
                SharedWorkspace.id == scope_id,
                SharedWorkspace.deleted_at.is_(None),
            )
        )
        workspace = result.scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail=f"Shared workspace not found: {scope_id}")
        if agent_id != workspace.owner_id and agent_id not in (workspace.members or []):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied to shared workspace {scope_id}",
            )
        return "shared", scope_id
    return "agent", agent_id


async def _build_attachment_metadata(
    attachment: AttachmentIn,
    agent_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Resolve and fetch metadata for a single attachment (no signed URLs)."""
    scope, scope_id = await _resolve_attachment_scope(attachment, agent_id, db)
    valid_path = _validate_path(attachment.path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Attachment path is required")
    meta = await fetch_file_metadata(agent_id, scope, scope_id, valid_path)
    return {
        "agent_id": agent_id,
        "path": valid_path,
        "scope": scope,
        "scope_id": scope_id,
        "filename": meta["filename"],
        "mime_type": meta["mime_type"],
        "size_bytes": meta["size_bytes"],
        "caption": attachment.caption,
        "media_type": _media_category_from_mime(meta["mime_type"]),
    }


def _sign_attachment_url(
    attachment: dict[str, Any],
    core_api_url: str | None = None,
    expires_minutes: int = 10,
) -> dict[str, Any]:
    """Return a copy of the attachment metadata enriched with a fresh signed download URL.

    When ``core_api_url`` is omitted, a relative path is returned for browser clients
    that proxy through the Board UI (``/api/...``). Services inside the Docker network
    should pass the absolute internal URL (e.g. ``http://core:8000``).
    """
    token = _create_file_download_token(
        agent_id=attachment["agent_id"],
        scope=attachment["scope"],
        scope_id=attachment["scope_id"],
        path=attachment["path"],
        expires_minutes=expires_minutes,
    )
    base = core_api_url.rstrip("/") if core_api_url else ""
    signed = dict(attachment)
    signed["download_url"] = f"{base}/v1/internal/files/download?token={token}"
    signed["expires_at"] = (
        datetime.now(UTC) + timedelta(minutes=expires_minutes)
    ).isoformat()
    return signed


def _enrich_message_attachments(message: dict[str, Any]) -> dict[str, Any]:
    """Add fresh signed download URLs to any attachment metadata in a message."""
    attachments = message.get("attachments")
    if not attachments:
        return message
    message = dict(message)
    message["attachments"] = [
        _sign_attachment_url(att) if "download_url" not in att else att
        for att in attachments
    ]
    return message


@router.post("/{session_id}/reply")
async def reply_to_session(
    session_id: str,
    payload: SessionReplyIn,
    db: AsyncSession = Depends(get_db),
    auth: dict[str, Any] = Depends(require_internal_auth),
) -> dict[str, Any]:
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

    if auth.get("sub") != sess.agent_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to reply to this session",
        )

    # ── PII Mesh defense-in-depth validation ──
    agent_result = await db.execute(select(Agent).where(Agent.id == sess.agent_id))
    agent = agent_result.scalar_one_or_none()
    agent_config = agent.config or {} if agent else {}
    reply_text = payload.text
    if agent_config.get("pii_mesh_enabled", False):
        pii_token_pattern = r"\{\{PII:[a-z_]+:[a-f0-9]+\}\}"
        if re.search(pii_token_pattern, reply_text):
            logger.critical(
                "sessions.pii_tokens_in_reply",
                session_id=session_id,
                agent_id=sess.agent_id,
            )
            from isli_core.compliance.pii_keeper_client import PIIKeeperClient
            rehydrated = await PIIKeeperClient().rehydrate(reply_text, session_id)
            reply_text = rehydrated

    now = datetime.now(UTC)

    # --- Audio handling ---
    audio_b64_for_channels: str | None = payload.audio_b64

    # Phase 2: Auto-TTS when voice_mode is enabled and no explicit audio provided
    session_metadata = sess.session_metadata or {}
    voice_mode = session_metadata.get("voice_mode_enabled")
    if not audio_b64_for_channels and voice_mode:
        try:
            settings = get_settings()
            voice = payload.audio_voice or session_metadata.get("voice_preference")
            tts_token = create_internal_token(
                "core-api", scopes=["audio:tts"], expires_minutes=1
            )
            async with httpx.AsyncClient(timeout=30.0) as client:
                tts_resp = await client.post(
                    f"{settings.audio_url}/tts/synthesize",
                    json={"text": payload.text, "voice": voice},
                    headers={"X-Internal-Auth": tts_token},
                )
                tts_resp.raise_for_status()
                tts_data = tts_resp.json()

                # Check if it returned a reference (new pattern) or b64 (legacy)
                if tts_data.get("audio_ref"):
                    # It's already in Redis! We just use the ref.
                    audio_ref = tts_data.get("audio_ref")
                    audio_b64_for_channels = None # We'll use the ref
                    logger.info("sessions.auto_tts_ref", session_id=session_id, ref=audio_ref)
                else:
                    audio_b64_for_channels = tts_data.get("audio_b64")
                    logger.info("sessions.auto_tts_synthesized", session_id=session_id)
        except Exception as exc:
            logger.warning("sessions.auto_tts_failed", session_id=session_id, error=str(exc))

    # If audio is provided as Base64 (legacy or explicit), store in Redis and get a token
    audio_ref = locals().get("audio_ref")
    if audio_b64_for_channels and not audio_ref:
        try:
            MAX_AUDIO_BYTES = 5 * 1024 * 1024
            audio_bytes = base64.b64decode(audio_b64_for_channels)
            if len(audio_bytes) <= MAX_AUDIO_BYTES:
                from isli_core.redis_blob_client import get_blob_redis
                blob_id = str(uuid4())
                audio_ref = f"blob:audio:{blob_id}"
                redis = await get_blob_redis()
                await redis.setex(audio_ref, 86400, audio_bytes)
                logger.info(
                    "sessions.audio_blob_stored",
                    session_id=session_id,
                    ref=audio_ref,
                )
            else:
                logger.warning(
                    "sessions.audio_too_large",
                    session_id=session_id,
                    size=len(audio_bytes),
                )
        except Exception as exc:
            logger.warning(
                "sessions.audio_blob_store_failed",
                session_id=session_id,
                error=str(exc),
            )

    # --- Attachments handling (metadata only; signed URLs generated at forward/UI time) ---
    attachment_records: list[dict[str, Any]] = []
    if payload.attachments:
        raw_attachments = payload.attachments[:MAX_REPLY_ATTACHMENTS]
        if len(payload.attachments) > MAX_REPLY_ATTACHMENTS:
            logger.warning(
                "sessions.too_many_attachments",
                session_id=session_id,
                agent_id=sess.agent_id,
                requested=len(payload.attachments),
                kept=MAX_REPLY_ATTACHMENTS,
            )
        for att in raw_attachments:
            try:
                record = await _build_attachment_metadata(att, sess.agent_id, db)
                attachment_records.append(record)
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning(
                    "sessions.attachment_metadata_failed",
                    session_id=session_id,
                    agent_id=sess.agent_id,
                    path=att.path,
                    workspace_id=att.workspace_id,
                    error=str(exc),
                )

    # Prepare message dict
    msg: dict[str, Any] = {
        "id": str(uuid4()),
        "role": "assistant",
        "content": reply_text,
        "timestamp": now.isoformat(),
        "agent_id": sess.agent_id,
        "agent_name": agent.name if agent else "Unknown Agent",
    }
    if payload.components:
        msg["components"] = [c.model_dump() for c in payload.components]
    if audio_ref:
        msg["audio_ref"] = audio_ref
    if attachment_records:
        msg["attachments"] = attachment_records

    # --- Blob Token Rewrite for Web UI & Promotion Trigger ---
    text_tokens = re.findall(r"(blob:(?:audio|browser):[a-f0-9-]+)", reply_text)

    from isli_core.models import Outbox
    outbox_item = Outbox(
        topic="session:message_persist",
        payload={
            "session_id": session_id,
            "message": msg,
            "channel": sess.channel,
            "user_id": sess.user_id,
        }
    )
    db.add(outbox_item)

    # For immediate response, rewrite tokens to URLs
    settings = get_settings()
    api_msg_content = reply_text
    for token in text_tokens:
        blob_uuid = token.split(":")[-1]
        api_msg_content = api_msg_content.replace(
            token, f"{settings.core_api_url}/v1/blobs/{blob_uuid}"
        )

    api_response_msg: dict[str, Any] = dict(msg)
    api_response_msg["content"] = api_msg_content
    if audio_ref:
        blob_uuid = audio_ref.split(":")[-1]
        api_response_msg["audio_url"] = (
            f"{settings.core_api_url}/v1/blobs/{blob_uuid}"
        )
    if attachment_records:
        # Relative URL so browser clients download through the Board UI /api proxy.
        api_response_msg["attachments"] = [
            _sign_attachment_url(rec) for rec in attachment_records
        ]

    sess.last_activity_at = now
    sess.status = "ready"
    await db.commit()

    # Forward to external channels
    if sess.channel and sess.channel != "web" and sess.user_id:
        channel_text = payload.text
        if payload.components and payload.components[0].text_fallback:
            channel_text = payload.components[0].text_fallback

        async def _send_to_channels() -> None:
            payload_channels: dict[str, Any] = {
                "channel": sess.channel,
                "channel_user_id": sess.user_id,
                "text": channel_text,
                "agent_id": sess.agent_id,
            }
            if audio_ref:
                payload_channels["audio_ref"] = audio_ref

            # Build channel-specific attachment payload with fresh signed URLs
            channel_attachments: list[dict[str, Any]] = []
            for rec in attachment_records:
                ok, reason = _attachment_fits_channel(rec, sess.channel)
                if not ok:
                    logger.warning(
                        "sessions.attachment_dropped_for_channel",
                        session_id=session_id,
                        channel=sess.channel,
                        filename=rec.get("filename"),
                        reason=reason,
                    )
                    continue
                signed = _sign_attachment_url(rec, settings.core_api_url)
                channel_attachments.append(signed)

            if channel_attachments:
                payload_channels["attachments"] = channel_attachments

            async with httpx.AsyncClient() as client:
                channels_token = create_internal_token(
                    "core", scopes=["channels:send"], expires_minutes=5
                )
                resp = await client.post(
                    f"{settings.channels_url}/send",
                    json=payload_channels,
                    headers={"X-Internal-Auth": channels_token},
                    timeout=30.0,
                )
                resp.raise_for_status()

        try:
            from isli_core.dynamic_config import get_setting
            max_retries = await get_setting(
                db, "default_max_retries", scope="general", default=3
            )
            base_delay = await get_setting(
                db, "default_base_delay_seconds", scope="general", default=1.0
            )
            max_delay = await get_setting(
                db, "default_max_delay_seconds", scope="general", default=10.0
            )
            _ = await exponential_backoff(
                _send_to_channels,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
            )
        except Exception as exc:
            logger.error("sessions.reply_send_failed", session_id=session_id, error=str(exc))

    # Outbound channel audit record
    try:
        outbound_audit = ChannelMessage(
            session_id=session_id,
            sequence_number=len(sess.messages or []) + 1,
            channel=sess.channel or "web",
            direction="outbound",
            content=api_msg_content[:2000],
            raw_payload={
                "agent_id": sess.agent_id,
                "attachments": [
                    {
                        "filename": r.get("filename"),
                        "mime_type": r.get("mime_type"),
                        "size_bytes": r.get("size_bytes"),
                    }
                    for r in attachment_records
                ],
                "audio_ref": audio_ref,
            },
        )
        db.add(outbound_audit)
        await db.commit()
    except Exception as exc:
        logger.warning("sessions.outbound_audit_failed", session_id=session_id, error=str(exc))

    await EventManager.emit("session:updated", {"session_id": session_id})
    try:
        redis = await get_redis()
        await redis.delete(f"session:{session_id}:draft")
        await redis.delete(f"session:{session_id}:debug_trace")
    except Exception:
        pass

    return {"status": "sent", "session_id": session_id, "message": api_response_msg}


class SessionStatusUpdateIn(BaseModel):
    status: str


@router.post("/{session_id}/status")
async def update_session_status(
    session_id: str,
    payload: SessionStatusUpdateIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_internal_auth),
):
    """Allow the agent runner to explicitly update session status (e.g. ready after processing)."""
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
    if auth.get("sub") != sess.agent_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this session")

    sess.status = payload.status
    sess.last_activity_at = datetime.now(UTC)
    await db.commit()

    await EventManager.emit("session:updated", {"session_id": session_id})
    return {"status": "updated", "session_id": session_id, "new_status": sess.status}


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

    now = datetime.now(UTC)

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
        select(Session).where(
            Session.id == session_id,
            Session.deleted_at.is_(None),
            Session.status != "closed",
        )
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


@router.put("/{session_id}/journal", response_model=SessionOut)
async def update_session_journal_text(
    session_id: str,
    data: JournalUpdateIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_admin_auth),
):
    """Manually update the session journal text."""
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None))
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    old_journal = sess.journal
    sess.journal = data.journal
    sess.journal_updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(sess)

    await EventManager.emit(
        "memory:journal_updated",
        {
            "session_id": session_id,
            "agent_id": sess.agent_id,
            "old_journal": old_journal,
            "new_journal": sess.journal,
        },
    )
    return sess


@router.post("/{session_id}/journal/regenerate", response_model=SessionOut)
async def regenerate_session_journal(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_admin_auth),
):
    """Force-regenerate the session journal using the Keeper."""
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None))
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    success = await update_session_journal(db, sess, trigger="manual_regenerate")
    if not success:
        raise HTTPException(status_code=500, detail="Failed to regenerate journal")

    await db.refresh(sess)
    return sess


@router.delete("/{session_id}/journal", response_model=SessionOut)
async def clear_session_journal(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_admin_auth),
):
    """Clear the session journal."""
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None))
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    sess.journal = None
    sess.journal_updated_at = None
    await db.commit()
    await db.refresh(sess)

    await EventManager.emit(
        "memory:journal_updated",
        {
            "session_id": session_id,
            "agent_id": sess.agent_id,
            "old_journal": None,
            "new_journal": None,
        },
    )
    return sess


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id))
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


@router.post("/{session_id}/restore", response_model=SessionOut)
async def restore_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id))
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    agent_result = await db.execute(
        select(Agent).where(Agent.id == sess.agent_id, Agent.deleted_at.is_(None))
    )
    if not agent_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400, detail="Cannot restore session: owning agent is deleted"
        )

    sess.status = "ready"
    sess.deleted_at = None
    await db.commit()
    await db.refresh(sess)
    await EventManager.emit("session:updated", {"session_id": session_id})
    return sess
