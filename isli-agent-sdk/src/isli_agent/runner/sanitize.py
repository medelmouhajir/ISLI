"""Tool-result sanitization before feeding results back to the LLM."""

from typing import Any


def _sanitize_tool_result(result: Any) -> Any:
    """Strip large binary payloads from tool results before they reach the LLM.

    Base64 audio/images can be megabytes; feeding them back into the model
    context causes token explosions and timeouts.  We preserve metadata so
    the LLM still knows the tool succeeded.
    """
    if not isinstance(result, dict):
        return result

    sanitized = dict(result)
    if "audio_b64" in sanitized and isinstance(sanitized["audio_b64"], str):
        audio_len = len(sanitized["audio_b64"])
        sanitized["audio_b64"] = (
            f"<{audio_len} chars of base64 audio omitted — "
            f"use send_message(audio_b64=...) to deliver to user>"
        )
    # Also truncate any other unexpectedly long string fields
    for key, value in sanitized.items():
        if isinstance(value, str) and len(value) > 10_000:
            sanitized[key] = value[:5000] + f"\n... [{len(value)} chars truncated]"
    return sanitized
