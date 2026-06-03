import time
from collections import deque
from datetime import UTC, datetime
from threading import Lock
from typing import Any

import numpy as np


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
        inference_ms: float | None = None,
        queue_wait_ms: float | None = None,
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
                    "inference_ms": round(inference_ms, 2) if inference_ms is not None else None,
                    "queue_wait_ms": round(queue_wait_ms, 2) if queue_wait_ms is not None else None,
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

    def get_snapshot(self, queue_depths: dict[int, int] | None = None) -> dict[str, Any]:
        with self._lock:
            total = max(self._total_requests, 1)
            avg_latency = round(self._total_latency_ms / total, 2)
            
            # Calculate percentiles for successful inferences
            latencies = [log["latency_ms"] for log in self._inference_log if log["status"] == "success"]
            p50 = round(float(np.percentile(latencies, 50)), 2) if latencies else 0
            p95 = round(float(np.percentile(latencies, 95)), 2) if latencies else 0
            p99 = round(float(np.percentile(latencies, 99)), 2) if latencies else 0

            # Determine SLO status
            # Threshold: P95 < 30s for critical path (context_inject is P0)
            # This is a simple heuristic for now
            slo_status = "healthy"
            if p95 > 30000:
                slo_status = "degraded"
            if p95 > 60000:
                slo_status = "critical"

            snapshot = {
                "start_time_iso": datetime.fromtimestamp(self._start_time, tz=UTC).isoformat(),
                "active_requests": self._active_requests,
                "total_requests": self._total_requests,
                "avg_latency_ms": avg_latency,
                "percentiles": {
                    "p50_ms": p50,
                    "p95_ms": p95,
                    "p99_ms": p99,
                },
                "slos": {
                    "status": slo_status,
                },
                "agent_calls": dict(self._agent_calls),
                "error_counts": dict(self._error_counts),
                "recent_inferences": list(self._inference_log),
            }

            if queue_depths:
                snapshot["queue"] = {
                    f"p{k}_depth": v for k, v in queue_depths.items()
                }

            return snapshot


_metrics = KeeperMetrics()


def get_metrics() -> KeeperMetrics:
    return _metrics
