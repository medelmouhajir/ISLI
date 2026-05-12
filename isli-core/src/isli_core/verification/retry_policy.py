"""Retry backoff configuration for grounding and skill failures."""

import random


class RetryPolicyMapper:
    """Map failure categories to retry/backoff configs."""

    DEFAULT = {"max_retries": 3, "backoff_base": 1.0, "backoff_cap": 30.0, "jitter": True}
    HTTP_5XX = {"max_retries": 3, "backoff_base": 1.0, "backoff_cap": 30.0, "jitter": True}
    VERIFICATION_FAIL = {"max_retries": 2, "backoff_base": 0.5, "backoff_cap": 5.0, "jitter": True}
    TIMEOUT = {"max_retries": 3, "backoff_base": 2.0, "backoff_cap": 60.0, "jitter": True}

    @classmethod
    def get(cls, category: str) -> dict:
        return getattr(cls, category.upper(), cls.DEFAULT)

    @staticmethod
    def compute_delay(attempt: int, base: float, cap: float, jitter: bool) -> float:
        delay = min(base * (2 ** attempt), cap)
        if jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        return delay
