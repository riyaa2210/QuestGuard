"""OpenTelemetry initialisation for QueueGuard FastAPI.

Instruments:
- FastAPI (HTTP server spans)
- SQLAlchemy async engine (DB spans)
- httpx (outbound HTTP spans used in alert notifications)

Trace context is attached to every request via the standard W3C
`traceparent` header and is also stored on the WebhookEvent row
(trace_id, span_id) so you can correlate delivery logs in CloudWatch
with your APM traces.

Export target: OTLP gRPC (configure OTEL_EXPORTER_OTLP_ENDPOINT) or the
console exporter when OTEL_TRACES_EXPORTER=console (good for local dev).

Set OTEL_SDK_DISABLED=true to disable all telemetry.
"""

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_SDK_DISABLED = os.environ.get("OTEL_SDK_DISABLED", "false").lower() == "true"


def _build_provider() -> TracerProvider:
    resource = Resource.create({"service.name": "queueguard-api", "service.version": "0.1.0"})
    provider = TracerProvider(resource=resource)

    exporter_name = os.environ.get("OTEL_TRACES_EXPORTER", "console").lower()

    if exporter_name == "otlp":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter()
    else:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def configure_telemetry(app) -> None:
    """Call once at app startup.  Idempotent."""
    if _SDK_DISABLED:
        return

    provider = _build_provider()
    trace.set_tracer_provider(provider)

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from app.database import engine
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except (ImportError, Exception):
        pass

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass


def get_current_trace_context() -> tuple[str, str]:
    """Return (trace_id_hex, span_id_hex) for the current active span.

    Returns ("", "") when no active span exists (e.g. in tests).
    """
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return "", ""
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
