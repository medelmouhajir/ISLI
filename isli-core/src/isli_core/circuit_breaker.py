import time
import structlog
from enum import Enum
from collections.abc import Callable

logger = structlog.get_logger()


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Simple in-memory circuit breaker for async coroutines."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        expected_exception: type[Exception] = Exception,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.expected_exception = expected_exception

        self._state = State.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0

    @property
    def state(self) -> State:
        if (
            self._state == State.OPEN
            and self._last_failure_time is not None
            and time.monotonic() - self._last_failure_time >= self.recovery_timeout
        ):
            self._state = State.HALF_OPEN
            logger.warning("circuit_breaker.transition", name=self.name, state="HALF_OPEN")
            self._half_open_calls = 0
            self._success_count = 0
        return self._state

    async def call(self, coro_factory: Callable, *args, **kwargs):
        st = self.state
        if st == State.OPEN:
            raise CircuitOpenError(self.name, self.recovery_timeout)
        if st == State.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max_calls:
                raise CircuitOpenError(self.name, self.recovery_timeout)
            self._half_open_calls += 1

        try:
            result = await coro_factory(*args, **kwargs)
        except self.expected_exception:
            self._record_failure()
            raise

        self._record_success()
        return result

    def _record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._state == State.HALF_OPEN:
            self._state = State.OPEN
            logger.error("circuit_breaker.transition", name=self.name, state="OPEN")
        elif self._failure_count >= self.failure_threshold:
            if self._state != State.OPEN:
                self._state = State.OPEN
                logger.error("circuit_breaker.transition", name=self.name, state="OPEN")

    def _record_success(self) -> None:
        self._failure_count = 0
        if self._state == State.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_max_calls:
                self._state = State.CLOSED
                logger.info("circuit_breaker.transition", name=self.name, state="CLOSED")
                self._half_open_calls = 0


class CircuitOpenError(Exception):
    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(f"Circuit '{name}' is OPEN. Retry after {retry_after}s")
