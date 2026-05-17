from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel


class InboundMessage(BaseModel):
    channel: str
    channel_user_id: str
    text: str
    attachments: list[dict[str, Any]] = []
    raw_payload: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class ChannelAdapter(ABC):
    @abstractmethod
    async def start(self):
        """Initialize the adapter (e.g., start polling or register webhooks)."""
        pass

    @abstractmethod
    async def stop(self):
        """Gracefully shut down the adapter."""
        pass

    @abstractmethod
    async def send_message(self, channel_user_id: str, text: str, **kwargs) -> bool:
        """Send a message back to the user on this channel."""
        pass

    @abstractmethod
    async def send_typing(self, channel_user_id: str):
        """Show a typing indicator to the user."""
        pass

    @abstractmethod
    def parse_update(self, raw_update: dict) -> Optional[InboundMessage]:
        """Parse a platform-specific update into a normalized InboundMessage."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the connection to the platform's API."""
        pass
