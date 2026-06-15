"""F1: OpenTelemetry tracing for FastAPI routes and Celery tasks.

Sets up the OTLP exporter that sends traces to a local Jaeger / Tempo instance.
Instrument by calling :func:`setup_tracing` once during application startup.

Gracefully degrades if ``opentelemetry-sdk`` is not installed — production
deployments simply won't emit traces rather than crashing.

Environment variables:
  OTEL_ENABLED           – Set to "true" to enable tracing (default: false in dev)
  OTEL_SERVICE_NAME      – Service name in traces (default: "trading-navigator")
  OTEL_EXPORTER_OTLP_ENDPOINT – OTLP endpoint (default: "http://localhost:4317")
"""

import os

from app.core.logging import get_logger

logger = get_logger(__name__)


def setup_tracing(app=None) -> bool:
    """Initialise OpenTelemetry tracing.

    Args:
        app: Optional FastAPI application instance.  When provided, the
             ``FastAPIInstrumentor`` is applied so all HTTP routes are traced
             automatically.

    Returns:
        True if tracing was successfully initialised, False otherwise.
    """
    if os.environ.get("OTEL_ENABLED", "false").lower() != "true":
        logger.debug("OpenTelemetry tracing disabled (OTEL_ENABLED != 'true')")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # type: ignore
    except ImportError:
        logger.warning(
            "opentelemetry-sdk not installed — tracing disabled. "
            "Install with: pip install opentelemetry-sdk opentelemetry-exporter-otlp"
        )
        return False

    service_name = os.environ.get("OTEL_SERVICE_NAME", "trading-navigator")
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Instrument FastAPI if the application is provided
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore

            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPIInstrumentor applied to %s", app.title)
        except ImportError:
            logger.warning("FastAPIInstrumentor not available — HTTP spans disabled")

    # Instrument SQLAlchemy
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # type: ignore

        SQLAlchemyInstrumentor().instrument()
        logger.info("SQLAlchemyInstrumentor applied")
    except ImportError:
        pass

    # Instrument Redis
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor  # type: ignore

        RedisInstrumentor().instrument()
        logger.info("RedisInstrumentor applied")
    except ImportError:
        pass

    logger.info(
        "OpenTelemetry tracing initialised — service=%s endpoint=%s",
        service_name,
        otlp_endpoint,
    )
    return True


def get_tracer(name: str = "trading-navigator"):
    """Return an OpenTelemetry tracer, or a no-op tracer if OTel is not active."""
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


class _NoOpSpan:
    """No-op span that satisfies the tracer context manager protocol."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def set_attribute(self, key: str, value: object) -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass

    def set_status(self, *_) -> None:
        pass


class _NoOpTracer:
    """No-op tracer returned when OTel is unavailable."""

    def start_as_current_span(self, name: str, **_kwargs):
        return _NoOpSpan()

    def start_span(self, name: str, **_kwargs):
        return _NoOpSpan()
