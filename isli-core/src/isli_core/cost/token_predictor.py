"""Estimate token usage before inference, including reasoning overhead."""

from typing import Any

from isli_core.cost.reasoning_detector import ReasoningDetector


class TokenPredictor:
    """Predict input + reasoning + output tokens for a given prompt and model."""

    TOKEN_OVERHEAD = 4  # chars per token rough estimate
    SYSTEM_OVERHEAD = 50  # system prompt + message framing tokens
    DEFAULT_MAX_TOKENS = 1024

    @staticmethod
    def estimate(
        prompt: str,
        model_id: str,
        history_messages: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, int]:
        input_tokens = TokenPredictor._estimate_input(prompt, history_messages)
        reasoning_multiplier = ReasoningDetector.get_multiplier(model_id)
        reasoning_tokens = int(input_tokens * (reasoning_multiplier - 1.0)) if ReasoningDetector.is_reasoning_model(model_id) else 0
        output_tokens = max_tokens or TokenPredictor.DEFAULT_MAX_TOKENS
        return {
            "input_tokens": input_tokens,
            "reasoning_tokens": reasoning_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + reasoning_tokens + output_tokens,
        }

    @staticmethod
    def _estimate_input(prompt: str, history_messages: list[dict[str, Any]] | None = None) -> int:
        text_len = len(prompt)
        if history_messages:
            for msg in history_messages:
                text_len += len(msg.get("content", ""))
        return max(1, text_len // TokenPredictor.TOKEN_OVERHEAD) + TokenPredictor.SYSTEM_OVERHEAD
