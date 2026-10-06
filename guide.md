# VersusLab — Step-by-Step Run Guide

This guide provides the exact step-by-step PowerShell commands to set up, run, seed, and test **VersusLab** on Windows.

---

## Prerequisites

Before starting, ensure you have the following installed on your machine:

1. **Python 3.12+**
   ```powershell
   python --version
   ```
2. **Node.js 24+** (and npm)
   ```powershell
   node --version
   npm --version
   ```
3. **Docker Desktop** (ensure Docker Desktop is running with WSL 2 or Hyper-V backend)
   ```powershell
   docker --version
   ```
4. **Git**
   ```powershell
   git --version
   ```
5. *(Optional)* **Ollama** (if running local open-weights models like `qwen3:8b` or `nomic-embed-text` embeddings)
   ```powershell
   ollama --version
   ```

---

## Quick Navigation

- [Option A: Standard Local Development Workflow (Recommended)](#option-a-standard-local-development-workflow-recommended)
  - [Step 1: Configure Environment Variables](#step-1-configure-environment-variables)
  - [Step 2: Start PostgreSQL & Observability Services](#step-2-start-postgresql--observability-services)
  - [Step 3: Setup Backend Virtual Environment & Migrations](#step-3-setup-backend-virtual-environment--migrations)
  - [Step 4: Seed Benchmark Dataset](#step-4-seed-the-benchmark-dataset-optional-but-recommended)
  - [Step 5: Start FastAPI Backend Server](#step-5-start-the-fastapi-backend-server)
  - [Step 6: Start Next.js Frontend Web App](#step-6-start-the-nextjs-frontend-web-application)
- [Option B: Full Containerized Stack (Docker Compose)](#option-b-full-containerized-stack-docker-compose)
- [Testing & Quality Verification](#testing--quality-verification)
- [Services & Ports Reference Table](#services--ports-reference-table)
- [Troubleshooting & Common Fixes](#troubleshooting--common-fixes)

---

## Option A: Standard Local Development Workflow (Recommended)

### Step 1: Configure Environment Variables

Open PowerShell and navigate to the project root directory:

```powershell
cd c:\files\programming\Python\projects\versus_lab
```

Copy the environment variable templates for both the backend and frontend:

```powershell
# Copy backend environment config
Copy-Item apps/api/.env.example apps/api/.env

# Copy frontend environment config
Copy-Item apps/web/.env.local.example apps/web/.env.local
```

> [!NOTE]
> **Zero Paid API Keys Required:** By default, VersusLab works immediately out of the box with built-in **Mock Providers** (`mock:fast`, `mock:slow`, `mock:broken`, `mock:stuck`).
>
> If you wish to benchmark cloud models, open `apps/api/.env` and paste your API keys:
> - `OPENAI_API_KEY=...`
> - `ANTHROPIC_API_KEY=...`
> - `GEMINI_API_KEY=...`
> - `XAI_API_KEY=...`
> - `DEEPSEEK_API_KEY=...`

---

### Step 2: Start PostgreSQL & Observability Services

Start the database (PostgreSQL with `pgvector`) and observability stack (OpenTelemetry Collector, Jaeger, Prometheus, Grafana) via Docker:

```powershell
docker compose -f infra/docker-compose.yml up -d
```

Verify that all containers are healthy and running:

```powershell
docker ps
```

You should see:
- `versuslab-postgres` (PostgreSQL 17 + pgvector mapped to **port 5433**)
- `versuslab-jaeger` (Jaeger Web UI on port 16686)
- `versuslab-otel-collector` (OTel Collector on ports 4317 / 4318)
- `versuslab-prometheus` (Prometheus Metrics on port 9090)
- `versuslab-grafana` (Grafana Dashboards on port 3001)

> [!IMPORTANT]
> PostgreSQL is mapped to host port **`5433`** by default (instead of `5432`) to avoid conflicts with any PostgreSQL instances already running on your machine.

---

### Step 3: Setup Backend Virtual Environment & Migrations

Navigate into `apps/api`, create the Python virtual environment, install dependencies, and apply database migrations:

```powershell
cd apps/api

# 1. Create Python virtual environment (if not already created)
python -m venv .venv

# 2. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 3. Upgrade pip and install backend dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Run database migrations with Alembic
alembic upgrade head

# 5. Return to workspace root
cd ../..
```

*(If PowerShell blocks script activation with an `ExecutionPolicy` error, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` then retry `.\.venv\Scripts\Activate.ps1`).*

---

### Step 4: Seed the Benchmark Dataset (Optional but Recommended)

Seed the 24-question benchmark dataset into PostgreSQL to enable instant evaluation runs and experiments:

```powershell
apps\api\.venv\Scripts\python scripts/load_benchmark_dataset.py evals/datasets/seed_benchmark.json
```

**Expected output:**
```text
Loaded 24 test cases from evals/datasets/seed_benchmark.json
Created dataset: id=... name=VersusLab Foundation Benchmark v1.0 version=1.0 (24 test cases)
```

---

### Step 5: Start the FastAPI Backend Server

Open **Terminal 1** and start the FastAPI backend:

```powershell
cd c:\files\programming\Python\projects\versus_lab\apps\api

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Launch backend with auto-reload
uvicorn app.main:app --reload --port 8000
```

Verify the backend is responding:
- **Interactive Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health) (returns `{"status":"ok"}`)
- **Prometheus Metrics**: [http://localhost:8000/api/metrics](http://localhost:8000/api/metrics)

---

### Step 6: Start the Next.js Frontend Web Application

Open a **second PowerShell terminal (Terminal 2)**:

```powershell
cd c:\files\programming\Python\projects\versus_lab\apps\web

# Install frontend dependencies
npm install

# Start development server
npm run dev
```

The web application is now live at:
👉 **[http://localhost:3000](http://localhost:3000)**

You can now:
1. **Run Live Races**: Select contenders (e.g., `Mock (Fast)`, `Mock (Slow)`), type a prompt, and watch side-by-side streaming with real-time TTFT and token throughput.
2. **Knowledge Base (RAG)**: Upload documents (`.txt`, `.md`, `.pdf`) and ask grounded questions.
3. **Experiment Engine**: Run benchmark datasets and inspect Pareto frontier trade-offs (Quality vs Speed vs Cost).

---

## Option B: Full Containerized Stack (Docker Compose)

If you prefer to run the entire system — including the FastAPI backend and Next.js frontend — inside Docker containers:

```powershell
cd c:\files\programming\Python\projects\versus_lab

# 1. Build and boot all containers
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

To view logs from all containers:
```powershell
docker compose -f docker-compose.prod.yml logs -f
```

To stop the container stack:
```powershell
docker compose -f docker-compose.prod.yml down
```

---

## Testing & Quality Verification

Run these commands from the root directory to verify code health and platform integrity:

### 1. Run Backend Hermetic Unit & Integration Tests (74 Tests)
```powershell
cd apps/api
.\.venv\Scripts\pytest -v
cd ../..
```
*All tests use mock providers and fakes — zero paid API credits or internet access required.*

### 2. Run Python Code Linter (Ruff)
```powershell
cd apps/api
.\.venv\Scripts\ruff check .
cd ../..
```

### 3. Run Automated Race Load Test
Simulates concurrent race workloads (measuring p50, p95, and p99 TTFT and throughput):
```powershell
# Ensure the backend server is running on port 8000 first
apps\api\.venv\Scripts\python scripts/load_test_races.py
```
*(Results are written to `docs/load-test-results.md`)*

### 4. Run CI Quality Regression Gate
Verifies evaluation baselines and detects model regressions against PostgreSQL:
```powershell
apps\api\.venv\Scripts\python scripts/run_ci_regression.py
```

---

## Services & Ports Reference Table

| Service | Address | Default Credentials / Notes |
| :--- | :--- | :--- |
| **VersusLab Web UI** | [http://localhost:3000](http://localhost:3000) | Next.js Frontend |
| **VersusLab Backend API** | [http://localhost:8000](http://localhost:8000) | FastAPI App |
| **OpenAPI / Swagger UI** | [http://localhost:8000/docs](http://localhost:8000/docs) | Interactive API Explorer |
| **API Health Check** | [http://localhost:8000/api/health](http://localhost:8000/api/health) | Liveness Probe |
| **Prometheus Metrics** | [http://localhost:8000/api/metrics](http://localhost:8000/api/metrics) | Operational Metrics |
| **PostgreSQL 17 (pgvector)** | `localhost:5433` | User: `versuslab`<br>Password: `versuslab`<br>Database: `versuslab` |
| **Jaeger Trace Explorer** | [http://localhost:16686](http://localhost:16686) | Distributed traces UI |
| **Prometheus UI** | [http://localhost:9090](http://localhost:9090) | Metric queries & targets |
| **Grafana Dashboards** | [http://localhost:3001](http://localhost:3001) | User: `admin`<br>Password: `admin` |
| **OpenTelemetry gRPC / HTTP** | Ports `4317` (gRPC), `4318` (HTTP) | Trace collector receiver |

---

## Troubleshooting & Common Fixes

### 1. PowerShell Script Execution Policy Error
If running `.\.venv\Scripts\Activate.ps1` gives:
> *cannot be loaded because running scripts is disabled on this system*

**Solution**:
Run this command in your PowerShell terminal to allow script execution for your session:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 2. PostgreSQL Connection Refused / Port Conflict
- VersusLab connects to PostgreSQL at **port 5433** (`postgresql+asyncpg://versuslab:versuslab@localhost:5433/versuslab`).
- Ensure the Docker container is running:
  ```powershell
  docker compose -f infra/docker-compose.yml up -d postgres
  ```
- Check logs if it fails to start:
  ```powershell
  docker logs versuslab-postgres
  ```

### 3. Using Ollama for Local Models
If you want to use local models with Ollama:
1. Start Ollama:
   ```powershell
   ollama serve
   ```
2. Pull the default chat and embedding models:
   ```powershell
   ollama pull qwen3:8b
   ollama pull nomic-embed-text
   ```
3. Set in `apps/api/.env`:
   ```env
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_CHAT_MODEL=qwen3:8b
   OLLAMA_EMBEDDING_MODEL=nomic-embed-text
   ```

### 4. Stopping All Local Infrastructure Cleanly
When you are done developing, stop the background Docker containers to free up system resources:
```powershell
docker compose -f infra/docker-compose.yml down
```
*(Add `-v` if you wish to wipe the volumes and start completely fresh: `docker compose -f infra/docker-compose.yml down -v`)*
