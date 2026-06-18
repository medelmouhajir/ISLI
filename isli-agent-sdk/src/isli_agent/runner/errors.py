"""Model error classification for the agent runner."""

import enum

from litellm import (
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout as LiteLLMTimeoutError,
)


class ModelErrorCategory(enum.Enum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    OVERLOADED = "overloaded"
    BAD_REQUEST = "bad_request"
    UNKNOWN = "unknown"


def _classify_model_error(exc: Exception) -> tuple[ModelErrorCategory, str]:
    """Classify a LiteLLM exception. Primary: isinstance. Fallback: string inspection."""
    error_str = str(exc).lower()

    if isinstance(exc, AuthenticationError):
        return (ModelErrorCategory.AUTH, "The AI model's API key is invalid or has expired. Please contact the administrator.")

    if isinstance(exc, RateLimitError):
        return (ModelErrorCategory.RATE_LIMIT, "The AI model is currently rate-limited. Please try again in a moment.")

    if isinstance(exc, LiteLLMTimeoutError):
        return (ModelErrorCategory.TIMEOUT, "Connection to the AI model timed out. Please try again shortly.")

    if isinstance(exc, ServiceUnavailableError):
        return (ModelErrorCategory.OVERLOADED, "The AI model is temporarily overloaded. Please try again in a moment.")

    if isinstance(exc, BadRequestError):
        if "api key" in error_str:
            return (ModelErrorCategory.AUTH, "The AI model's API key is invalid or has expired. Please contact the administrator.")
        return (ModelErrorCategory.BAD_REQUEST, "The request could not be processed by the AI model. It may be too long or contain unsupported content.")

    # String fallback for provider-specific errors LiteLLM doesn't wrap
    if any(k in error_str for k in ("api key not valid", "unauthorized", "auth", "invalid token", "permission denied")):
        return (ModelErrorCategory.AUTH, "The AI model's API key is invalid or has expired. Please contact the administrator.")
    if "rate limit" in error_str or "too many requests" in error_str:
        return (ModelErrorCategory.RATE_LIMIT, "The AI model is currently rate-limited. Please try again in a moment.")
    if "api connection error" in error_str or "timeout" in error_str:
        return (ModelErrorCategory.TIMEOUT, "Connection to the AI model timed out. Please try again shortly.")
    if "overloaded" in error_str or "temporarily unavailable" in error_str:
        return (ModelErrorCategory.OVERLOADED, "The AI model is temporarily overloaded. Please try again in a moment.")

    return (ModelErrorCategory.UNKNOWN, "An unexpected error occurred while talking to the AI model. The administrator has been notified.")
