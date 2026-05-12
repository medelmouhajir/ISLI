import os
import structlog

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def configure_structlog(service_name: str) -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.ExtraAdder(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def configure_otel(service_name: str) -> trace.TracerProvider:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


def configure_otel_metrics(service_name: str) -> MeterProvider:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    resource = Resource.create({"service.name": service_name})
    exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=60000)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return provider


def get_meter(service_name: str):
    return metrics.get_meter(service_name)


_meter = None

def _get_core_meter():
    global _meter
    if _meter is None:
        _meter = metrics.get_meter("isli-core")
    return _meter


def get_task_creation_counter():
    return _get_core_meter().create_counter(
        "isli.task.creation",
        description="Number of tasks created",
        unit="1",
    )


def get_heartbeat_latency_histogram():
    return _get_core_meter().create_histogram(
        "isli.agent.heartbeat_latency",
        description="Agent heartbeat latency in milliseconds",
        unit="ms",
    )


def get_skill_invocation_error_counter():
    return _get_core_meter().create_counter(
        "isli.skill.invocation_errors",
        description="Number of skill invocation errors",
        unit="1",
    )


def instrument_fastapi(app, service_name: str) -> trace.TracerProvider:
    configure_structlog(service_name)
    provider = configure_otel(service_name)
    configure_otel_metrics(service_name)
    FastAPIInstrumentor.instrument_app(app)
    return provider


propagator = TraceContextTextMapPropagator()


def get_trace_id() -> str | None:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return None
