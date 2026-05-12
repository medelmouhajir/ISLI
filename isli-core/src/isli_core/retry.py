import asyncio
import random
import structlog
from typing import Callable, TypeVar

from isli_core.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = structlog.get_logger()

T = TypeVar("T")


async def exponential_backoff(
    coro_factory: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    circuit_breaker: CircuitBreaker | None = None,
    jitter: bool = True,
) -> T:
    last_exception: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            if circuit_breaker:
                return await circuit_breaker.call(coro_factory)
            return await coro_factory()
        except CircuitOpenError:
            raise
        except exceptions as exc:
            last_exception = exc
            if attempt >= max_retries:
                break
            delay = min(base_delay * (2 ** attempt), max_delay)
            if jitter:
                delay = delay * (0.5 + random.random())
            logger.warning(
                "retry.backoff",
                attempt=attempt + 1,
                max_retries=max_retries,
                delay=delay,
                exception=type(exc).__name__,
            )
            await asyncio.sleep(delay)
    raise last_exception
