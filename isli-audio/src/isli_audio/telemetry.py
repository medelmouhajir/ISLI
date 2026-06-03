"""Telemetry utilities for the audio service."""

import time
from typing import Any

import structlog
from fastapi import FastAPI, Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = structlog.get_logger()


class AudioMetrics:
    """Simple in-memory metrics collector for the audio service."""

    def __init__(self):
        self._start_time = time.monotonic()
        self.total_requests = 0
        self.active_requests = 0
        self.inference_counts: dict[str, int] = {"stt": 0, "tts": 0}
        self.inference_latencies: dict[str, list[float]] = {"stt": [], "tts": []}
        self.error_counts: dict[str, int] = {"stt": 0, "tts": 0}
        self.recent_inferences: list[dict[str, Any]] = []

    def start_request(self):
        self.total_requests += 1
        self.active_requests += 1

    def end_request(self):
        self.active_requests = max(0, self.active_requests - 1)

    def record_inference(
        self,
        endpoint: str,
        model: str,
        latency_ms: float,
        status: str = "success",
        error: str | None = None,
    ):
        self.inference_counts[endpoint] = self.inference_counts.get(endpoint, 0) + 1
        if status == "success":
            self.inference_latencies.setdefault(endpoint, []).append(latency_ms)
        else:
            self.error_counts[endpoint] = self.error_counts.get(endpoint, 0) + 1

        self.recent_inferences.append({
            "endpoint": endpoint,
            "model": model,
            "latency_ms": round(latency_ms, 2),
            "status": status,
            "error": error,
            "timestamp": time.time(),
        })
        # Keep only last 50
        self.recent_inferences = self.recent_inferences[-50:]

    def get_snapshot(self) -> dict[str, Any]:
        avg_latencies = {}
        for ep, latencies in self.inference_latencies.items():
            if latencies:
                avg_latencies[ep] = round(sum(latencies) / len(latencies), 2)
            else:
                avg_latencies[ep] = 0.0

        return {
            "total_requests": self.total_requests,
            "active_requests": self.active_requests,
            "inference_counts": self.inference_counts,
            "avg_latency_ms": avg_latencies,
            "error_counts": self.error_counts,
            "recent_inferences": self.recent_inferences,
        }


_metrics_instance: AudioMetrics | None = None


def get_metrics() -> AudioMetrics:
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = AudioMetrics()
    return _metrics_instance


def instrument_fastapi(app: FastAPI, service_name: str):
    """Instrument FastAPI with OpenTelemetry tracing."""
    resource = Resource(attributes={SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(OTLPSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
