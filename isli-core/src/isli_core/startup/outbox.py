import re
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from isli_core.db import get_db_session_manual
from isli_core.event_manager import EventManager
from isli_core.jobs.outbox_worker import register_outbox_handler
from isli_core.models import ChannelMessage, Room, Session
from isli_core.redis_blob_client import get_blob_redis
from isli_core.routers.workspaces import upload_bytes_to_workspace

logger = structlog.get_logger()

async def handle_session_persist(
    topic: str, payload: dict[str, Any], headers: dict[str, Any]
) -> None:
    """Authoritatively persist a session message and promote blob tokens to disk."""
    session_id = payload.get("session_id")
    msg = payload.get("message")
    channel = payload.get("channel")

    if not session_id or not msg:
        logger.error("outbox.session_persist.invalid_payload", payload=payload)
        return

    async with get_db_session_manual() as db:
        # 1. Fetch the session
        result = await db.execute(select(Session).where(Session.id == session_id))
        sess = result.scalar_one_or_none()
        if not sess:
            logger.error("outbox.session_persist.session_not_found", session_id=session_id)
            return

        # 2. Promotion Logic: detect blob tokens in message content and audio_ref
        content = msg.get("content", "")
        tokens = re.findall(r"(blob:(?:audio|browser):[a-f0-9-]+)", content)

        # Also check for explicit audio_ref field
        audio_ref = msg.get("audio_ref")
        if audio_ref and audio_ref.startswith("blob:") and audio_ref not in tokens:
            tokens.append(audio_ref)

        redis = await get_blob_redis()

        for token in tokens:
            blob_bytes = await redis.get(token)
            if blob_bytes:
                # Promote to Workspace disk
                blob_uuid = token.split(":")[-1]
                service = token.split(":")[1]
                ext = "wav" if service == "audio" else "png"

                workspace_path = f"_attachments/{service}/{session_id}/{blob_uuid}.{ext}"
                try:
                    await upload_bytes_to_workspace(
                        agent_id=sess.agent_id,
                        path=workspace_path,
                        data=blob_bytes,
                        scope="attachment",
                        scope_id=session_id,
                    )

                    # Update content if token was found there
                    disk_url = f"/v1/sessions/{session_id}/{service}/{blob_uuid}.{ext}"
                    if token in content:
                        msg["content"] = msg["content"].replace(token, disk_url)

                    # Update explicit audio_ref if it matches
                    if msg.get("audio_ref") == token:
                        msg["audio_url"] = disk_url
                        del msg["audio_ref"]

                    # GC: Delete from Redis immediately
                    await redis.delete(token)
                    logger.info("outbox.blob_promoted", token=token, path=workspace_path)
                except Exception as exc:
                    logger.error("outbox.blob_promotion_failed", token=token, error=str(exc))

        # 3. Append message and update session
        sess.messages = (sess.messages or []) + [msg]
        sess.last_message_at = sess.created_at # fallback
        from isli_core.utils.tokens import count_message_tokens
        sess.token_count = count_message_tokens(sess.messages)

        # 3b. Council room: mirror authoritative thread to the room and all room sessions.
        if sess.room_id:
            room = await db.get(Room, sess.room_id)
            if room:
                now = datetime.now(UTC)
                # Tag assistant replies with the parent user message id for UI grouping.
                last_user_msg = next(
                    (m for m in reversed(room.messages or []) if m.get("role") == "user"),
                    None,
                )
                if last_user_msg and not msg.get("parent_id"):
                    msg["parent_id"] = last_user_msg.get("id")

                room.messages = (room.messages or []) + [msg]
                room.last_activity_at = now

                room_sessions = await db.execute(
                    select(Session).where(
                        Session.room_id == room.id, Session.deleted_at.is_(None)
                    )
                )
                for room_sess in room_sessions.scalars().all():
                    room_sess.messages = list(room.messages)
                    room_sess.last_activity_at = now
                    room_sess.last_message_at = now
                    room_sess.token_count = count_message_tokens(room_sess.messages)

        # 4. Store outbound channel message for audit
        msg_audit = ChannelMessage(
            session_id=session_id,
            sequence_number=len(sess.messages),
            channel=channel or "unknown",
            direction="outbound",
            content=msg.get("content", ""),
            raw_payload={
                "source": "agent_reply_outbox",
                "agent_id": sess.agent_id,
            },
        )
        db.add(msg_audit)

        await db.commit()

        # 5. Emit WebSocket event so the UI updates
        await EventManager.emit("session:updated", {"session_id": session_id})
        if sess.room_id:
            await EventManager.emit("room:updated", {"room_id": sess.room_id})
        logger.info("outbox.session_persist.success", session_id=session_id)

def register_handlers() -> None:
    register_outbox_handler("session:message_persist", handle_session_persist)
