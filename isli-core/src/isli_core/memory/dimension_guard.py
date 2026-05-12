import structlog
from typing import Any

logger = structlog.get_logger()

# Expected dimensions per model
MODEL_DIMENSIONS = {
    "nomic-embed-text": 768,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

DEFAULT_DIMENSION = 768


class VectorDimensionGuard:
    """Startup assertion that model output dimension matches schema."""

    @staticmethod
    def assert_dimension(embedding: list[float], model_name: str | None = None) -> None:
        expected = MODEL_DIMENSIONS.get(model_name or "nomic-embed-text", DEFAULT_DIMENSION)
        actual = len(embedding)
        if actual != expected:
            raise ValueError(
                f"Vector dimension mismatch for {model_name}: expected {expected}, got {actual}"
            )
        logger.info("dimension_guard.ok", model=model_name, dim=actual)

    @staticmethod
    def register_model(name: str, dimension: int) -> None:
        MODEL_DIMENSIONS[name] = dimension
        logger.info("dimension_guard.registered", model=name, dim=dimension)

    @staticmethod
    def get_dimension(model_name: str) -> int:
        return MODEL_DIMENSIONS.get(model_name, DEFAULT_DIMENSION)
