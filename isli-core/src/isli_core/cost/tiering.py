"""Three-tier fallback: expensive → cheap → local → pause."""

import structlog
from typing import Any

from isli_core.cost.rate_card import RATE_CARD, ModelRate

logger = structlog.get_logger()

TIER_ORDER = ["premium", "standard", "local"]

TIER_MODELS: dict[str, list[str]] = {
    "premium": ["claude-sonnet-4-6", "gpt-4o"],
    "standard": ["claude-haiku-4-5", "gpt-4o-mini"],
    "local": ["qwen3:1.7b", "qwen3:0.6b"],
}


class ModelTiering:
    """Route tasks through cost tiers with fallback."""

    @staticmethod
    def resolve_model(agent_config: dict[str, Any], tier: str | None = None) -> str:
        if tier:
            candidates = TIER_MODELS.get(tier, TIER_MODELS["standard"])
        else:
            candidates = [agent_config.get("model_id", "qwen3:1.7b")]

        preferred = agent_config.get("preferred_model")
        if preferred and preferred in candidates:
            return preferred

        # Return first available candidate
        for c in candidates:
            if c in RATE_CARD:
                return c
        return "qwen3:1.7b"

    @staticmethod
    def downgrade_tier(current_tier: str) -> str | None:
        idx = TIER_ORDER.index(current_tier)
        if idx + 1 < len(TIER_ORDER):
            return TIER_ORDER[idx + 1]
        return None  # Already at local; next step is pause

    @staticmethod
    async def attempt_with_fallback(
        agent_config: dict[str, Any],
        call_fn: Any,
        budget_remaining: float,
    ) -> dict[str, Any]:
        tier = agent_config.get("tier", "premium")
        while tier:
            model = ModelTiering.resolve_model(agent_config, tier)
            rate = RATE_CARD.get(model)
            if rate and not rate.is_local:
                # Rough estimate: if budget can't cover even a small turn, downgrade
                estimated_cost = (1000 / 1000) * rate.input_per_1k + (500 / 1000) * rate.output_per_1k
                if estimated_cost > budget_remaining:
                    logger.warning("tiering.budget_exceeded", tier=tier, model=model, budget=budget_remaining)
                    tier = ModelTiering.downgrade_tier(tier)
                    continue

            try:
                result = await call_fn(model)
                logger.info("tiering.success", tier=tier, model=model)
                return {"result": result, "tier": tier, "model": model}
            except Exception as exc:
                logger.warning("tiering.failed", tier=tier, model=model, error=str(exc))
                tier = ModelTiering.downgrade_tier(tier)

        logger.error("tiering.exhausted", agent_id=agent_config.get("agent_id"))
        return {"result": None, "tier": "paused", "model": None, "reason": "All tiers exhausted"}
