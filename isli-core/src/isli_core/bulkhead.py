import asyncio
from typing import Any, Callable

from fastapi import HTTPException


class Bulkhead:
    """Per-agent and per-skill connection limiter using asyncio.Semaphore."""

    def __init__(self, name: str, max_concurrent: int, max_queue: int = 100):
        self.name = name
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_queue = max_queue
        self._queue_size = 0
        self._lock = asyncio.Lock()

    async def acquire(self, timeout: float = 10.0) -> bool:
        async with self._lock:
            if self._queue_size >= self.max_queue:
                raise HTTPException(
                    status_code=503,
                    detail=f"Bulkhead '{self.name}' queue full ({self.max_queue})",
                )
            self._queue_size += 1

        try:
            acquired = await asyncio.wait_for(self.semaphore.acquire(), timeout=timeout)
            return acquired
        except asyncio.TimeoutError:
            async with self._lock:
                self._queue_size -= 1
            raise HTTPException(
                status_code=503,
                detail=f"Bulkhead '{self.name}' acquire timeout",
            )

    def release(self) -> None:
        self.semaphore.release()
        asyncio.create_task(self._decrement_queue())

    async def _decrement_queue(self) -> None:
        async with self._lock:
            self._queue_size = max(0, self._queue_size - 1)

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.release()


class BulkheadRegistry:
    """Registry of bulkheads per agent and per skill."""

    def __init__(self):
        self._bulkheads: dict[str, Bulkhead] = {}

    def get_or_create(self, name: str, max_concurrent: int, max_queue: int = 100) -> Bulkhead:
        if name not in self._bulkheads:
            self._bulkheads[name] = Bulkhead(name, max_concurrent, max_queue)
        return self._bulkheads[name]

    def remove(self, name: str) -> None:
        self._bulkheads.pop(name, None)
