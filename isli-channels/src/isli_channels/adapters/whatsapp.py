import asyncio
import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from ..chunking import MessageChunker
from ..idempotency import WebhookIdempotency
from .base import ChannelAdapter, InboundMessage

logger = structlog.get_logger()

# Map Core access-denial detail strings to user-facing WhatsApp replies.
_REJECTION_REPLIES = {
    "closed_mode": "This assistant only accepts messages from its owner.",
    "not_in_whitelist": "You're not on the access list for this assistant.",
    "outside_schedule": (
        "This assistant is currently offline. Please try again during business hours."
    ),
    "consent_required": "Welcome! Please send /start to begin chatting with this agent.",
    "rate_limited": "You've sent too many messages. Please try again later.",
}


def _normalize_jid(jid: str) -> str:
    """Strip domain and device suffix from a WhatsApp JID."""
    return jid.split("@")[0].split(":")[0]


class WhatsAppAdapter(ChannelAdapter):
    def __init__(
        self,
        core_api_url: str,
        webhook_secret: str = "",
        redis_client=None,
        sidecar_url: str = "http://whatsapp-sidecar:3001",
        sidecar_api_token: str = "",
        sidecar_webhook_secret: str = "",
    ):
        self.core_api_url = core_api_url.rstrip("/")
        self.webhook_secret = webhook_secret
        self.redis = redis_client
        self.sidecar_url = sidecar_url.rstrip("/")
        self.sidecar_api_token = sidecar_api_token
        self.sidecar_webhook_secret = sidecar_webhook_secret
        self.idempotency = WebhookIdempotency(redis_client) if redis_client else None

        # Per-agent state (synced from sidecar via webhooks/polling)
        self.qr_codes: dict[str, str | None] = {}
        self.qr_sequences: dict[str, int] = {}
        self.connection_states: dict[str, dict[str, Any]] = {}
        # Preserve original JIDs (including .lid suffix) for accurate replies
        self.user_jids: dict[str, dict[str, str]] = {}

    # --- Lifecycle ---

    async def start(self):
        logger.info("whatsapp.adapter_starting", sidecar_url=self.sidecar_url)
        # Sidecar auto-restarts sessions from its own /auth volume

    async def stop(self):
        logger.info("whatsapp.adapter_stopping")
        # No local tasks to cancel in proxy mode

    def _sidecar_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.sidecar_api_token:
            headers["Authorization"] = f"Bearer {self.sidecar_api_token}"
        return headers

    # --- Session management (Proxy to Sidecar) ---

    async def create_session(self, agent_id: str) -> dict[str, Any]:
        """Idempotent session creation for an agent."""
        # Check sidecar directly — survives adapter restarts
        async with httpx.AsyncClient() as client:
            status_resp = await client.get(
                f"{self.sidecar_url}/session/{agent_id}/status",
                headers=self._sidecar_headers(),
                timeout=10.0,
            )
            if status_resp.status_code == 200:
                sidecar_state = status_resp.json()
                if sidecar_state.get("status") == "open":
                    return {"status": "already_connected", "agent_id": agent_id}

            resp = await client.post(
                f"{self.sidecar_url}/session/{agent_id}/start",
                headers=self._sidecar_headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_session(self, agent_id: str) -> dict[str, Any]:
        """Remove a WhatsApp session for an agent."""
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self.sidecar_url}/session/{agent_id}",
                headers=self._sidecar_headers(),
                timeout=10.0,
            )
            resp.raise_for_status()

            self.qr_codes.pop(agent_id, None)
            self.qr_sequences.pop(agent_id, None)
            self.connection_states.pop(agent_id, None)

            return resp.json()

    def get_qr(self, agent_id: str) -> dict[str, Any]:
        # Query sidecar directly so QR survives adapter restarts
        try:
            import httpx
            with httpx.Client() as client:
                resp = client.get(
                    f"{self.sidecar_url}/session/{agent_id}/qr",
                    headers=self._sidecar_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                qr = data.get("qr")
                return {
                    "qr": qr,
                    "qr_sequence": self.qr_sequences.get(agent_id, 0),
                    "qr_expires_at": (
                        (datetime.now(UTC) + timedelta(seconds=20)).isoformat()
                        if qr
                        else None
                    ),
                }
        except Exception as exc:
            logger.warning("whatsapp.get_qr_failed", agent_id=agent_id, error=str(exc))
            return {
                "qr": self.qr_codes.get(agent_id),
                "qr_sequence": self.qr_sequences.get(agent_id, 0),
                "qr_expires_at": (
                    (datetime.now(UTC) + timedelta(seconds=20)).isoformat()
                    if self.qr_codes.get(agent_id)
                    else None
                ),
            }

    def get_status(self, agent_id: str) -> dict[str, Any]:
        # Query sidecar directly so status survives adapter restarts
        try:
            import httpx
            with httpx.Client() as client:
                resp = client.get(
                    f"{self.sidecar_url}/session/{agent_id}/status",
                    headers=self._sidecar_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "agent_id": agent_id,
                    "status": data.get("status", "disconnected"),
                    "is_new_login": data.get("is_new_login", False),
                    "last_disconnect_reason": data.get("last_disconnect_reason"),
                }
        except Exception as exc:
            logger.warning("whatsapp.get_status_failed", agent_id=agent_id, error=str(exc))
            state = self.connection_states.get(agent_id, {})
            return {
                "agent_id": agent_id,
                "status": state.get("status", "disconnected"),
                "is_new_login": state.get("is_new_login", False),
                "last_disconnect_reason": state.get("last_disconnect_reason"),
            }

    def list_sessions(self) -> list[dict[str, Any]]:
        return [
            {
                "agent_id": agent_id,
                "status": state.get("status", "disconnected"),
                "is_new_login": state.get("is_new_login", False),
            }
            for agent_id, state in self.connection_states.items()
        ]

    # --- Inbound Webhook Handling ---

    async def handle_webhook(self, agent_id: str, payload: dict[str, Any]):
        """Handle events from the Node.js sidecar."""
        if self.idempotency:
            try:
                if await self.idempotency.is_duplicate("whatsapp", payload):
                    logger.info("whatsapp.duplicate_webhook_ignored", agent_id=agent_id)
                    return
            except Exception as exc:
                logger.warning("whatsapp.idempotency_check_failed", error=str(exc))

        event_type = payload.get("type")
        data = payload.get("payload")

        logger.debug("whatsapp.webhook_received", agent_id=agent_id, type=event_type)

        if event_type == "connection.update":
            qr = data.get("qr")
            connection = data.get("connection")

            if qr:
                self.qr_codes[agent_id] = qr
                self.qr_sequences[agent_id] = self.qr_sequences.get(agent_id, 0) + 1

            if connection:
                state = self.connection_states.setdefault(agent_id, {})
                state["status"] = connection
                if connection == "open":
                    self.qr_codes[agent_id] = None
                elif connection == "close":
                    state["last_disconnect_reason"] = data.get("lastDisconnect", {}).get("error")

        elif event_type == "message":
            await self._handle_inbound_message(agent_id, data)

    async def _handle_inbound_message(self, agent_id: str, data: dict[str, Any]):
        key = data.get("key", {})
        remote_jid = key.get("remoteJid", "")
        message = data.get("message", {})

        # Extract text
        text = message.get("conversation") or message.get("extendedTextMessage", {}).get("text")
        msg_id = key.get("id", "")

        # Extract attachments
        attachments: list[dict[str, Any]] = []
        attachment_types = {
            "imageMessage": "image",
            "videoMessage": "video",
            "audioMessage": "audio",
            "documentMessage": "document",
        }
        for msg_key, att_type in attachment_types.items():
            att = message.get(msg_key)
            if att:
                attachments.append({
                    "type": att_type,
                    "mimetype": att.get("mimetype"),
                    "caption": att.get("caption"),
                    "filename": att.get("fileName"),
                    "size": att.get("fileLength"),
                })

        if not remote_jid or (not text and not attachments):
            return

        phone_number = _normalize_jid(remote_jid)

        # Preserve the original JID (e.g. xxx@lid) so replies go to the correct address
        self.user_jids.setdefault(agent_id, {})[phone_number] = remote_jid

        inbound = InboundMessage(
            channel="whatsapp",
            channel_user_id=phone_number,
            text=text or "",
            attachments=attachments,
            metadata={
                "message_id": msg_id,
                "remote_jid": remote_jid,
            },
        )

        # Check for pending /new lock
        if (
            not inbound.text.startswith("/")
            and await self._is_new_session_pending(agent_id, phone_number)
        ):
            await self.send_message(
                phone_number,
                "Setting up new session, please wait a moment before sending your next message.",
                agent_id=agent_id,
            )
            return

        # Detect slash commands
        if inbound.text.startswith("/"):
            await self._handle_command(inbound, agent_id, phone_number)
            return

        # Normal message flow
        session_id = await self._get_active_session_id(agent_id, phone_number)
        normalized = {
            "text": inbound.text,
            "user_id": phone_number,
            "dedup_id": inbound.metadata.get("message_id"),
            "session_id": session_id,
            "agent_id": agent_id,
            "attachments": [
                att.model_dump() if hasattr(att, "model_dump") else att
                for att in inbound.attachments
            ],
        }

        try:
            await self._forward_to_core("whatsapp", "webhook", normalized)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in (403, 429):
                detail = ""
                off_hours_reply = ""
                try:
                    body = exc.response.json()
                    raw_detail = body.get("detail", "")
                    if isinstance(raw_detail, dict):
                        detail = raw_detail.get("reason", "")
                        off_hours_reply = raw_detail.get("off_hours_reply", "")
                    else:
                        detail = str(raw_detail)
                except Exception:
                    pass
                reply = _REJECTION_REPLIES.get(
                    detail,
                    _REJECTION_REPLIES["consent_required"],
                )
                if detail == "outside_schedule" and off_hours_reply:
                    reply = off_hours_reply
                logger.info(
                    "whatsapp.access_denied_auto_reply",
                    agent_id=agent_id,
                    user_id=phone_number,
                    reason=detail,
                    status_code=status_code,
                )
                await self.send_message(phone_number, reply, agent_id=agent_id)
                return
            logger.error(
                "whatsapp.forward_to_core_failed",
                agent_id=agent_id,
                user_id=phone_number,
                status_code=status_code,
                error=str(exc),
            )
            raise

    async def _handle_command(
        self, inbound: InboundMessage, agent_id: str, user_id: str
    ):
        text = inbound.text or ""
        raw_cmd = text.split()[0]
        command = raw_cmd.lstrip("/").lower()
        args = text[len(raw_cmd) :].strip()

        session_id = await self._get_active_session_id(agent_id, user_id)

        if command == "new":
            await self._set_new_session_pending(agent_id, user_id)

        payload = {
            "user_id": user_id,
            "agent_id": agent_id,
            "session_id": session_id,
            "command": command,
            "args": args,
            "text": text,
        }

        try:
            data = await self._forward_to_core("whatsapp", "commands", payload)
        except Exception as exc:
            logger.error("whatsapp.command_forward_failed", command=command, error=str(exc))
            await self.send_message(
                user_id,
                "Sorry, I couldn't process that command right now. Please try again.",
                agent_id=agent_id,
            )
            await self._clear_new_session_pending(agent_id, user_id)
            return

        response_text = data.get("response_text", "Command processed.")
        await self.send_message(user_id, response_text, agent_id=agent_id)

        if command == "new":
            new_session_id = data.get("new_session_id")
            if new_session_id:
                await self._set_active_session_id(agent_id, user_id, new_session_id)
            await self._clear_new_session_pending(agent_id, user_id)

    async def _forward_to_core(self, channel: str, endpoint: str, payload: dict) -> dict:
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if self.webhook_secret:
            signature = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = signature

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.core_api_url}/v1/channels/{channel}/{endpoint}",
                content=body,
                headers=headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()

    # --- Redis session tracking ---

    def _session_key(self, agent_id: str, user_id: str) -> str:
        return f"active_session:whatsapp:{agent_id}:{user_id}"

    def _pending_key(self, agent_id: str, user_id: str) -> str:
        return f"new_session_pending:whatsapp:{agent_id}:{user_id}"

    async def _get_active_session_id(self, agent_id: str, user_id: str) -> str:
        if self.redis:
            try:
                stored = await self.redis.get(self._session_key(agent_id, user_id))
                if stored:
                    return stored
            except Exception as exc:
                logger.warning("whatsapp.redis_session_read_failed", error=str(exc))
        return f"sess_wa_{agent_id}_{user_id}"

    async def _set_active_session_id(self, agent_id: str, user_id: str, session_id: str):
        if self.redis:
            try:
                await self.redis.setex(self._session_key(agent_id, user_id), 86400 * 30, session_id)
            except Exception as exc:
                logger.warning("whatsapp.redis_session_write_failed", error=str(exc))

    async def _is_new_session_pending(self, agent_id: str, user_id: str) -> bool:
        if not self.redis:
            return False
        try:
            return await self.redis.exists(self._pending_key(agent_id, user_id)) > 0
        except Exception as exc:
            logger.warning("whatsapp.redis_pending_check_failed", error=str(exc))
            return False

    async def _set_new_session_pending(self, agent_id: str, user_id: str):
        if self.redis:
            try:
                await self.redis.setex(self._pending_key(agent_id, user_id), 10, "1")
            except Exception as exc:
                logger.warning("whatsapp.redis_pending_set_failed", error=str(exc))

    async def _clear_new_session_pending(self, agent_id: str, user_id: str):
        if self.redis:
            try:
                await self.redis.delete(self._pending_key(agent_id, user_id))
            except Exception as exc:
                logger.warning("whatsapp.redis_pending_clear_failed", error=str(exc))

    # --- ChannelAdapter interface ---

    async def send_message(self, channel_user_id: str, text: str, **kwargs) -> bool:
        agent_id = kwargs.get("agent_id")
        audio_b64 = kwargs.get("audio_b64")
        if not agent_id:
            logger.error("whatsapp.send_missing_agent_id", channel_user_id=channel_user_id)
            return False

        # Use the original JID if we have it (preserves .lid vs .s.whatsapp.net)
        agent_jids = self.user_jids.get(agent_id, {})
        jid = agent_jids.get(channel_user_id, f"{channel_user_id}@s.whatsapp.net")

        # --- Send text chunks first ---
        chunks = MessageChunker.chunk(text, "whatsapp")
        all_ok = True

        for chunk in chunks:
            last_exc = None
            success = False
            for attempt in range(4):
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"{self.sidecar_url}/send",
                            headers=self._sidecar_headers(),
                            json={"agentId": agent_id, "jid": jid, "text": chunk},
                            timeout=15.0,
                        )
                        resp.raise_for_status()
                        success = resp.json().get("success", False)
                        if success:
                            break
                except Exception as exc:
                    last_exc = exc
                    if attempt < 3:
                        delay = min(1.0 * (2 ** attempt), 10.0)
                        await asyncio.sleep(delay)

            if not success:
                all_ok = False
                logger.error(
                    "whatsapp.send_failed_final",
                    agent_id=agent_id,
                    jid=jid,
                    error=str(last_exc),
                )

        # --- Send file attachments ---
        attachments = kwargs.get("attachments") or []
        if attachments and all_ok:
            for att in attachments:
                try:
                    await self._send_attachment(jid, att, agent_id)
                except Exception as exc:
                    logger.warning(
                        "whatsapp.attachment_send_failed",
                        agent_id=agent_id,
                        jid=jid,
                        filename=att.get("filename"),
                        error=str(exc),
                    )

        # --- Send audio as PTT if present ---
        if audio_b64 and all_ok:
            last_exc = None
            success = False
            for attempt in range(4):
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"{self.sidecar_url}/send",
                            headers=self._sidecar_headers(),
                            json={
                                "type": "audio",
                                "agentId": agent_id,
                                "jid": jid,
                                "audio_b64": audio_b64,
                                "caption": text[:1024] if len(text) <= 1024 else None,
                            },
                            timeout=30.0,
                        )
                        resp.raise_for_status()
                        success = resp.json().get("success", False)
                        if success:
                            logger.info(
                                "whatsapp.audio_sent",
                                agent_id=agent_id,
                                jid=jid,
                            )
                            break
                except Exception as exc:
                    last_exc = exc
                    if attempt < 3:
                        delay = min(1.0 * (2 ** attempt), 10.0)
                        await asyncio.sleep(delay)

            if not success:
                logger.error(
                    "whatsapp.audio_send_failed",
                    agent_id=agent_id,
                    jid=jid,
                    error=str(last_exc),
                )
                # Audio failure is non-fatal; text was already delivered

        return all_ok

    async def _send_attachment(
        self,
        jid: str,
        attachment: dict[str, Any],
        agent_id: str,
    ) -> None:
        """Fetch a file from Core's signed download URL and send it via the WhatsApp sidecar."""
        url = attachment.get("download_url")
        if not url:
            logger.warning(
                "whatsapp.attachment_missing_url",
                filename=attachment.get("filename"),
            )
            return

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            file_bytes = resp.content

        media_type = attachment.get("media_type", "document")
        # WhatsApp sidecar supports image, video, document, audio. Voice/PTT uses a separate path.
        sidecar_type = (
            media_type if media_type in {"image", "video", "document", "audio"} else "document"
        )
        media_b64 = base64.b64encode(file_bytes).decode("utf-8")
        filename = attachment.get("filename") or "file"
        caption = (attachment.get("caption") or "")[:1024]

        last_exc: Exception | None = None
        success = False
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        f"{self.sidecar_url}/send",
                        headers=self._sidecar_headers(),
                        json={
                            "type": sidecar_type,
                            "agentId": agent_id,
                            "jid": jid,
                            "media_b64": media_b64,
                            "mimetype": attachment.get("mime_type"),
                            "filename": filename,
                            "caption": caption or None,
                        },
                    )
                    resp.raise_for_status()
                    success = resp.json().get("success", False)
                    if success:
                        logger.info(
                            "whatsapp.attachment_sent",
                            agent_id=agent_id,
                            jid=jid,
                            media_type=sidecar_type,
                            filename=filename,
                            size=len(file_bytes),
                        )
                        break
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    delay = min(1.0 * (2 ** attempt), 10.0)
                    await asyncio.sleep(delay)

        if not success:
            logger.error(
                "whatsapp.attachment_send_exhausted",
                agent_id=agent_id,
                jid=jid,
                filename=filename,
                error=str(last_exc),
            )
            raise last_exc or RuntimeError("Failed to send WhatsApp attachment")

    async def send_typing(self, channel_user_id: str, **kwargs):
        # Baileys support for typing is optional, skipped for MVP sidecar
        pass

    def parse_update(self, raw_update: dict) -> InboundMessage | None:
        # Not used directly in proxy mode, handle_webhook does the parsing
        return None

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.sidecar_url}/health",
                    headers=self._sidecar_headers(),
                    timeout=3.0,
                )
                return resp.status_code == 200 and resp.json().get("status") == "ok"
        except Exception:
            return False
