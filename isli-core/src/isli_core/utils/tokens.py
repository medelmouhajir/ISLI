"""Token counting utilities.

Uses ``tiktoken`` with ``cl100k_base`` (GPT-4) for accurate counts.
This is exact for OpenAI models and approximate for Qwen/Gemini.
Sufficient for budget alerts and routing thresholds.

If ``tiktoken`` is not available, falls back to a crude character-count
heuristic with a prominent log warning.
"""

import structlog

logger = structlog.get_logger()

HAS_TIKTOKEN = False
_enc = None

try:
    import tiktoken

    _enc = tiktoken.encoding_for_model("gpt-4")
    HAS_TIKTOKEN = True
    logger.info("tokens.tiktoken_loaded", encoding="cl100k_base")
except Exception:
    logger.warning(
        "tokens.tiktoken_unavailable",
        fallback="len(str(text)) // 4",
        reason="tiktoken not installed or binary wheel missing",
    )


def count_tokens(text: str) -> int:
    """Return the approximate token count for *text*.

    Uses tiktoken when available; otherwise falls back to a character-count
    heuristic that is accurate only for ASCII prose.
    """
    if HAS_TIKTOKEN and _enc is not None:
        return len(_enc.encode(text))
    return len(str(text)) // 4


def count_message_tokens(messages: list[dict]) -> int:
    """Return the approximate token count for a list of chat messages."""
    flattened = "\n".join(
        f"{m.get('role', '')}: {m.get('content', '')}" for m in messages
    )
    return count_tokens(flattened)
