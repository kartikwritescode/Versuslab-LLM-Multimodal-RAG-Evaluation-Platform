# VersusLab Project Analysis & Fix Guide

**Date:** 2026-09-23  
**Analysis Type:** Comprehensive Project Review & Ollama Integration Diagnosis

---

## Executive Summary

Your VersusLab project is **well-architected** and follows the production guide closely. The codebase demonstrates solid engineering practices with proper provider abstraction, structured types, and observability setup. However, there are **critical missing components** preventing the system from functioning, and the Ollama integration has **configuration mismatches** that need to be resolved.

### Current Status: ⚠️ **Non-Functional** (Critical components missing)

---

## Table of Contents

1. [Project Architecture Assessment](#project-architecture-assessment)
2. [Critical Issues Blocking Functionality](#critical-issues-blocking-functionality)
3. [Ollama Integration Problems](#ollama-integration-problems)
4. [Missing Components Analysis](#missing-components-analysis)
5. [Configuration Issues](#configuration-issues)
6. [Recommended Fix Sequence](#recommended-fix-sequence)
7. [Testing Strategy](#testing-strategy)

---

## 1. Project Architecture Assessment

### ✅ What's Working Well

#### Strong Provider Abstraction
- **Protocol-based design** using `ModelProvider` interface
- **Consistent types** with `ModelRequest`, `ModelDelta`, `Usage`
- **Clean separation** between providers
- **Registry pattern** for provider management

#### Good Configuration Management
- **Pydantic Settings** with `.env` support
- **Sensible defaults** for all providers
- **Proper environment variable mapping**

#### Observability Infrastructure
- **OpenTelemetry** integration setup
- **Structured logging** with correlation IDs
- **Prometheus metrics** endpoints
- **Sentry** error tracking support

#### Production-Ready Docker Setup
- **Multi-container** docker-compose with all services
- **Health checks** for PostgreSQL
- **Proper networking** with service dependencies
- **Volume persistence** for data

### 📁 Project Structure

```
versuslab/
├── apps/
│   ├── api/                    ✅ Present
│   │   ├── app/
│   │   │   ├── api/           ✅ Routers defined
│   │   │   ├── core/          ✅ Config, metrics, telemetry
│   │   │   ├── providers/     ✅ All providers implemented
│   │   │   ├── race/          ⚠️  Coordinator exists
│   │   │   ├── retrieval/     ⚠️  Partial implementation
│   │   │   ├── evaluation/    ⚠️  Partial implementation
│   │   │   ├── db/            ⚠️  Models/service exist
│   │   │   └── main.py        ✅ FastAPI app configured
│   │   └── tests/             ✅ Test structure present
│   │
│   └── web/                   ❌ NOT FOUND - Next.js frontend missing
│
├── infra/                     ✅ Docker infrastructure
├── docker-compose.prod.yml    ✅ Production setup
└── .env                       ⚠️  Minimal configuration
```

---

## 2. Critical Issues Blocking Functionality

### Issue #1: ❌ **Missing Next.js Frontend** (BLOCKER)

**Severity:** CRITICAL  
**Impact:** Cannot run the application

The `apps/web/` directory is **completely missing**. The docker-compose expects a Next.js frontend but it doesn't exist.

**Evidence:**
```yaml
# docker-compose.prod.yml line 59-70
web:
  build:
    context: ./apps/web    # ← This directory doesn't exist
    dockerfile: Dockerfile
```

**Fix Required:**
- Create complete Next.js application in `apps/web/`
- Implement live race UI with SSE streaming
- Build model comparison dashboard
- Implement document upload interface

---

### Issue #2: ⚠️ **Incomplete Race Coordinator Implementation**

**Severity:** HIGH  
**Impact:** Core race functionality may not work

While the race coordinator exists (`app/race/coordinator.py`), it needs verification for:
- Concurrent model execution with `asyncio.gather`
- Failure isolation (one model failure shouldn't kill the race)
- Timeout handling per model
- Cancellation support
- SSE multiplexing

**Action Required:** Verify implementation completeness

---

### Issue #3: ⚠️ **Partial RAG Implementation**

**Severity:** HIGH  
**Impact:** Document-based queries won't work properly

The retrieval system has components but may be incomplete:
- ✅ Hybrid retrieval interface exists
- ✅ Context canonicalization present
- ⚠️ Document ingestion pipeline status unknown
- ⚠️ Embedding generation unclear
- ⚠️ Reranking implementation unclear
- ❌ Chunking strategy not visible

**Action Required:** Complete RAG pipeline implementation

---

### Issue #4: ⚠️ **Database Schema & Migrations Missing**

**Severity:** HIGH  
**Impact:** Cannot persist any data

While database models exist in `app/db/models.py`, there's no evidence of:
- Alembic migrations setup
- Initial schema creation scripts
- Database initialization process

**Action Required:** 
- Setup Alembic
- Create initial migration
- Add database initialization to startup

---

## 3. Ollama Integration Problems

### Problem #1: 🔴 **Configuration Mismatch**

**Root Cause:** Environment variable inconsistency

Your `.env` file has:
```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen3:4b
```

But `config.py` defaults to:
```python
ollama_chat_model: str = "qwen3:8b"  # ← Expects 8b variant
```

**Why This Breaks Ollama:**
- If `qwen3:4b` isn't pulled to Ollama, requests will fail
- If `.env` isn't loaded properly, it defaults to `qwen3:8b`
- Model naming must match exactly what Ollama has

**Fix:**
```bash
# Either pull the 4b model:
ollama pull qwen3:4b

# Or update .env to use 8b:
OLLAMA_CHAT_MODEL=qwen3:8b
ollama pull qwen3:8b
```

---

### Problem #2: 🟡 **Docker Network Configuration**

**Issue:** Docker containers can't reach host Ollama

In `docker-compose.prod.yml` line 51:
```yaml
OLLAMA_BASE_URL: ${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
```

**Why This Might Fail:**
- `host.docker.internal` works on **Docker Desktop** (Mac/Windows)
- Does **NOT** work on **Linux Docker** by default
- If Ollama runs on host, containers can't reach `localhost:11434`

**Fix for Linux:**
```yaml
# Option 1: Use host network mode (Linux)
network_mode: "host"

# Option 2: Add extra_hosts mapping
extra_hosts:
  - "host.docker.internal:host-gateway"

# Option 3: Use actual host IP
OLLAMA_BASE_URL: http://192.168.1.x:11434
```

**Fix for Development:**
Update `.env`:
```env
# When running API locally (not in Docker)
OLLAMA_BASE_URL=http://localhost:11434

# When running API in Docker on Linux
OLLAMA_BASE_URL=http://172.17.0.1:11434

# When running API in Docker on Mac/Windows
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

---

### Problem #3: 🟡 **Ollama Service Not Running**

**Check:** Verify Ollama is actually running

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Expected response: JSON list of models
# If connection refused: Ollama isn't running
```

**Fix:**
```bash
# Start Ollama
ollama serve

# Verify models are pulled
ollama list

# Pull required models if missing
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

---

### Problem #4: 🔴 **Missing Error Handling for Offline Ollama**

**Issue:** If Ollama is down, the provider initialization succeeds but requests fail

The `OllamaProvider` is instantiated at import time:
```python
# registry.py line 17
"ollama": OllamaProvider(settings.ollama_base_url, think=settings.ollama_think),
```

**Impact:**
- No validation that Ollama is reachable
- Cryptic errors when requests fail
- Hard to diagnose for users

**Recommended Fix:**
Add a health check endpoint or startup validation:

```python
# Add to api/race.py or main.py startup
async def validate_ollama():
    """Check if Ollama is reachable on startup."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            if response.status_code == 200:
                logger.info("Ollama connection validated")
            else:
                logger.warning("Ollama returned status %d", response.status_code)
    except Exception as e:
        logger.error("Cannot connect to Ollama: %s", e)
```

---

## 4. Missing Components Analysis

### 4.1 Frontend Application ❌

**Missing:** Entire `apps/web/` directory

**Required Components:**
- Next.js 14+ with App Router
- TypeScript configuration
- TailwindCSS + shadcn/ui
- SSE client for streaming
- Race UI with live model columns
- Document upload interface
- Experiment dashboard
- Charts (Recharts/ECharts)

**Estimated Effort:** 3-5 days for MVP

---

### 4.2 Database Migrations ❌

**Missing:** Alembic setup and migrations

**Required:**
```bash
apps/api/
  └── alembic/
      ├── versions/
      │   └── 001_initial_schema.py
      ├── env.py
      └── alembic.ini
```

**Fix:**
```bash
cd apps/api
pip install alembic
alembic init alembic
# Create initial migration
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

---

### 4.3 Document Ingestion Pipeline ⚠️

**Status:** Unclear implementation

**Required Components:**
- PDF/DOCX/TXT parsing
- Chunking strategy (structure-aware)
- Embedding generation
- Vector storage in pgvector
- Content hashing for idempotency

**Verification Needed:**
- Check `app/api/documents.py` completeness
- Verify chunking implementation
- Test embedding generation
- Validate pgvector integration

---

### 4.4 Evaluation Engine ⚠️

**Status:** Partial implementation visible

**Required Components:**
- ✅ Citation faithfulness evaluator (exists)
- ✅ Blind judge (exists)  
- ✅ Cost calculation (exists)
- ⚠️ Quality metrics (unclear)
- ⚠️ Grounding verification (unclear)
- ⚠️ Retrieval metrics (unclear)

---

## 5. Configuration Issues

### Issue 5.1: Multiple `.env` Files

**Problem:** Configuration scattered across locations

Found `.env` files at:
- `/versus_lab/.env` (root, only 2 lines)
- Expected: `/versus_lab/apps/api/.env`

**Impact:**
- Settings may not load correctly
- Different values between local/docker
- Hard to maintain consistency

**Fix:**
Create comprehensive `.env` at project root:

```env
# === Ollama Configuration ===
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen3:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_THINK=false

# === Database Configuration ===
POSTGRES_USER=versuslab
POSTGRES_PASSWORD=versuslab
POSTGRES_DB=versuslab
POSTGRES_PORT=5433
DATABASE_URL=postgresql+asyncpg://versuslab:versuslab@localhost:5433/versuslab

# === Provider API Keys ===
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
XAI_API_KEY=...
DEEPSEEK_API_KEY=...

# === Security ===
JWT_SECRET_KEY=your-secret-key-change-in-production
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$argon2id$v=19$m=65536,t=3,p=4$...
AUTH_ENABLED=false

# === Observability ===
OTEL_ENABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
SENTRY_DSN=
```

---

### Issue 5.2: Port Conflicts

**Problem:** PostgreSQL on non-standard port

```python
# config.py line 54
database_url: str = "postgresql+asyncpg://versuslab:versuslab@localhost:5433/versuslab"
```

**Why:** Avoiding conflict with system PostgreSQL on 5432

**Validation Required:**
- Ensure docker-compose exposes 5433
- Check `docker-compose.prod.yml` line 17 ✅ (correct)
- Verify local connection works

---

## 6. Recommended Fix Sequence

### Phase 1: Verify Ollama (IMMEDIATE) ⚡

**Goal:** Get Ollama working in isolation

```bash
# 1. Ensure Ollama is running
ollama serve

# 2. Verify in another terminal
curl http://localhost:11434/api/tags

# 3. Pull the correct model
ollama pull qwen3:8b  # Match config.py default
ollama pull nomic-embed-text

# 4. Test model works
ollama run qwen3:8b "Hello, how are you?"

# 5. Verify embedding model
ollama run nomic-embed-text "test"
```

**Success Criteria:** ✅ Ollama responds to all commands

---

### Phase 2: Fix Configuration (30 minutes)

```bash
# 1. Update root .env
cat > .env << 'EOF'
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen3:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
DATABASE_URL=postgresql+asyncpg://versuslab:versuslab@localhost:5433/versuslab
POSTGRES_PORT=5433
EOF

# 2. Copy to api directory
cp .env apps/api/.env

# 3. Test config loading
cd apps/api
python -c "from app.core.config import settings; print(f'Ollama: {settings.ollama_base_url}, Model: {settings.ollama_chat_model}')"
```

**Success Criteria:** ✅ Config loads correctly

---

### Phase 3: Setup Database (1 hour)

```bash
# 1. Start PostgreSQL
docker-compose -f docker-compose.prod.yml up -d postgres

# 2. Wait for health check
docker-compose -f docker-compose.prod.yml ps

# 3. Install Alembic in API
cd apps/api
pip install alembic

# 4. Initialize Alembic
alembic init alembic

# 5. Configure alembic.ini to use async
# Edit: sqlalchemy.url = postgresql+asyncpg://...

# 6. Create initial migration
alembic revision --autogenerate -m "Initial schema"

# 7. Apply migration
alembic upgrade head

# 8. Verify tables created
docker exec -it versuslab-prod-postgres psql -U versuslab -d versuslab -c "\dt"
```

**Success Criteria:** ✅ Database schema created

---

### Phase 4: Test API Backend (1 hour)

```bash
# 1. Install dependencies
cd apps/api
pip install -r requirements.txt  # or setup via pyproject.toml

# 2. Start API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Test health endpoint
curl http://localhost:8000/api/health

# 4. Test Ollama provider
curl -X POST http://localhost:8000/api/race/stream \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Say hello in one sentence",
    "models": ["ollama"],
    "temperature": 0.7
  }'

# 5. Watch for SSE streaming response
```

**Success Criteria:** ✅ API responds and streams from Ollama

---

### Phase 5: Build Next.js Frontend (3-5 days)

**This is the biggest missing piece. High-level plan:**

```bash
# 1. Create Next.js app
cd apps/
npx create-next-app@latest web --typescript --tailwind --app --src-dir

# 2. Install dependencies
cd web
npm install @tanstack/react-query eventsource recharts shadcn-ui

# 3. Create pages:
# - app/page.tsx - Live race UI
# - app/race/[id]/page.tsx - Race detail
# - app/documents/page.tsx - Document management
# - app/experiments/page.tsx - Experiment tracking

# 4. Implement SSE client
# - lib/sse-client.ts - EventSource wrapper
# - hooks/useRaceStream.ts - Race streaming hook

# 5. Build UI components
# - components/ModelColumn.tsx - Live model output
# - components/MetricsPanel.tsx - TTFT, latency, cost
# - components/RaceControls.tsx - Start/stop race
```

**Estimated Time:** 3-5 days for functional MVP

---

### Phase 6: Integration Testing (1 day)

```bash
# 1. Test full stack
docker-compose -f docker-compose.prod.yml up --build

# 2. Verify all services healthy
docker-compose -f docker-compose.prod.yml ps

# 3. Test race with Ollama
# Open browser: http://localhost:3000
# Create race with ollama:qwen3:8b

# 4. Test with multiple providers
# Add OpenAI key, test race with ollama + openai

# 5. Test document upload (if RAG complete)
# Upload PDF, create race with document context
```

---

## 7. Testing Strategy

### Unit Tests ✅ (Partial)

Found test files:
- `tests/test_ollama_provider.py` ✅
- `tests/test_evaluations.py` ✅

**Run Tests:**
```bash
cd apps/api
pytest tests/ -v
```

**Expected Failures:**
- Database tests (schema not created)
- RAG tests (if incomplete)
- Provider tests needing API keys

---

### Integration Tests (Need Creation)

**Test Ollama Integration:**

```python
# tests/integration/test_ollama_live.py
import pytest
from app.providers.ollama import OllamaProvider
from app.providers.types import Message, ModelRequest

@pytest.mark.asyncio
async def test_ollama_streaming():
    provider = OllamaProvider("http://localhost:11434")
    request = ModelRequest(
        model="qwen3:8b",
        messages=[Message(role="user", content="Say 'test' and nothing else")],
        temperature=0.0,
    )
    
    chunks = []
    async for delta in provider.stream(request):
        chunks.append(delta)
    
    assert len(chunks) > 0
    text = "".join(d.text or "" for d in chunks if d.text)
    assert "test" in text.lower()
```

**Run:**
```bash
pytest tests/integration/ -v -s
```

---

### Load Testing (Future)

Once system is functional:

```bash
# Install k6 or locust
k6 run load-tests/race-test.js

# Test scenarios:
# - 1 race, 4 models
# - 10 concurrent races
# - Measure TTFT, latency, error rate
```

---

## 8. Diagnostic Commands

### Check Ollama Status

```bash
# Is Ollama running?
curl http://localhost:11434/api/tags

# List pulled models
ollama list

# Test model inference
ollama run qwen3:8b "test"

# Check Ollama logs
journalctl -u ollama -f  # if systemd service
```

---

### Check Docker Services

```bash
# Start services
docker-compose -f docker-compose.prod.yml up -d

# Check status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f api
docker-compose -f docker-compose.prod.yml logs -f postgres

# Test database connection
docker exec -it versuslab-prod-postgres psql -U versuslab -d versuslab -c "SELECT version();"
```

---

### Check API Health

```bash
# Health check
curl http://localhost:8000/api/health

# Metrics
curl http://localhost:8000/api/metrics

# Test race (if API running)
curl -X POST http://localhost:8000/api/race/stream \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Count to 5",
    "models": ["ollama"],
    "temperature": 0.7
  }'
```

---

## 9. Quick Win: Test Ollama Provider in Isolation

**Create a minimal test script to verify Ollama works:**

```python
# test_ollama_direct.py
import asyncio
from app.providers.ollama import OllamaProvider
from app.providers.types import Message, ModelRequest

async def main():
    print("Testing Ollama provider...")
    provider = OllamaProvider("http://localhost:11434")
    
    request = ModelRequest(
        model="qwen3:8b",
        messages=[Message(role="user", content="Say hello in one sentence")],
        temperature=0.7,
    )
    
    print("\nStreaming response:")
    async for delta in provider.stream(request):
        if delta.text:
            print(delta.text, end="", flush=True)
        if delta.finish_reason:
            print(f"\n\nFinished: {delta.finish_reason}")
            print(f"Tokens: {delta.usage}")

if __name__ == "__main__":
    asyncio.run(main())
```

**Run:**
```bash
cd apps/api
python test_ollama_direct.py
```

**Expected Output:**
```
Testing Ollama provider...

Streaming response:
Hello! I'm doing well, thank you for asking.

Finished: stop
Tokens: input_tokens=15 output_tokens=12
```

**If this fails, Ollama integration is definitely broken.**

---

## 10. Summary of Changes Needed

### Immediate (Ollama Fix)

1. ✅ **Pull correct model:** `ollama pull qwen3:8b`
2. ✅ **Fix .env:** Match model name in config
3. ✅ **Verify Ollama running:** `curl localhost:11434/api/tags`
4. ✅ **Test provider:** Run `test_ollama_direct.py`

### Short-term (Make API Functional)

5. ⚠️ **Setup database:** Alembic migrations
6. ⚠️ **Complete RAG pipeline:** Document ingestion, embeddings
7. ⚠️ **Verify race coordinator:** Test concurrent streaming
8. ⚠️ **Add startup validation:** Check Ollama/DB on startup

### Medium-term (Full System)

9. ❌ **Build Next.js frontend:** Complete web UI (3-5 days)
10. ⚠️ **Complete evaluation engine:** All metrics
11. ⚠️ **Integration testing:** End-to-end tests
12. ⚠️ **Production deployment:** Docker compose with all services

---

## 11. Key Findings

### ✅ What's Good

1. **Excellent architecture** - Provider abstraction is production-grade
2. **Clean code** - Type hints, Pydantic models, proper error handling
3. **Observability ready** - OpenTelemetry, Prometheus, structured logging
4. **Docker setup** - Comprehensive production-like environment
5. **Ollama provider** - Implementation looks solid

### ⚠️ What's Incomplete

1. **Frontend missing** - No Next.js app (biggest blocker)
2. **Database migrations** - No Alembic setup
3. **RAG pipeline** - Unclear completion status
4. **Evaluation** - Partial implementation
5. **Documentation** - No README with setup instructions

### 🔴 What's Broken (Ollama Specific)

1. **Model mismatch** - .env has `qwen3:4b`, config expects `qwen3:8b`
2. **Docker networking** - `host.docker.internal` may not work on Linux
3. **No validation** - API starts even if Ollama is down
4. **Error messages** - Hard to diagnose Ollama connection issues

---

## 12. Estimated Timeline to Working System

| Phase | Task | Time | Priority |
|-------|------|------|----------|
| 1 | Fix Ollama configuration | 30 min | 🔴 CRITICAL |
| 2 | Test Ollama provider works | 15 min | 🔴 CRITICAL |
| 3 | Setup database migrations | 1 hour | 🔴 CRITICAL |
| 4 | Verify API backend | 1 hour | 🔴 CRITICAL |
| 5 | Build Next.js frontend MVP | 3-5 days | 🔴 CRITICAL |
| 6 | Complete RAG pipeline | 2-3 days | 🟡 HIGH |
| 7 | Complete evaluation engine | 1-2 days | 🟡 HIGH |
| 8 | Integration testing | 1 day | 🟡 HIGH |
| 9 | Production deployment | 1 day | 🟢 MEDIUM |
| 10 | Documentation | 1 day | 🟢 MEDIUM |

**Total: ~2 weeks for fully functional system**

---

## 13. Next Steps

### Right Now (Next 30 minutes)

1. Run diagnostic commands above
2. Fix Ollama model mismatch
3. Test `test_ollama_direct.py` script
4. Verify API health endpoint works

### Today (Next 2-3 hours)

1. Setup Alembic and database schema
2. Start PostgreSQL in Docker
3. Run API and test basic race endpoint
4. Confirm Ollama integration works end-to-end

### This Week

1. Build Next.js frontend MVP
2. Implement live race UI
3. Complete RAG pipeline
4. End-to-end testing

---

## Conclusion

Your VersusLab project has **excellent architectural foundations** but is currently **non-functional** due to:

1. 🔴 **Missing Next.js frontend** (complete blocker)
2. 🟡 **Ollama configuration mismatch** (easy fix)
3. 🟡 **Missing database setup** (1 hour fix)
4. 🟡 **Incomplete RAG/evaluation** (needs completion)

**The Ollama provider implementation itself is solid.** The issues are configuration and environment setup, not code bugs.

**Immediate action:** Follow Phase 1-4 of the fix sequence to get the backend + Ollama working. The frontend is the biggest remaining piece of work.

---

**Generated:** 2026-09-23  
**Project:** VersusLab Production LLM Evaluation Platform  
**Status:** Architecture ✅ | Backend ⚠️ | Frontend ❌ | Ollama 🟡
