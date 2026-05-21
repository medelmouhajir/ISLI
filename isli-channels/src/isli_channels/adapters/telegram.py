import hashlib
import hmac
import httpx
import json
import structlog
from typing import Optional, Any
from telegram import Bot, BotCommand, Update

from .base import ChannelAdapter, InboundMessage

logger = structlog.get_logger()

# Commands registered with Telegram Bot API via setMyCommands.
# The "command" field must be lowercase, 1–32 chars, no leading slash.
ISLI_COMMANDS = [
    BotCommand("new", "Start a fresh session"),
    BotCommand("compact", "Trigger journal compaction now"),
    BotCommand("context", "Show current session journal"),
    BotCommand("status", "Show agent and session stats"),
    BotCommand("remember", "Pin a fact to memory"),
    BotCommand("forget", "Search and propose a memory to delete"),
    BotCommand("confirm_forget", "Confirm deletion from last /forget"),
    BotCommand("memories", "List pinned memories"),
    BotCommand("retry", "Retry the last unanswered message"),
    BotCommand("cancel", "Cancel the current in-progress task"),
    BotCommand("help", "Show available commands"),
]


class TelegramAdapter(ChannelAdapter):
    def __init__(self, token: str, core_api_url: str, webhook_secret: str = "", redis_client=None):
        self.token = token
        self.core_api_url = core_api_url.rstrip("/")
        self.webhook_secret = webhook_secret
        self.bot = Bot(token=token)
        self.redis = redis_client
        self._commands_registered_for_tokens: set[str] = set()

    async def start(self):
        logger.info("telegram.adapter_starting")
        # Validation
        try:
            me = await self.bot.get_me()
            logger.info("telegram.bot_authenticated", bot_name=me.username)
        except Exception as e:
            logger.error("telegram.auth_failed", error=str(e))
            return

        # Register command menu with Telegram (persists until changed)
        try:
            await self.bot.set_my_commands(ISLI_COMMANDS)
            self._commands_registered_for_tokens.add(self.token)
            logger.info(
                "telegram.commands_registered",
                count=len(ISLI_COMMANDS),
                bot_name=me.username,
            )
        except Exception as exc:
            logger.warning("telegram.set_commands_failed", error=str(exc))

    async def stop(self):
        logger.info("telegram.adapter_stopping")

    async def _resolve_token(self, agent_id: str | None) -> str:
        if not agent_id:
            return self.token
        token = self.token
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.core_api_url}/v1/agents/{agent_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    cfg = data.get("config") or {}
                    per_agent = cfg.get("telegram_bot_token")
                    if per_agent:
                        token = str(per_agent)
        except Exception as exc:
            logger.warning("telegram.resolve_token_failed", agent_id=agent_id, error=str(exc))

        # Register commands for per-agent tokens the first time they are resolved
        if token != self.token and token not in self._commands_registered_for_tokens:
            try:
                bot = Bot(token=token)
                await bot.set_my_commands(ISLI_COMMANDS)
                self._commands_registered_for_tokens.add(token)
                logger.info(
                    "telegram.commands_registered_per_agent",
                    agent_id=agent_id,
                    count=len(ISLI_COMMANDS),
                )
            except Exception as exc:
                logger.warning(
                    "telegram.set_commands_per_agent_failed",
                    agent_id=agent_id,
                    error=str(exc),
                )

        return token

    # --- Redis session tracking ---

    def _session_key(self, agent_id: str, user_id: str) -> str:
        return f"active_session:telegram:{agent_id}:{user_id}"

    def _pending_key(self, agent_id: str, user_id: str) -> str:
        return f"new_session_pending:telegram:{agent_id}:{user_id}"

    async def _get_active_session_id(self, agent_id: str, user_id: str) -> str:
        if self.redis:
            try:
                stored = await self.redis.get(self._session_key(agent_id, user_id))
                if stored:
                    return stored
            except Exception as exc:
                logger.warning("telegram.redis_session_read_failed", error=str(exc))
        return f"sess_tg_{agent_id}_{user_id}"

    async def _set_active_session_id(self, agent_id: str, user_id: str, session_id: str):
        if self.redis:
            try:
                await self.redis.set(self._session_key(agent_id, user_id), session_id)
            except Exception as exc:
                logger.warning("telegram.redis_session_write_failed", error=str(exc))

    async def _is_new_session_pending(self, agent_id: str, user_id: str) -> bool:
        if not self.redis:
            return False
        try:
            return await self.redis.exists(self._pending_key(agent_id, user_id)) > 0
        except Exception as exc:
            logger.warning("telegram.redis_pending_check_failed", error=str(exc))
            return False

    async def _set_new_session_pending(self, agent_id: str, user_id: str):
        if self.redis:
            try:
                await self.redis.setex(self._pending_key(agent_id, user_id), 10, "1")
            except Exception as exc:
                logger.warning("telegram.redis_pending_set_failed", error=str(exc))

    async def _clear_new_session_pending(self, agent_id: str, user_id: str):
        if self.redis:
            try:
                await self.redis.delete(self._pending_key(agent_id, user_id))
            except Exception as exc:
                logger.warning("telegram.redis_pending_clear_failed", error=str(exc))

    # --- Sending ---

    async def send_message(self, channel_user_id: str, text: str, **kwargs) -> bool:
        import asyncio
        agent_id = kwargs.get("agent_id")
        token = await self._resolve_token(agent_id)
        last_exc = None
        for attempt in range(4):  # initial + 3 retries
            try:
                bot = Bot(token=token) if token != self.token else self.bot
                await bot.send_message(chat_id=channel_user_id, text=text)
                return True
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    delay = min(1.0 * (2 ** attempt), 10.0)
                    await asyncio.sleep(delay)
        logger.error("telegram.send_failed", chat_id=channel_user_id, error=str(last_exc), agent_id=agent_id)
        return False

    async def send_typing(self, channel_user_id: str, **kwargs):
        agent_id = kwargs.get("agent_id")
        token = await self._resolve_token(agent_id)
        try:
            bot = Bot(token=token) if token != self.token else self.bot
            await bot.send_chat_action(chat_id=channel_user_id, action="typing")
        except Exception as exc:
            logger.error("telegram.typing_failed", chat_id=channel_user_id, error=str(exc), agent_id=agent_id)

    def parse_update(self, raw_update: dict) -> Optional[InboundMessage]:
        try:
            update = Update.de_json(raw_update, self.bot)
            if not update or not update.message:
                return None

            message = update.message
            return InboundMessage(
                channel="telegram",
                channel_user_id=str(message.chat_id),
                text=message.text or "",
                raw_payload=raw_update,
                metadata={
                    "message_id": message.message_id,
                    "username": message.from_user.username if message.from_user else None
                }
            )
        except Exception as e:
            logger.error("telegram.parse_failed", error=str(e))
            return None

    async def health_check(self) -> bool:
        try:
            await self.bot.get_me()
            return True
        except Exception:
            return False

    # --- Webhook handling ---

    async def handle_webhook(self, raw_update: dict, agent_id: str):
        """Handle incoming webhook and forward to Core."""
        inbound = self.parse_update(raw_update)
        if not inbound:
            return {"status": "ignored"}

        user_id = inbound.channel_user_id

        # Check for pending /new lock on normal messages
        if (
            not inbound.text.startswith("/")
            and await self._is_new_session_pending(agent_id, user_id)
        ):
            await self.send_message(
                user_id,
                "Setting up new session, please wait a moment before sending your next message.",
                agent_id=agent_id,
            )
            return {"status": "new_session_pending"}

        # Detect slash commands
        if inbound.text.startswith("/"):
            return await self._handle_command(inbound, agent_id, user_id, raw_update)

        # Normal message flow
        session_id = await self._get_active_session_id(agent_id, user_id)
        normalized = {
            "text": inbound.text,
            "user_id": user_id,
            "dedup_id": inbound.metadata.get("message_id"),
            "session_id": session_id,
            "agent_id": agent_id
        }

        body = json.dumps(normalized, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if self.webhook_secret:
            signature = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = signature

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.core_api_url}/v1/channels/telegram/webhook",
                content=body,
                headers=headers
            )
            resp.raise_for_status()
            logger.info("telegram.forwarded_to_core", task_id=resp.json().get("task_id"))
            return resp.json()

    async def _handle_command(
        self, inbound: InboundMessage, agent_id: str, user_id: str, raw_update: dict
    ):
        """Parse and forward a slash command to Core's commands endpoint."""
        text = inbound.text or ""
        # Strip @botname suffix if present (group chat syntax)
        raw_cmd = text.split()[0].split("@")[0]
        command = raw_cmd.lstrip("/").lower()
        args = text[len(raw_cmd):].strip()

        session_id = await self._get_active_session_id(agent_id, user_id)

        # Set pending lock before /new to prevent race conditions
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

        body = json.dumps(payload, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if self.webhook_secret:
            signature = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = signature

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.core_api_url}/v1/channels/telegram/commands",
                    content=body,
                    headers=headers,
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("telegram.command_forward_failed", command=command, error=str(exc))
            await self.send_message(
                user_id,
                "Sorry, I couldn't process that command right now. Please try again.",
                agent_id=agent_id
            )
            await self._clear_new_session_pending(agent_id, user_id)
            return {"status": "command_error"}

        response_text = data.get("response_text", "Command processed.")
        await self.send_message(user_id, response_text, agent_id=agent_id)

        # If /new created a new session, update Redis and clear the lock
        if command == "new":
            new_session_id = data.get("new_session_id")
            if new_session_id:
                await self._set_active_session_id(agent_id, user_id, new_session_id)
            await self._clear_new_session_pending(agent_id, user_id)

        logger.info("telegram.command_handled", command=command, agent_id=agent_id, user_id=user_id)
        return {"status": "command_handled"}
