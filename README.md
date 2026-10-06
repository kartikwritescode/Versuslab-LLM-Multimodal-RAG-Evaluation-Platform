# VersusLab — LLM Experimentation & Multimodal Evaluation Platform

[![CI/CD Pipeline](https://github.com/kartikwritescode/versus_lab/actions/workflows/regression.yml/badge.svg)](https://github.com/kartikwritescode/versus_lab/actions)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Next.js 16](https://img.shields.io/badge/next.js-16.3-black.svg)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-336791.svg)](https://github.com/pgvector/pgvector)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-Tracing-blueviolet.svg)](https://opentelemetry.io)
[![Prometheus](https://img.shields.io/badge/Prometheus-Metrics-orange.svg)](https://prometheus.io)

**VersusLab** is an open-source LLM experimentation, benchmarking, and evaluation platform designed for side-by-side model comparison. A user sends a prompt (optionally grounded in knowledge-base documents) to several LLMs simultaneously. Every contender streams its answer live over **one multiplexed Server-Sent Events (SSE) connection**.

The platform captures **Time To First Token (TTFT)**, total latency, throughput (tokens/sec), token usage, financial cost, and output quality across deterministic metrics and blind LLM-as-judge evaluations, persisting all runs into PostgreSQL for reproducible experimentation.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Client ["Frontend & Clients"]
        Web["Next.js Web App\n(React 19 / TailwindCSS 4)"]
        Locust["Locust / Load Test Scripts"]
    end

    subgraph API ["VersusLab API (FastAPI / Python 3.12)"]
        AuthMiddleware["Correlation & JWT Auth Middleware"]
        RateLimiter["In-Memory Sliding-Window Rate Limiter"]
        Coordinator["Race Coordinator\n(Multiplexed SSE Engine)"]
        RAGPipeline["Advanced RAG Engine\n(pgvector + tsvector + FlashRank)"]
        EvalEngine["Evaluation Engine\n(Deterministic & Blind LLM Judge)"]
        ExpEngine["Experiment Engine\n(Benchmark Runner & Pareto Aggregator)"]
    end

    subgraph Storage ["Storage Layer"]
        Postgres[("PostgreSQL 17 + pgvector\n(Races, ModelRuns, Documents, Chunks, Datasets, Experiments)")]
    end

    subgraph Providers ["Model Provider Adapters"]
        MockP["MockProvider (Fast, Slow, Broken, Stuck)"]
        OllamaP["OllamaProvider (qwen3:4b, nomic-embed-text)"]
        OpenAIP["OpenAIProvider (gpt-4o-mini)"]
        AnthropicP["AnthropicProvider (claude-3-5-haiku)"]
        GeminiP["GeminiProvider (gemini-2.5-flash)"]
        GrokP["GrokProvider (grok-2-1212)"]
    end

    subgraph Observability ["Observability Stack"]
        OTel["OpenTelemetry Collector (Contrib:4317)"]
        Jaeger["Jaeger Tracing (16686)"]
        Prometheus["Prometheus (9090)"]
        Grafana["Grafana Dashboards (3001)"]
    end

    Web -->|HTTP / SSE| AuthMiddleware
    Locust -->|HTTP / SSE| AuthMiddleware
    AuthMiddleware --> RateLimiter
    RateLimiter --> Coordinator
    RateLimiter --> RAGPipeline
    RateLimiter --> ExpEngine
    Coordinator -->|Async Generators| Providers
    RAGPipeline -->|Dense Embeddings| OllamaP
    RAGPipeline -->|Hybrid Search| Postgres
    Coordinator -->|Async Persistence Tracker| Postgres
    ExpEngine -->|Reuses Race Engine| Coordinator
    EvalEngine -->|Scores Runs| Postgres
    API -.->|OTLP Traces| OTel
    OTel --> Jaeger
    Prometheus -->|Scrapes /api/metrics| API
    Grafana -->|Queries| Prometheus
```

---

## Core Capabilities

1. **Multiplexed Live SSE Streaming**:
   - Single HTTP connection for all contenders, avoiding browser connection limits.
   - Centralized, strictly monotonic event sequence stamping (`0, 1, 2, ...`).
   - Failure resilience: model timeouts, crashes, or connection drops are isolated as data events without interrupting the race.
2. **Fairness Guarantees (Rule 6)**:
   - Identical request templates across all models; only the model identifier differs.
   - SHA-256 canonical context hashing: all contenders receive byte-for-byte identical RAG contexts.
3. **Hybrid RAG Pipeline**:
   - Dense vector similarity (`pgvector`) + lexical BM25 full-text search (`tsvector`).
   - Reciprocal Rank Fusion (RRF) with cross-encoder re-ranking via `flashrank`.
   - Anti-prompt-injection boundary delimiters isolating untrusted document evidence.
4. **Multi-Dimensional Evaluation & Cost Tracking**:
   - Deterministic evaluators: exact match, regex patterns, JSON schema validation.
   - Information retrieval metrics: Recall@K, Precision@K, and Mean Reciprocal Rank (MRR).
   - Blind LLM-as-judge: randomized contender labeling to eliminate brand and position bias.
   - Citation faithfulness: verifies `[S1]`, `[S2]` citation references against retrieved chunks.
   - Token-exact `Decimal` cost calculator based on published provider rates.
5. **Experiment Engine & Pareto Analysis**:
   - Versioned, immutable benchmark datasets.
   - Automated benchmark runner executing cases concurrently under global semaphore limits.
   - Trade-off analysis: interactive Pareto frontier scatter plots (Quality vs Latency vs Cost).
   - Automated CI quality regression gating on pull requests.
6. **Production Hardening (Phase 10)**:
   - Modern Argon2id password hashing via `pwdlib`.
   - JWT authentication (`pyjwt`) protecting state-changing and data-reading endpoints.
   - In-memory sliding-window rate limiting on race and document uploads.
   - OpenTelemetry distributed tracing across FastAPI, HTTPX, and SQLAlchemy into Jaeger.
   - Prometheus `/api/metrics` exposition and pre-provisioned Grafana dashboards.

---

## Quickstart & Setup Guide

### Prerequisites
- **Operating System**: Windows (PowerShell), macOS, or Linux
- **Python**: 3.12+
- **Node.js**: 24+
- **Docker & Docker Compose**: For PostgreSQL (pgvector) and Observability services

---

### Step 1: Clone the Repository & Configure Environment Variables
```powershell
git clone https://github.com/kartikwritescode/versus_lab.git
cd versus_lab

# Copy the API environment template
cp apps/api/.env.example apps/api/.env
```

Edit `apps/api/.env` with your preferred credentials. Default settings are pre-configured to work with **Mock and Local providers with zero paid API keys required**:
```env
# Optional cloud provider keys (leave as-is to test with Mock/Ollama)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
XAI_API_KEY=

# Database & Auth Defaults
DATABASE_URL=postgresql+asyncpg://versuslab:versuslab@localhost:5432/versuslab
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$argon2id$v=19$m=65536,t=3,p=4$ATMUOT3NjHGMGBi4yJ8Qjw$+N2Jdrzuej32NBq72GFqoRZnet8/RDYwBWZaphR4FCg
JWT_SECRET_KEY=versuslab-dev-jwt-secret-key-change-in-prod-must-be-long-and-secure
```
*(Default login credentials: `admin` / `versuslab123`)*

---

### Step 2: Start PostgreSQL (with pgvector) & Observability Services
```powershell
docker compose -f infra/docker-compose.yml up -d
```
This boots:
- PostgreSQL 17 with `pgvector` on port `5432`
- Jaeger Tracing on port `16686`
- OpenTelemetry Collector on ports `4317` (gRPC) / `4318` (HTTP)
- Prometheus on port `9090`
- Grafana on port `3001` (user: `admin`, password: `admin`)

---

### Step 3: Set up Backend & Run Database Migrations
```powershell
cd apps/api

# Create and activate Python virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Run Alembic migrations to create the database schema
alembic upgrade head

# Return to workspace root
cd ../..
```

---

### Step 4: Seed the Benchmark Dataset (Optional but Recommended)
Load the 24-question seed benchmark into PostgreSQL:
```powershell
apps\api\.venv\Scripts\python scripts/load_benchmark_dataset.py evals/datasets/seed_benchmark.json
```

---

### Step 5: Start the FastAPI Backend Server
```powershell
cd apps/api
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```
Backend API will be live at:
- **Interactive OpenAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)
- **Prometheus Metrics**: [http://localhost:8000/api/metrics](http://localhost:8000/api/metrics)

---

### Step 6: Start the Next.js Frontend Web Application
Open a new PowerShell terminal:
```powershell
cd apps/web
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Running in Local Production Mode (Docker)

To run the entire platform (API, Next.js Web, PostgreSQL, OTel Collector, Jaeger, Prometheus, and Grafana) inside multi-stage containers:

```powershell
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

Services are accessible at:
- **VersusLab Web App**: [http://localhost:3000](http://localhost:3000)
- **VersusLab Backend API**: [http://localhost:8000](http://localhost:8000)
- **Jaeger Distributed Tracing**: [http://localhost:16686](http://localhost:16686)
- **Prometheus Metrics Engine**: [http://localhost:9090](http://localhost:9090)
- **Grafana Dashboards**: [http://localhost:3001](http://localhost:3001)

---

## Testing & Verification

### Run the Hermetic Pytest Suite (69 Tests)
```powershell
cd apps/api
.venv\Scripts\pytest -v
```

### Run Code Linting (Ruff)
```powershell
cd apps/api
.venv\Scripts\ruff check .
```

### Run the Automated Load Test Benchmark
Exercises 1 baseline race and 10 concurrent races (50 simultaneous model streams) and measures p50/p95/p99 TTFT and latency:
```powershell
apps\api\.venv\Scripts\python scripts/load_test_races.py
```
Results are saved to [`docs/load-test-results.md`](docs/load-test-results.md).

### Run CI Quality Regression Gate against PostgreSQL
```powershell
apps\api\.venv\Scripts\python scripts/run_ci_regression.py
```

---

## User Interface

### 1. Multi-Model Live Streaming Race
*Live side-by-side multiplexed token streaming, nanosecond TTFT measurement, and usage tracking across Mock, Local, and Cloud providers.*

```text
+-------------------------------------------------------------------------------+
|  PROMPT: "Explain the difference between synchronous and async programming"   |
|  CONTENDERS: [Mock Fast]  [Claude 3.5 Haiku]  [GPT-4o Mini]  [Gemini 2.5]    |
+-------------------------------------------------------------------------------+
| Mock (Fast)           | Claude 3.5 Haiku      | GPT-4o Mini                   |
| Status: Completed     | Status: Streaming...  | Status: Completed             |
| TTFT: 48ms            | TTFT: 312ms           | TTFT: 245ms                   |
| Speed: 20.2 tok/s     | Speed: 62.4 tok/s     | Speed: 78.1 tok/s             |
| Cost: $0.000000       | Cost: $0.004800       | Cost: $0.003100               |
|                       |                       |                               |
| 1. Synchronous...     | 1. Synchronous...     | 1. Synchronous...             |
+-------------------------------------------------------------------------------+
```

### 2. Experiment Engine & Pareto Trade-Off Analysis
*Versioned benchmark evaluation runs comparing Quality Score vs Latency vs Cost with Pareto frontier highlighting.*

```text
+-------------------------------------------------------------------------------+
| EXPERIMENT: "Foundation Models vs Open Weights Baseline" (v1.0 - 24 Cases)    |
| Status: Finished (100%) | Cases: 24/24 | LLM Judge: GPT-4o-Mini               |
+-------------------------------------------------------------------------------+
| Model               | Mean Quality | Mean TTFT | Mean Latency | Total Cost    |
|---------------------|--------------|-----------|--------------|---------------|
| gpt-4o-mini         | 92.4%        | 210ms     | 1.42s        | $0.074        |
| claude-3-5-haiku    | 94.1%        | 285ms     | 1.28s        | $0.115        |
| gemini-2.5-flash    | 91.8%        | 195ms     | 1.15s        | $0.062        |
| ollama:qwen3:4b     | 82.5%        | 540ms     | 3.10s        | $0.000 (Free) |
+-------------------------------------------------------------------------------+
```

---

## What I Learned Across 10 Phases

Building VersusLab was an extensive engineering journey covering 50 core software concepts:

1. **Typed Protocols & Structural Subtyping**: Using Python's `Protocol` to define provider adapters (`ModelDelta` stream generator) without deep class hierarchies.
2. **Asynchronous Generators & Concurrency**: Yielding streaming deltas non-blockingly with `async for` and `asyncio.Queue`.
3. **Multiplexed SSE Streaming**: Merging independent async streams onto a single connection with monotonic sequence stamping.
4. **Failure Isolation ("Errors as Data")**: Never letting an individual model timeout or crash break an active user race.
5. **Idempotency & Safe Retry Policies**: Restricting connection retries strictly to the window *before* the first token arrives.
6. **Non-Blocking Persistence Trackers**: Recording race events into PostgreSQL in the background without blocking the live SSE pipe.
7. **Database Migrations with Alembic**: Evolving relational schemas reproducibly with version-controlled migration scripts.
8. **Dense Vector Embeddings & Cosine Distance**: Projecting semantic text into vector space using `pgvector` HNSW indexes.
9. **Lexical Full-Text Search (TSVector)**: Stemming and inverted index search with PostgreSQL native text search.
10. **Reciprocal Rank Fusion (RRF)**: Combining diverse search algorithm rank positions without arbitrary score normalizations.
11. **Cross-Encoder Reranking**: Using deep Transformer models (`FlashRank`) to rescore high-potential candidate passages.
12. **Prompt Injection Boundaries**: Treating retrieved documents as untrusted passive evidence wrapped in system delimiters.
13. **Deterministic Evaluators**: Scoring model answers hermetically via exact match, regex patterns, and JSON schema constraints.
14. **Information Retrieval Metrics**: Measuring search recall, precision, and Mean Reciprocal Rank (MRR).
15. **Blind LLM-as-Judge**: Eliminating evaluator bias by anonymizing contender labels and randomizing answer order.
16. **Citation Faithfulness Verification**: Detecting factual hallucinations by checking citations against retrieved chunks.
17. **Decimal Token Accounting**: Calculating sub-cent financial costs with exact fixed-point `Decimal` math.
18. **Immutable Benchmark Datasets**: Guaranteeing evaluation reproducibility by versioning test cases.
19. **Pareto Trade-Off Optimization**: Analyzing multi-dimensional trade-offs between speed, cost, and output intelligence.
20. **Automated CI Quality Regression Gates**: Blocking pull requests if model contenders drop below historical quality baselines.
21. **Argon2id Password Hashing**: Modern, memory-hard hashing resistant to GPU-accelerated cracking.
22. **JWT Bearer Authentication**: Stateless token verification with cryptographic signatures (`HS256`).
23. **Sliding-Window Rate Limiting**: Mitigating DoS attacks by tracking request timestamps across moving time windows.
24. **OpenTelemetry Distributed Tracing**: Exporting vendor-neutral OTLP traces across API, HTTPX, and database layers into Jaeger.
25. **Prometheus Metrics Architecture**: Emitting counters and histograms for statistical latency percentile analysis.
26. **Multi-Stage Container Builds**: Creating lean, secure Docker images running as non-root users (`appuser` UID 1000).

---

## License

MIT License. Designed and built by **Kartik** for experimentation, research, and portfolio demonstration.
