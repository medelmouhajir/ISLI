from typing import Any
from pydantic import BaseModel


class PartialResult(BaseModel):
    """Schema for skill calls that partially succeed."""

    success: bool
    task_id: str
    skill_name: str
    data: dict[str, Any] | None = None
    error: str | None = None
    completed_steps: list[str]
    remaining_steps: list[str]
    idempotency_key: str | None = None

    def is_complete(self) -> bool:
        return self.success and not self.remaining_steps

    def can_retry(self) -> bool:
        return not self.success and bool(self.remaining_steps)


class IdempotencyCache:
    """In-memory idempotency cache for skill call results (Redis-backed in production)."""

    def __init__(self):
        self._cache: dict[str, PartialResult] = {}

    def get(self, key: str) -> PartialResult | None:
        return self._cache.get(key)

    def set(self, key: str, result: PartialResult) -> None:
        self._cache[key] = result

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)
