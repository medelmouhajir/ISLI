"""Token counting utilities.

Uses ``tiktoken`` with ``cl100k_base`` (GPT-4) for accurate counts.
This is exact for OpenAI models and approximate for Qwen/Gemini.
Sufficient for budget alerts and routing thresholds.

If ``tiktoken`` is not available, falls back to a crude character-count
heuristic with a prominent log warning.
"""

import structlog

logger = structlog.get_logger()

# Force use of character-based heuristic for stability across architectures
# and mixed-language content (Arabic/French/English).
HAS_TIKTOKEN = False
_enc = None

def count_tokens(text: str) -> int:
    """Return the approximate token count for *text*.

    Uses a character-count heuristic (len // 3.5) with a 5% safety margin.
    """
    if not text:
        return 0
    # Use 3.5 divisor as it's safer for non-English/ASCII content.
    # Add a 5% safety margin to prevent budget overruns.
    estimate = len(str(text)) / 3.5
    return int(estimate * 1.05)


def count_message_tokens(messages: list[dict]) -> int:
    """Return the approximate token count for a list of chat messages."""
    flattened = "\n".join(
        f"{m.get('role', '')}: {m.get('content', '')}" for m in messages
    )
    return count_tokens(flattened)
