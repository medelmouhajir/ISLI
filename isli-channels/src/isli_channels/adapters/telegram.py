import httpx
import structlog
from typing import Optional, Any
from telegram import Bot, Update

from .base import ChannelAdapter, InboundMessage

logger = structlog.get_logger()

class TelegramAdapter(ChannelAdapter):
    def __init__(self, token: str, core_api_url: str):
        self.token = token
        self.core_api_url = core_api_url.rstrip("/")
        self.bot = Bot(token=token)

    async def start(self):
        logger.info("telegram.adapter_starting")
        # Validation
        try:
            me = await self.bot.get_me()
            logger.info("telegram.bot_authenticated", bot_name=me.username)
        except Exception as e:
            logger.error("telegram.auth_failed", error=str(e))

    async def stop(self):
        logger.info("telegram.adapter_stopping")

    async def send_message(self, channel_user_id: str, text: str, **kwargs) -> bool:
        try:
            await self.bot.send_message(chat_id=channel_user_id, text=text, **kwargs)
            return True
        except Exception as exc:
            logger.error("telegram.send_failed", chat_id=channel_user_id, error=str(exc))
            return False

    async def send_typing(self, channel_user_id: str):
        try:
            await self.bot.send_chat_action(chat_id=channel_user_id, action="typing")
        except Exception as exc:
            logger.error("telegram.typing_failed", chat_id=channel_user_id, error=str(exc))

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

    async def handle_webhook(self, raw_update: dict, agent_id: str):
        """Handle incoming webhook and forward to Core."""
        inbound = self.parse_update(raw_update)
        if not inbound:
            return {"status": "ignored"}
            
        # Normalize for isli-core/routers/channels.py
        normalized = {
            "text": inbound.text,
            "user_id": inbound.channel_user_id,
            "dedup_id": inbound.metadata.get("message_id"),
            "session_id": f"sess_tg_{inbound.channel_user_id}",
            "agent_id": agent_id
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.core_api_url}/v1/channels/telegram/webhook", 
                json=normalized
            )
            resp.raise_for_status()
            logger.info("telegram.forwarded_to_core", task_id=resp.json().get("task_id"))
            return resp.json()
