"""Keeper-side score to route trivial tasks to cheaper models."""

import structlog
from typing import Any

logger = structlog.get_logger()

KEYWORD_WEIGHTS = {
    "simple": -2,
    "hello": -2,
    "hi": -2,
    "what is": -1,
    "define": -1,
    "summarize": -1,
    "research": 2,
    "analyze": 2,
    "compare": 2,
    "code": 1,
    "debug": 1,
    "refactor": 2,
    "architect": 3,
    "design": 2,
    "plan": 1,
    "complex": 2,
    "deep": 1,
    "detailed": 1,
}

LENGTH_THRESHOLDS = {
    "short": 50,
    "medium": 200,
    "long": 500,
}


class TaskComplexityScorer:
    """Score task complexity on a 1–10 scale. Lower = simpler/cheaper model."""

    @staticmethod
    def score(task_input: str) -> int:
        text = task_input.lower().strip()
        score = 5  # baseline

        # Keyword modifiers
        for keyword, weight in KEYWORD_WEIGHTS.items():
            if keyword in text:
                score += weight

        # Length modifier
        length = len(text)
        if length < LENGTH_THRESHOLDS["short"]:
            score -= 2
        elif length < LENGTH_THRESHOLDS["medium"]:
            score -= 1
        elif length > LENGTH_THRESHOLDS["long"]:
            score += 2

        # Clamp 1–10
        return max(1, min(10, score))

    @staticmethod
    def recommend_tier(score: int) -> str:
        if score <= 3:
            return "local"
        if score <= 6:
            return "standard"
        return "premium"

    @staticmethod
    def score_task_input(task_input: str) -> tuple[int, str]:
        """Score task complexity and return (score, tier)."""
        score = TaskComplexityScorer.score(task_input)
        tier = TaskComplexityScorer.recommend_tier(score)
        return score, tier

    @staticmethod
    def recommend_model(score: int, agent_config: dict[str, Any]) -> str:
        from isli_core.cost.tiering import ModelTiering

        tier = TaskComplexityScorer.recommend_tier(score)
        return ModelTiering.resolve_model(agent_config, tier)


TIER_ORDER = ["local", "standard", "premium"]


def filter_models_by_tier(secondary_models: list[dict], tier: str) -> list[dict]:
    """Drop models whose cost_tier is strictly more expensive than the task tier.

    If no models remain after filtering, return the full list (fail-open).
    """
    if not secondary_models:
        return []

    try:
        task_idx = TIER_ORDER.index(tier)
    except ValueError:
        return list(secondary_models)

    filtered = [
        m for m in secondary_models
        if TIER_ORDER.index(m.get("cost_tier", "premium")) <= task_idx
    ]

    if not filtered:
        logger.warning(
            "complexity.filter_empty",
            tier=tier,
            model_count=len(secondary_models),
            message="All secondary models are above task tier; returning full list",
        )
        return list(secondary_models)

    return filtered
