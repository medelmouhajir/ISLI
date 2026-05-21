import time
from collections import deque
from datetime import UTC, datetime
from threading import Lock
from typing import Any


class KeeperMetrics:
    """Lightweight in-memory metrics collector for the Keeper dashboard."""

    def __init__(self):
        self._lock = Lock()
        self._start_time = time.monotonic()
        self._inference_log: deque[dict[str, Any]] = deque(maxlen=100)
        self._agent_calls: dict[str, dict[str, int]] = {}
        self._error_counts: dict[str, int] = {}
        self._active_requests = 0
        self._total_requests = 0
        self._total_latency_ms = 0.0

    def record_inference(
        self,
        *,
        agent_id: str | None,
        endpoint: str,
        model: str | None,
        latency_ms: float,
        prompt: str = "",
        completion: str = "",
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        status: str = "success",
        error: str | None = None,
    ) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
            self._total_requests += 1
            self._total_latency_ms += latency_ms

            aid = agent_id or "system"
            self._agent_calls.setdefault(aid, {})
            self._agent_calls[aid][endpoint] = self._agent_calls[aid].get(endpoint, 0) + 1

            if status == "error" and error:
                err_key = error.split(":")[0] if ":" in error else error
                self._error_counts[err_key] = self._error_counts.get(err_key, 0) + 1

            self._inference_log.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "agent_id": aid,
                    "endpoint": endpoint,
                    "model": model or "unknown",
                    "latency_ms": round(latency_ms, 2),
                    "prompt": prompt,
                    "completion": completion,
                    "prompt_preview": prompt[:80],
                    "completion_preview": completion[:80],
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "status": status,
                    "error": error,
                }
            )

    def start_request(self) -> None:
        with self._lock:
            self._active_requests += 1

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            total = max(self._total_requests, 1)
            avg_latency = round(self._total_latency_ms / total, 2)
            return {
                "start_time_iso": datetime.fromtimestamp(self._start_time, tz=UTC).isoformat(),
                "active_requests": self._active_requests,
                "total_requests": self._total_requests,
                "avg_latency_ms": avg_latency,
                "agent_calls": dict(self._agent_calls),
                "error_counts": dict(self._error_counts),
                "recent_inferences": list(self._inference_log),
            }


_metrics = KeeperMetrics()


def get_metrics() -> KeeperMetrics:
    return _metrics
