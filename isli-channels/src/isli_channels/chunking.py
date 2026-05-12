import structlog
from typing import Callable

logger = structlog.get_logger()

PLATFORM_LIMITS = {
    "telegram": {"max_length": 4096, "split_on": "\n"},
    "whatsapp": {"max_length": 1600, "split_on": "\n\n"},
    "email": {"max_length": 100_000, "split_on": "\n\n"},
    "web": {"max_length": 50_000, "split_on": "\n\n"},
    "sms": {"max_length": 160, "split_on": " "},
}


class MessageChunker:
    """Per-platform message size enforcement with intelligent chunking."""

    @staticmethod
    def chunk(text: str, channel: str) -> list[str]:
        config = PLATFORM_LIMITS.get(channel, PLATFORM_LIMITS["web"])
        max_len = config["max_length"]
        split_on = config["split_on"]

        if len(text) <= max_len:
            return [text]

        chunks = []
        current = ""
        parts = text.split(split_on)

        for part in parts:
            candidate = current + split_on + part if current else part
            if len(candidate) <= max_len:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # If single part is too long, hard-split it
                if len(part) > max_len:
                    for i in range(0, len(part), max_len):
                        chunks.append(part[i : i + max_len])
                    current = ""
                else:
                    current = part

        if current:
            chunks.append(current)

        logger.info("chunking.split", channel=channel, original_len=len(text), chunks=len(chunks))
        return chunks

    @staticmethod
    async def send_chunked(
        channel: str,
        recipient: str,
        text: str,
        sender: Callable[[str, str, str], None],
    ) -> list[str]:
        chunks = MessageChunker.chunk(text, channel)
        sent_ids = []
        for idx, chunk in enumerate(chunks):
            try:
                await sender(channel, recipient, chunk)
                sent_ids.append(f"{recipient}:{idx}")
            except Exception:
                logger.exception("chunking.send_failed", channel=channel, recipient=recipient, chunk_idx=idx)
                raise
        return sent_ids
