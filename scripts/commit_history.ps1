# VersusLab - Sequential Conventional Commit Script
# Executes atomic, phase-aligned commits across the repository.

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🚀 VersusLab - Starting Sequential Commit Pipeline" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# -----------------------------------------------------------------------------
# Step 0: Ensure runtime log files are ignored
# -----------------------------------------------------------------------------
Write-Host "`n[0/13] Updating .gitignore..." -ForegroundColor Yellow
$gitignoreContent = Get-Content -Raw .gitignore
if ($gitignoreContent -notmatch "versuslab-api\.log") {
    Add-Content -Path .gitignore -Value "`n# Logs`n*.log`nversuslab-api.log`n"
}
git add .gitignore

# -----------------------------------------------------------------------------
# Commit 1: Architecture Restructuring & Provider Abstraction (Phase 1)
# -----------------------------------------------------------------------------
Write-Host "[1/13] Committing Phase 1: Provider Architecture & Restructuring..." -ForegroundColor Yellow
git rm -rf --ignore-unmatch apps/providers apps/api/app/__pycache__ apps/api/app/poviders apps/api/stream.py 2>$null

git add `
  .gitignore `
  apps/api/requirements.txt `
  apps/api/.env.example `
  apps/api/app/api/__init__.py `
  apps/api/app/core/config.py `
  apps/api/app/providers/__init__.py `
  apps/api/app/providers/types.py `
  apps/api/app/providers/base.py `
  apps/api/app/providers/mock.py `
  apps/api/app/providers/ollama.py `
  apps/api/app/providers/registry.py `
  apps/api/tests/__init__.py `
  apps/api/tests/conftest.py `
  apps/api/tests/test_mock_provider.py `
  apps/api/tests/test_ollama_provider.py `
  apps/api/tests/test_health.py

git commit -m "refactor(core): standardize provider architecture and clean repository structure" -m "- Restructure providers under apps/api/app/providers/
- Define typed ModelProvider protocol, ModelRequest, and ModelDelta models
- Implement MockProvider and local OllamaProvider with registry discovery
- Add environment configuration via pydantic-settings
- Remove accidental cache binaries and add test suite for core providers"

# -----------------------------------------------------------------------------
# Commit 2: Concurrent Race Coordinator & Failure Isolation (Phase 2)
# -----------------------------------------------------------------------------
Write-Host "[2/13] Committing Phase 2: Concurrent Race Coordinator & SSE..." -ForegroundColor Yellow
git add `
  apps/api/app/race/events.py `
  apps/api/app/race/coordinator.py `
  apps/api/app/api/race.py `
  apps/api/tests/test_race.py `
  apps/api/tests/test_coordinator_direct.py

git commit -m "feat(race): implement concurrent race coordinator and multiplexed SSE protocol" -m "- Coordinate simultaneous model execution over an asyncio queue
- Stamp strict sequence numbers centrally in run_race
- Implement failure isolation: model errors do not crash concurrent contenders
- Add TTFT and total latency observation
- Add unit tests for multi-model concurrency and edge-case failure paths"

# -----------------------------------------------------------------------------
# Commit 3: Cloud LLM Providers & Resilient Concurrency (Phase 3)
# -----------------------------------------------------------------------------
Write-Host "[3/13] Committing Phase 3: Cloud LLM Providers..." -ForegroundColor Yellow
git add `
  apps/api/app/providers/openai.py `
  apps/api/app/providers/anthropic.py `
  apps/api/app/providers/gemini.py `
  apps/api/app/providers/grok.py `
  apps/api/app/providers/deepseek.py `
  apps/api/tests/test_cloud_providers.py

git commit -m "feat(providers): add cloud LLM providers with retry handling and rate safeguards" -m "- Implement OpenAI, Anthropic Claude, Google Gemini, xAI Grok, and DeepSeek providers
- Normalize streaming chunks into unified ModelDelta format with token usage
- Integrate exponential backoff retries for transient HTTP/socket failures
- Add comprehensive mock test suite for all cloud model streaming responses"

# -----------------------------------------------------------------------------
# Commit 4: Next.js Live Streaming Arena Frontend (Phase 4)
# -----------------------------------------------------------------------------
Write-Host "[4/13] Committing Phase 4: Next.js Live Streaming Arena..." -ForegroundColor Yellow
git add `
  apps/web/package.json `
  apps/web/package-lock.json `
  apps/web/tsconfig.json `
  apps/web/next.config.ts `
  apps/web/postcss.config.mjs `
  apps/web/eslint.config.mjs `
  apps/web/.env.local.example `
  apps/web/.gitignore `
  apps/web/README.md `
  apps/web/AGENTS.md `
  apps/web/CLAUDE.md `
  apps/web/public/ `
  apps/web/lib/types.ts `
  apps/web/lib/race-client.ts `
  apps/web/app/layout.tsx `
  apps/web/app/page.tsx `
  apps/web/app/globals.css `
  apps/web/app/favicon.ico

git commit -m "feat(web): build Next.js live streaming arena with RAF batching and dual cancellation" -m "- Scaffold Next.js App Router frontend with Tailwind CSS
- Implement SSE multiplexed client parsing single-stream multi-model events
- Add requestAnimationFrame batching for high-throughput 60fps token rendering
- Add real-time contender cards showing live TTFT, latency, and token metrics
- Support two-sided race cancellation (client abort signal & backend task cleanup)"

# -----------------------------------------------------------------------------
# Commit 5: PostgreSQL Persistence & Experiment History (Phase 5)
# -----------------------------------------------------------------------------
Write-Host "[5/13] Committing Phase 5: PostgreSQL Persistence & Alembic..." -ForegroundColor Yellow
git add `
  apps/api/alembic.ini `
  apps/api/migrations/env.py `
  apps/api/migrations/script.py.mako `
  apps/api/migrations/versions/001_initial_races_and_model_runs.py `
  apps/api/app/db/ `
  apps/api/tests/test_persistence.py `
  apps/web/app/history/page.tsx

git commit -m "feat(db): add asynchronous PostgreSQL persistence and experiment history UI" -m "- Set up SQLAlchemy 2.0 async engine and Alembic migration framework
- Create schema for races, model runs, token usage, and latency records
- Implement non-blocking background event tracking without degrading SSE throughput
- Add /history endpoint and Next.js past races dashboard
- Add test coverage for persistence layer and database rollback handling"

# -----------------------------------------------------------------------------
# Commit 6: Vector RAG with pgvector & Ollama Embeddings (Phase 6)
# -----------------------------------------------------------------------------
Write-Host "[6/13] Committing Phase 6: Vector RAG & pgvector..." -ForegroundColor Yellow
git add `
  apps/api/migrations/versions/002_add_pgvector_and_documents.py `
  apps/api/app/providers/embeddings.py `
  apps/api/app/retrieval/__init__.py `
  apps/api/app/retrieval/chunking.py `
  apps/api/app/retrieval/basic.py `
  apps/api/app/retrieval/context.py `
  apps/api/app/api/documents.py `
  apps/api/tests/test_rag.py

git commit -m "feat(rag): add pgvector document retrieval and embedding pipeline" -m "- Add Alembic migration for pgvector extension and document chunk tables
- Implement embedding provider abstraction targeting Ollama nomic-embed-text
- Add deterministic paragraph chunking and SHA-256 content deduplication
- Implement canonical context injection into shared race template
- Add document upload endpoint and RAG integration tests"

# -----------------------------------------------------------------------------
# Commit 7: Trustworthy RAG: Hybrid Search, Reranking & Citations (Phase 7)
# -----------------------------------------------------------------------------
Write-Host "[7/13] Committing Phase 7: Advanced Trustworthy RAG..." -ForegroundColor Yellow
git add `
  apps/api/migrations/versions/003_add_context_hash_and_citations.py `
  apps/api/app/retrieval/hybrid.py `
  apps/api/app/retrieval/rerank.py `
  apps/api/app/evaluation/citation_check.py `
  apps/api/app/evaluation/citation_faithfulness.py `
  apps/api/tests/test_hybrid_retrieval.py `
  apps/api/tests/fixtures/adversarial_injection.txt `
  evals/fixtures/gold_retrieval_set.json

git commit -m "feat(rag): implement hybrid search, cross-encoder reranking and citation verification" -m "- Combine vector similarity and full-text search using Reciprocal Rank Fusion (RRF)
- Integrate cross-encoder reranker for precision passage filtering
- Guarantee race fairness with SHA-256 context hashing across contenders
- Add citation verification and faithfulness scoring against source chunks
- Enforce prompt injection defense by treating ingested documents as untrusted data"

# -----------------------------------------------------------------------------
# Commit 8: Multi-Model Evaluation Framework & Cost Engine (Phase 8)
# -----------------------------------------------------------------------------
Write-Host "[8/13] Committing Phase 8: Multi-Model Evaluation & Costs..." -ForegroundColor Yellow
git add `
  apps/api/migrations/versions/004_add_evaluations_and_costs.py `
  apps/api/app/evaluation/__init__.py `
  apps/api/app/evaluation/cost.py `
  apps/api/app/evaluation/deterministic.py `
  apps/api/app/evaluation/judge.py `
  apps/api/app/evaluation/metrics.py `
  apps/api/app/evaluation/retrieval_metrics.py `
  apps/api/tests/test_evaluations.py

git commit -m "feat(eval): introduce multi-model evaluation framework, LLM judge and token cost engine" -m "- Implement LLM-as-a-judge evaluation with structured rubrics and calibration
- Add deterministic evaluators for JSON schema validity, latency, and regex matching
- Implement per-token cost calculation across all provider pricing tiers
- Add evaluation schema migration and automated evaluation test suite"

# -----------------------------------------------------------------------------
# Commit 9: Benchmark Experiment Engine & CI Regression Gating (Phase 9)
# -----------------------------------------------------------------------------
Write-Host "[9/13] Committing Phase 9: Benchmark Experiments & CI Gating..." -ForegroundColor Yellow
git add `
  apps/api/migrations/versions/005_add_experiments_and_benchmarks.py `
  apps/api/app/experiments/ `
  apps/api/app/api/experiments.py `
  apps/api/tests/test_experiments.py `
  evals/datasets/seed_benchmark.json `
  evals/baselines/ci_baseline.json `
  scripts/run_ci_regression.py `
  scripts/load_benchmark_dataset.py `
  .github/workflows/regression.yml `
  apps/web/app/experiments/

git commit -m "feat(experiments): add benchmark runner, Pareto tradeoff analysis and CI regression gating" -m "- Implement automated experiment runner across versioned benchmark datasets
- Compute Pareto-optimal tradeoff frontiers (cost vs quality vs latency)
- Add Next.js benchmark dashboard and experiment drill-down views
- Add GitHub Actions CI workflow with quality regression gating against baseline"

# -----------------------------------------------------------------------------
# Commit 10: Production Hardening, Observability & Security (Phase 10)
# -----------------------------------------------------------------------------
Write-Host "[10/13] Committing Phase 10: Infrastructure, Observability & Security..." -ForegroundColor Yellow
git add `
  apps/api/Dockerfile `
  apps/web/Dockerfile `
  docker-compose.prod.yml `
  infra/ `
  apps/api/app/core/logging.py `
  apps/api/app/core/metrics.py `
  apps/api/app/core/rate_limit.py `
  apps/api/app/core/telemetry.py `
  apps/api/app/core/auth.py `
  apps/api/app/api/auth.py `
  apps/api/app/main.py `
  apps/api/tests/test_auth_and_security.py `
  apps/api/tests/test_metrics_and_observability.py `
  scripts/locustfile.py `
  scripts/load_test_races.py `
  docs/architecture.md `
  docs/load-test-results.md

git commit -m "feat(infra): add containerization, OpenTelemetry, Prometheus metrics and security controls" -m "- Multi-stage Dockerfiles for API and web with production Docker Compose stack
- Export Prometheus metrics for TTFT, request latency, and race throughput
- Set up OpenTelemetry distributed tracing across FastAPI, HTTPX, and SQLAlchemy
- Add structured JSON logging with correlation IDs and in-memory rate limiting
- Provide Locust load test scripts and baseline performance benchmarks"

# -----------------------------------------------------------------------------
# Commit 11: UI Redesign, Ollama Stream Diagnostics & Document Hub (Phase 11)
# -----------------------------------------------------------------------------
Write-Host "[11/13] Committing Phase 11: Document Hub & Ollama Diagnostics..." -ForegroundColor Yellow
git add `
  apps/web/app/components/DocumentManager.tsx `
  apps/api/test_ollama_direct.py

git commit -m "feat(ui): add interactive drag-and-drop document hub and streaming diagnostics" -m "- Build DocumentManager component with live status, file upload, and chunk inspection
- Add test_ollama_direct.py CLI diagnostic tool for local model latency and streaming
- Improve race arena layout and responsiveness for local and cloud models"

# -----------------------------------------------------------------------------
# Commit 12: Head-to-Head Comparison & Enhanced Metrics (Phase 12)
# -----------------------------------------------------------------------------
Write-Host "[12/13] Committing Phase 12: Head-to-Head Comparison & Radar Charts..." -ForegroundColor Yellow
git add `
  apps/api/migrations/versions/006_add_enhanced_metrics.py `
  apps/api/tests/test_enhanced_metrics.py `
  apps/web/app/history/[race_id]/page.tsx

git commit -m "feat(analytics): introduce contender comparison dashboard with radar and latency metrics" -m "- Add migration 006 for enhanced metrics storage and model comparison data
- Build head-to-head comparison dashboard in /history/[race_id]
- Display multi-dimensional performance radar charts and TTFT vs throughput tradeoffs
- Add unit tests for enhanced metrics calculation and aggregator functions"

# -----------------------------------------------------------------------------
# Commit 13: Project Documentation, Run Scripts & Developer Guides
# -----------------------------------------------------------------------------
Write-Host "[13/13] Committing Phase 13: Complete Documentation & Automation..." -ForegroundColor Yellow
git add `
  AGENTS.md `
  README.md `
  docs/phase-notes/ `
  start-versuslab.bat `
  start-versuslab.sh `
  stop-versuslab.bat `
  stop-versuslab.sh `
  guide.md `
  SETUP_COMPLETE.md `
  FINAL_STATUS_REPORT.md `
  IMPLEMENTATION_COMPLETE.md `
  VERSUSLAB_ANALYSIS_AND_FIXES.md `
  .vscode/settings.json `
  scripts/commit_history.ps1

git commit -m "docs: add comprehensive phase documentation, architecture guides and launch automation" -m "- Add detailed Phase 1-12 learning notes covering core engineering principles
- Add root README with quickstart instructions, architecture diagram, and feature matrix
- Add Windows PowerShell/batch and Linux shell scripts for zero-friction local launch
- Add AGENTS.md with project boundaries, architecture rules, and testing standards"

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "✅ All 13 commits created successfully!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
