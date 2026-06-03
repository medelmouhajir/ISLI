"""Rate-card calculator with per-agent monthly projections."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ModelRate:
    model_id: str
    provider: str
    input_per_1k: float  # USD per 1K input tokens
    output_per_1k: float  # USD per 1K output tokens
    reasoning_per_1k: float = 0.0  # USD per 1K reasoning tokens
    is_local: bool = False


# ISLI rate card (2026-05-11)
RATE_CARD: dict[str, ModelRate] = {
    "claude-sonnet-4-6": ModelRate("claude-sonnet-4-6", "anthropic", 3.00, 15.00),
    "claude-haiku-4-5": ModelRate("claude-haiku-4-5", "anthropic", 0.80, 4.00),
    "gpt-4o": ModelRate("gpt-4o", "openai", 2.50, 10.00),
    "gpt-4o-mini": ModelRate("gpt-4o-mini", "openai", 0.15, 0.60),
    "o1": ModelRate("o1", "openai", 5.00, 15.00, reasoning_per_1k=10.00),
    "o3": ModelRate("o3", "openai", 5.00, 15.00, reasoning_per_1k=10.00),
    "claude-opus-4-7-thinking": ModelRate("claude-opus-4-7-thinking", "anthropic", 7.50, 30.00, reasoning_per_1k=15.00),
    "qwen3:1.7b": ModelRate("qwen3:1.7b", "ollama", 0.0, 0.0, is_local=True),
    "qwen3:0.6b": ModelRate("qwen3:0.6b", "ollama", 0.0, 0.0, is_local=True),
    # Gemini 2.5 (2026-05-31)
    "gemini-2.5-pro": ModelRate("gemini-2.5-pro", "google", 0.00125, 0.01),
    "gemini-2.5-flash": ModelRate("gemini-2.5-flash", "google", 0.0003, 0.0025),
    "gemini-2.5-flash-lite": ModelRate("gemini-2.5-flash-lite", "google", 0.0001, 0.0004),
    # Gemini 3 & 3.1 (2026-05-31)
    "gemini-3.1-pro": ModelRate("gemini-3.1-pro", "google", 0.002, 0.012),
    "gemini-3.0-flash": ModelRate("gemini-3.0-flash", "google", 0.0005, 0.003),
    "gemini-3.1-flash-lite": ModelRate("gemini-3.1-flash-lite", "google", 0.00025, 0.0015),
}


class CostEstimator:
    """Calculate token costs and monthly projections."""

    @staticmethod
    def estimate_turn(model_id: str, input_tokens: int, output_tokens: int, reasoning_tokens: int = 0) -> float:
        rate = RATE_CARD.get(model_id)
        if rate is None:
            # Unknown model: assume zero cost (common for local/Ollama models)
            # Log would happen at call site if needed; here we return 0.0 to avoid crashes.
            return 0.0
        if rate.is_local:
            return 0.0
        input_cost = (input_tokens / 1000) * rate.input_per_1k
        output_cost = (output_tokens / 1000) * rate.output_per_1k
        reasoning_cost = (reasoning_tokens / 1000) * rate.reasoning_per_1k
        return input_cost + output_cost + reasoning_cost

    @staticmethod
    def monthly_projection(
        model_id: str,
        turns_per_day: int,
        avg_input_tokens: int,
        avg_output_tokens: int,
    ) -> dict[str, Any]:
        daily = CostEstimator.estimate_turn(model_id, avg_input_tokens, avg_output_tokens) * turns_per_day
        monthly = daily * 30
        return {
            "model_id": model_id,
            "turns_per_day": turns_per_day,
            "daily_cost_usd": round(daily, 4),
            "monthly_cost_usd": round(monthly, 2),
            "yearly_cost_usd": round(monthly * 12, 2),
        }

    @staticmethod
    def compare_tiers(
        turns_per_day: int,
        avg_input_tokens: int,
        avg_output_tokens: int,
    ) -> list[dict[str, Any]]:
        results = []
        for model_id, rate in RATE_CARD.items():
            if rate.is_local:
                continue
            proj = CostEstimator.monthly_projection(
                model_id, turns_per_day, avg_input_tokens, avg_output_tokens
            )
            results.append(proj)
        results.sort(key=lambda x: x["monthly_cost_usd"])
        return results
