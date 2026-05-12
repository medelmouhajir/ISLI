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
    def recommend_model(score: int, agent_config: dict[str, Any]) -> str:
        from isli_core.cost.tiering import ModelTiering

        tier = TaskComplexityScorer.recommend_tier(score)
        return ModelTiering.resolve_model(agent_config, tier)
