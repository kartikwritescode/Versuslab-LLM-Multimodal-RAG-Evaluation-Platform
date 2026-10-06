# Phase 10: Production Hardening, Observability & Deployment Readiness

Welcome to the Phase 10 notes for **VersusLab**! This is the final phase of the 10-phase journey, taking the platform from a working prototype into a production-grade, hardened evaluation system.

---

## 1. What We Built

In Phase 10, we hardened the entire platform across 5 core dimensions:

1. **Security Basics**:
   - **Modern Password Hashing**: Integrated `pwdlib[argon2]` using memory-hard **Argon2id** password hashing.
   - **JWT Authentication**: Built single-user authentication (`POST /api/auth/login`, `GET /api/auth/me`) issuing signed JSON Web Tokens (`HS256`).
   - **FastAPI Auth Dependency**: Enforced valid JWTs (`get_current_user`) across all state-changing and data-reading endpoints (`/api/races`, `/api/documents`, `/api/experiments`, `/api/datasets`), while keeping `/api/health` and `/api/metrics` public.
   - **In-Memory Rate Limiting**: Implemented a sliding-window rate limiter on `POST /api/races` (60 req/min) and `POST /api/documents` (30 req/min), returning HTTP 429 with `Retry-After`.
   - **Upload Hardening**: Enforced 5MB request size limits and MIME-type/binary null-byte validation on document uploads.
   - **API Keys at Rest**: Confirmed that all provider API keys live exclusively in `.env` and `Settings`, never touching the database or frontend.

2. **Observability Stack**:
   - **Structured JSON Logging**: Implemented a single-line JSON log formatter with `X-Request-ID` correlation via `CorrelationIdMiddleware`.
   - **Race Lifecycle Logging**: Logged structured events (`race.started`, `model.started`, first token arrival with `ttft_ms`, `model.completed` with `latency_ms`, timeouts, errors, cancellations).
   - **OpenTelemetry Instrumentation**: Wired FastAPI, HTTPX (provider API calls), and SQLAlchemy database queries into an OpenTelemetry tracing pipeline exporting via OTLP gRPC to `otel/opentelemetry-collector-contrib` and visualized in Jaeger.
   - **Prometheus Metrics Endpoint**: Implemented `GET /api/metrics` exposing operational counters and histograms (`versuslab_races_total`, `versuslab_model_requests_total`, `versuslab_model_ttft_seconds`, `versuslab_model_latency_seconds`, `versuslab_retrieval_latency_seconds`).
   - **Grafana Dashboard**: Checked in an auto-provisioned starter dashboard in `infra/grafana/dashboards/versuslab_dashboard.json`.
   - **Sentry Integration**: Added plug-and-play exception tracking, initialized only if `SENTRY_DSN` is configured.

3. **Testing Completeness**:
   - **Gap-Filling Provider Tests**: Added fake HTTP transport tests (`httpx.MockTransport`) for `GrokProvider` streaming and `OllamaEmbeddingProvider`.
   - **Coordinator Direct Unit Tests**: Added unit tests directly calling `run_race` covering normal completion, first-token timeout, total model timeout, provider exceptions, and cancellation.
   - **Security & Observability Tests**: Added unit tests for Argon2id hashing, JWT validation, rate limiting, upload size limits, Prometheus metrics, and correlation IDs.
   - **Test Count**: Increased hermetic unit test coverage from **53 passed** to **69 passed** with 0 failures!
   - **Automated Load Testing**: Built `scripts/load_test_races.py` and `scripts/locustfile.py`, executing 1 baseline race and 10 concurrent races (50 model streams) and recording real measured numbers in `docs/load-test-results.md` (0.0% error rate).

4. **CI/CD Pipeline & Production Containerization**:
   - **GitHub Actions Pipeline**: Extended `.github/workflows/regression.yml` with Ruff linting, `pip-audit` security scanning, `npm audit`, unit tests, frontend build checks, and PostgreSQL regression gates.
   - **Production Multi-Stage Dockerfiles**: Created hardened, non-root Dockerfiles for `apps/api` (`python:3.12-slim`, user `appuser`) and `apps/web` (`node:24-alpine`, user `nextjs`).
   - **Production Docker Compose**: Created `docker-compose.prod.yml` wiring API, Web, PostgreSQL with pgvector, OTel Collector, Jaeger, Prometheus, and Grafana.

---

## 2. Why We Built It This Way

- **Argon2id over Legacy Passlib/Bcrypt**: `passlib` is no longer actively maintained. Modern FastAPI standards recommend `pwdlib` with Argon2id because it is memory-hard, making it resistant to GPU/ASIC hardware-cracking attacks.
- **Process-Local Rate Limiting for Portfolio Scope**: Rather than requiring an extra Redis service dependency for a single-user portfolio project, an in-memory sliding window provides clean DoS protection.
- **No Provider Keys in the Database**: By keeping all provider credentials strictly in `.env` and `Settings`, we avoid key-management complexity, database encryption overhead, and data-leak risks entirely.
- **OpenTelemetry Standard**: By exporting standard OTLP traces to an OpenTelemetry Collector rather than tying the application to a single tracing vendor, the API can export traces to Jaeger, Datadog, Honeycomb, or AWS X-Ray without code changes.

---

## 3. Files Touched and Created

```text
versus_lab/
├── docker-compose.prod.yml                    # Local production stack (API, Web, DB, Observability)
├── README.md                                  # Top-level documentation and quickstart
├── .github/workflows/regression.yml           # CI/CD pipeline with pip-audit and build checks
├── infra/
│   ├── docker-compose.yml                     # Updated with OTel, Jaeger, Prometheus, Grafana
│   ├── otel-collector-config.yaml             # OpenTelemetry pipeline routing traces to Jaeger
│   ├── prometheus/prometheus.yml              # Prometheus scraper configuration
│   └── grafana/
│       ├── provisioning/datasources/          # Auto-provisioned Prometheus datasource
│       ├── provisioning/dashboards/           # Dashboard provider configuration
│       └── dashboards/versuslab_dashboard.json# Starter operational dashboard
├── scripts/
│   ├── load_test_races.py                     # Load test runner (measures p50/p95/p99)
│   └── locustfile.py                          # Locust load test scenario script
├── docs/
│   ├── architecture.md                        # Complete architecture of the built system
│   ├── load-test-results.md                   # Real measured load test metrics
│   └── phase-notes/phase-10.md                # This document
└── apps/
    ├── api/
    │   ├── Dockerfile                         # Multi-stage production container for API
    │   ├── requirements.txt                   # Added pwdlib, pyjwt, prometheus, opentelemetry, sentry
    │   ├── .env.example                       # Documented all Phase 10 environment variables
    │   ├── app/
    │   │   ├── main.py                        # Added correlation middleware, metrics, telemetry
    │   │   ├── core/
    │   │   │   ├── auth.py                    # Password hashing, JWT token creation/verification
    │   │   │   ├── config.py                  # Added auth, upload limits, rate limits, OTel settings
    │   │   │   ├── logging.py                 # Structured JSON logging & correlation ID middleware
    │   │   │   ├── metrics.py                 # Prometheus counters & histograms
    │   │   │   ├── rate_limit.py              # In-memory sliding-window rate limiter
    │   │   │   └── telemetry.py               # OpenTelemetry tracer & instrumentation hooks
    │   │   ├── api/
    │   │   │   ├── auth.py                    # Login and user profile endpoints
    │   │   │   ├── documents.py               # Added auth, rate limiting, upload size limit
    │   │   │   ├── experiments.py             # Added auth dependency across all endpoints
    │   │   │   └── race.py                    # Added auth, rate limiting, retrieval metrics
    │   │   └── race/coordinator.py            # Added structured logging & metrics observation
    │   └── tests/
    │       ├── conftest.py                    # Shared autouse auth fixture for legacy tests
    │       ├── test_auth_and_security.py      # Auth, Argon2, rate limit, upload validation tests
    │       ├── test_coordinator_direct.py     # Direct unit tests for run_race generator
    │       ├── test_metrics_and_observability.py # Prometheus & correlation ID tests
    │       ├── test_cloud_providers.py        # Added Grok MockTransport test
    │       ├── test_ollama_provider.py        # Added Ollama embedding MockTransport test
    │       └── test_evaluations.py            # Added cost calculation matrix edge cases
    └── web/
        ├── Dockerfile                         # Multi-stage production container for Next.js
        └── lib/race-client.ts                 # Added JWT token storage and auth headers
```

---

## 4. How to Run and Verify Everything

### A. Run Hermetic Test Suite (69 Passed)
```powershell
cd apps/api
.venv\Scripts\pytest -v
```

### B. Run Code Quality & Lint Checks
```powershell
cd apps/api
.venv\Scripts\ruff check .
```

### C. Run Load Test Benchmark (Generates `docs/load-test-results.md`)
```powershell
apps\api\.venv\Scripts\python scripts\load_test_races.py
```

### D. Run Local Production Stack with Docker Compose
```powershell
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```
Then visit:
- **Next.js Web UI**: `http://localhost:3000`
- **FastAPI OpenAPI Docs**: `http://localhost:8000/docs`
- **Prometheus Metrics**: `http://localhost:8000/api/metrics`
- **Jaeger Tracing UI**: `http://localhost:16686`
- **Grafana Dashboard**: `http://localhost:3001` (login: `admin` / `admin`)

---

## 5. Five Software Engineering Concepts to Understand

### 1. Argon2id vs Legacy Password Hashing (Bcrypt & PBKDF2)
- **What it is**: Passwords should never be stored in plain text. Hashing algorithms like MD5 or SHA-256 are fast, which makes them vulnerable to brute-force attacks on GPUs. Argon2id (winner of the Password Hashing Competition) is **memory-hard**: it requires a configurable amount of RAM to compute each hash, making parallel GPU attacks prohibitively expensive.

### 2. OpenTelemetry (OTel) & the OTLP Protocol
- **What it is**: OpenTelemetry is the vendor-neutral cloud-native standard for distributed tracing and metrics. Instead of embedding proprietary SDKs for specific vendors into your application code, you emit traces over standard OTLP (OpenTelemetry Protocol, typically over gRPC port 4317). A local Collector receives these traces and fans them out to visualization engines like Jaeger.

### 3. Prometheus Metric Types: Counters vs Histograms
- **What it is**:
  - **Counter**: A cumulative metric that only increases (e.g. `versuslab_races_total`). Used with functions like `rate()` to calculate requests per second.
  - **Histogram**: Samples observations (usually timings like TTFT and Latency) and counts them in configurable buckets. This allows computing accurate statistical percentiles (p50, p95, p99) over sliding time windows.

### 4. Sliding-Window Rate Limiting
- **What it is**: To prevent denial-of-service (DoS) attacks or API abuse, rate limiters restrict the number of requests a client can make in a given timeframe. Unlike a "fixed window" (which can suffer from request spikes at the boundary between minutes), a **sliding window** tracks recent request timestamps and evicts those older than 60 seconds, guaranteeing a smooth, fair request rate.

### 5. Multi-Stage Docker Builds & Non-Root Containers
- **What it is**: In standard Docker builds, compilers (like `gcc`), package caches, and build tools end up in the final image, making it large and vulnerable. A **multi-stage build** compiles dependencies in an initial `builder` stage, then copies only the final runtime artifacts into a slim `runner` stage. Furthermore, running the container under an unprivileged user (`appuser` with UID 1000) prevents root-escalation attacks if the application is ever compromised.
