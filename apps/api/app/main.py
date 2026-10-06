from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.documents import router as documents_router
from app.api.experiments import router as experiments_router
from app.api.race import router as race_router
from app.core.config import settings
from app.core.logging import CorrelationIdMiddleware, setup_structured_logging
from app.core.metrics import get_metrics_response
from app.core.telemetry import setup_telemetry
from app.db.base import get_engine

# 1. Initialize Sentry error-tracking if DSN is configured (no-op if unset)
if settings.sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
        )
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("Failed to initialize Sentry: %s", exc)

# 2. Configure structured JSON logging across the application
setup_structured_logging()

app = FastAPI(title="VersusLab API")

# 3. Add correlation ID middleware for request tracking
app.add_middleware(CorrelationIdMiddleware)

# 4. Allow CORS requests from Next.js frontend during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 5. Initialize OpenTelemetry tracing across FastAPI, HTTPX, and SQLAlchemy
setup_telemetry(app, get_engine())

# 6. Mount application routers (direct access, no auth router)
app.include_router(race_router)
app.include_router(documents_router)
app.include_router(experiments_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Public liveness check for deployment orchestration and health monitoring."""
    return {"status": "ok"}


@app.get("/api/metrics")
async def metrics():
    """Public Prometheus metrics endpoint exposing operational counters and latency histograms."""
    return get_metrics_response()