from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from ai_agent_template.core.settings import Settings


def configure_tracing(app: FastAPI, settings: Settings) -> None:
    if not settings.otel_enabled:
        return

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: settings.service_name}))
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str = "ai_agent_template") -> trace.Tracer:
    return trace.get_tracer(name)


@contextmanager
def agent_span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    """Open a span with the agent tracer, dropping `None` attributes for cleanliness.

    No-ops cleanly when tracing is not configured (the OTEL API returns a no-op tracer).
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is None:
                continue
            span.set_attribute(f"agent.{key}", value)
        yield span
