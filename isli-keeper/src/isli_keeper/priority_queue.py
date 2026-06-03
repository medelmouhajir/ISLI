import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict

import structlog

from .metrics import get_metrics

logger = structlog.get_logger()

# Priority Tiers (Lower number = Higher priority)
P0 = 0  # Critical: Context Injection, Model Routing
P1 = 1  # High: Heartbeat Validation, PII Scrubbing
P2 = 2  # Standard: Summarization, Skill Clean, Logic Verify
P3 = 3  # Background: Journal Update, Embed

@dataclass(order=True)
class PrioritizedTask:
    priority: int
    timestamp: float = field(default_factory=time.monotonic)
    func: Callable[..., Coroutine[Any, Any, Any]] = field(default=None, compare=False)
    args: tuple = field(default_factory=tuple, compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)
    future: asyncio.Future = field(default=None, compare=False)
    enqueue_time: float = field(default_factory=time.monotonic, compare=False)
    metadata: dict = field(default_factory=dict, compare=False)

class PriorityManager:
    def __init__(self, max_p3_depth: int = 50):
        self.queue: asyncio.PriorityQueue[PrioritizedTask] = asyncio.PriorityQueue()
        self.max_p3_depth = max_p3_depth
        self._depths: Dict[int, int] = {P0: 0, P1: 0, P2: 0, P3: 0}
        self._worker_task: asyncio.Task | None = None
        self._running = False

    def start(self):
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("priority_manager.started", max_p3_depth=self.max_p3_depth)

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
            logger.info("priority_manager.stopped")

    def get_depths(self) -> Dict[int, int]:
        return self._depths.copy()

    async def submit(self, priority: int, timeout: float, func: Callable, metadata: dict, *args, **kwargs) -> Any:
        if priority == P3 and self._depths[P3] >= self.max_p3_depth:
            logger.warning("priority_manager.p3_throttled", depth=self._depths[P3])
            raise RuntimeError("P3 queue depth exceeded")

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        task = PrioritizedTask(
            priority=priority,
            func=func,
            args=args,
            kwargs=kwargs,
            future=future,
            metadata=metadata
        )
        
        self._depths[priority] += 1
        await self.queue.put(task)
        
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("priority_manager.task_timeout", priority=priority, timeout=timeout, endpoint=metadata.get("endpoint"))
            raise
        finally:
            self._depths[priority] -= 1

    async def _worker_loop(self):
        metrics = get_metrics()
        while self._running:
            try:
                task = await self.queue.get()
                if task.future.done():
                    self.queue.task_done()
                    continue
                
                wait_time_ms = (time.monotonic() - task.enqueue_time) * 1000
                inference_start = time.monotonic()
                
                try:
                    result = await task.func(*task.args, **task.kwargs)
                    inference_ms = (time.monotonic() - inference_start) * 1000
                    total_latency_ms = (time.monotonic() - task.enqueue_time) * 1000
                    
                    if not task.future.done():
                        task.future.set_result(result)
                    
                    # Record success metrics
                    metrics.record_inference(
                        agent_id=task.metadata.get("agent_id"),
                        endpoint=task.metadata.get("endpoint", "unknown"),
                        model=task.metadata.get("model"),
                        latency_ms=total_latency_ms,
                        inference_ms=inference_ms,
                        queue_wait_ms=wait_time_ms,
                        prompt=task.metadata.get("prompt", ""),
                        completion=str(result.get("response", "")) if isinstance(result, dict) else "",
                        status="success"
                    )
                except Exception as e:
                    inference_ms = (time.monotonic() - inference_start) * 1000
                    total_latency_ms = (time.monotonic() - task.enqueue_time) * 1000
                    
                    if not task.future.done():
                        task.future.set_exception(e)
                    
                    # Record error metrics
                    metrics.record_inference(
                        agent_id=task.metadata.get("agent_id"),
                        endpoint=task.metadata.get("endpoint", "unknown"),
                        model=task.metadata.get("model"),
                        latency_ms=total_latency_ms,
                        inference_ms=inference_ms,
                        queue_wait_ms=wait_time_ms,
                        status="error",
                        error=str(e)
                    )
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("priority_manager.worker_error", error=str(e))
                await asyncio.sleep(0.1)

_manager = PriorityManager()

def get_priority_manager() -> PriorityManager:
    return _manager
