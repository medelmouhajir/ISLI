"""Model-provider string normalization and Ollama Cloud constants."""

import structlog

logger = structlog.get_logger()

# Ollama Cloud exposes an OpenAI-compatible endpoint at /v1/chat/completions.
# LiteLLM's native 'ollama/...' adapter hits /api/chat and can loop on tool
# results (no final text answer). The OpenAI-compatible adapter synthesizes
# final answers correctly, so we default to it for Ollama Cloud agents.
OLLAMA_OPENAI_BASE = "https://ollama.com/v1"
OLLAMA_NATIVE_OPT_OUT_KEY = "use_native_ollama_endpoint"


def _normalize_provider(provider: str) -> str:
    """
    Normalizes the model provider string to the format expected by LiteLLM.
    e.g., 'google' -> 'gemini', 'vertex' -> 'vertex_ai'
    """
    mapping = {
        "google": "gemini",
        "nvidia": "nvidia_nim",
        "vertex": "vertex_ai",
    }
    normalized = mapping.get(provider.lower(), provider)
    if normalized != provider:
        logger.debug("runner.provider_normalized", original=provider, normalized=normalized)
    return normalized
