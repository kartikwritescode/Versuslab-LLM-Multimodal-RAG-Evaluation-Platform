import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import settings

logger = logging.getLogger(__name__)


def setup_telemetry(app: Any, engine: Any = None) -> None:
    """Configures OpenTelemetry tracing and instruments FastAPI, HTTPX, and SQLAlchemy.

    Exports traces via OTLP gRPC to the configured collector endpoint (e.g. otel-collector:4317).
    Operates as a safe no-op if settings.otel_enabled is False.
    """
    if not settings.otel_enabled:
        logger.info("OpenTelemetry tracing is disabled by configuration (settings.otel_enabled=False).")
        return

    try:
        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)

        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=True,
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(provider)

        # 1. Instrument FastAPI application
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

        # 2. Instrument HTTPX client calls (used by all cloud and local providers)
        HTTPXClientInstrumentor().instrument(tracer_provider=provider)

        # 3. Instrument SQLAlchemy queries if engine is provided
        if engine is not None:
            sync_engine = getattr(engine, "sync_engine", engine)
            SQLAlchemyInstrumentor().instrument(
                engine=sync_engine,
                tracer_provider=provider,
            )

        logger.info(
            "OpenTelemetry initialized successfully. Exporting traces to %s",
            settings.otel_exporter_otlp_endpoint,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialize OpenTelemetry tracing: %s", exc)
