"""Detect reasoning models that produce separate reasoning tokens."""

REASONING_MODELS = {
    "o1",
    "o3",
    "o1-preview",
    "o1-mini",
    "o3-mini",
    "claude-opus-4-7-thinking",
    "claude-sonnet-4-6-thinking",
    "deepseek-r1",
    "gemini-2.0-flash-thinking",
}

REASONING_MULTIPLIERS = {
    "o1": 3.0,
    "o3": 3.0,
    "o1-preview": 2.5,
    "o1-mini": 2.0,
    "o3-mini": 2.0,
    "claude-opus-4-7-thinking": 2.5,
    "claude-sonnet-4-6-thinking": 2.0,
    "deepseek-r1": 2.0,
    "gemini-2.0-flash-thinking": 1.5,
}


class ReasoningDetector:
    """Identify models that use chain-of-thought / reasoning tokens."""

    @staticmethod
    def is_reasoning_model(model_id: str) -> bool:
        return model_id.lower() in REASONING_MODELS

    @staticmethod
    def get_multiplier(model_id: str) -> float:
        return REASONING_MULTIPLIERS.get(model_id.lower(), 1.0)
