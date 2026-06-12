"""OpenTelemetry hooks (optional, best-effort).

Tracing is opt-in via OTEL_ENABLED. We keep imports lazy and failures non-fatal:
a prototype must still run if OTEL packages aren't installed. When enabled and the
packages are present, we auto-instrument FastAPI and (if configured) export to an
OTLP endpoint or Azure Monitor / Application Insights.

TODO(prod): pin opentelemetry-* and azure-monitor-opentelemetry in pyproject and
remove the soft-import guards once observability is a hard requirement.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.telemetry")


def configure_telemetry(app: Any) -> None:
    """Configure tracing for the FastAPI app if enabled and available."""
    settings = get_settings()
    if not settings.otel_enabled:
        logger.debug("otel_disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "otel_unavailable",
            extra={"hint": "uv add opentelemetry-sdk opentelemetry-instrumentation-fastapi"},
        )
        return

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)

    exporter = _build_exporter(settings)
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    logger.info("otel_enabled", extra={"service": settings.otel_service_name})


def _build_exporter(settings: Any) -> Any | None:
    """Return a span exporter based on configuration, or None."""
    # Prefer Azure Monitor / App Insights when a connection string is present.
    if settings.applicationinsights_connection_string:
        try:
            from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

            return AzureMonitorTraceExporter(
                connection_string=settings.applicationinsights_connection_string
            )
        except ImportError:
            logger.warning("azure_monitor_exporter_unavailable")

    if settings.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            return OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        except ImportError:
            logger.warning("otlp_exporter_unavailable")

    return None
