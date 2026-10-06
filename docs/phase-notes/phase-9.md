# Phase 9: Experiment Engine, Benchmark Runner, Comparison Dashboard & CI Regression Gating

Welcome to the Phase 9 notes for **VersusLab**! This document explains how we transformed VersusLab from a system that runs one-off multi-model races into an **experiment engine** capable of executing versioned benchmark datasets, computing multi-dimensional tradeoff metrics, rendering Pareto scatter plots, and enforcing automated CI quality regression gates on pull requests.

---

## 1. What We Built

In Phase 9, we built the following capabilities on top of Phases 1–8:

1. **Database Schema Additions & Migration (`005_add_experiments_and_benchmarks.py`)**:
   - **`benchmark_datasets`**: Immutable, versioned collections of evaluation test cases (`id`, `name`, `version`, `description`, `created_at`).
   - **`benchmark_cases`**: Individual questions or prompts within a dataset (`id`, `dataset_id` FK, `question`, `expected_answer`, `gold_chunk_ids` JSON, `category`).
   - **`experiments`**: Configured multi-model evaluation runs across a dataset (`id`, `name`, `dataset_id` FK, `models` JSON, `git_commit`, `status`, `include_llm_judge`, `created_at`, `finished_at`).
   - **`experiment_runs`**: Traceable join table linking an experiment's case execution back to a real `race_id` in the `races` table (`id`, `experiment_id` FK, `benchmark_case_id` FK, `race_id` FK, `created_at`).

2. **Hand-Authored Seed Benchmark Dataset (`evals/datasets/seed_benchmark.json`)**:
   - Sourced **24 hand-authored cases** across 4 distinct categories (6 cases each):
     - **`factual`**: Objective questions with exact deterministic answers (e.g. *Capital of France*, *Chemical symbol for Gold*, *Speed of light in km/s*).
     - **`reasoning`**: Deductive logic and word math problems (e.g. *Syllogisms*, *Relative ages*, *Handshake combinatorics*).
     - **`coding`**: Structured outputs and programming challenges (e.g. *JSON extraction schema*, *Prime numbers list*, *Regex pattern*).
     - **`rag`**: Domain questions mapped to VersusLab lore with `gold_chunk_ids` for IR metric evaluation (`Recall@K`, `MRR`).

3. **Dataset Loader Script (`scripts/load_benchmark_dataset.py`)**:
   - Reads JSON benchmark files and inserts them into PostgreSQL.
   - **Enforces Immutability**: If a dataset name already exists, the loader queries the highest existing version and inserts the new cases under `version = latest_version + 1` with a new UUID. Datasets are never modified in place.

4. **Experiment Runner (`app/experiments/runner.py`)**:
   - `run_experiment(experiment_id)`: Orchestrates the execution of all cases in an experiment's dataset.
   - **Reuses the Race Engine**: Executes each case as a real race using `run_race` and `RacePersistenceTracker` from Phase 2/5. No duplicate execution path was created.
   - **Concurrency Enforcement**: Respects the global `MAX_CONCURRENT_MODEL_CALLS` semaphore from Phase 3. Cases run sequentially, while each case's configured models run concurrently within the semaphore.
   - **Automatic Evaluators**: Runs Phase 8's deterministic evaluators (`exact_match`, `json_schema_validity`, retrieval metrics) on every case with an expected answer.
   - **Cost Guardrail**: Paid blind LLM judging and citation faithfulness only execute if `include_llm_judge=True` was explicitly opted into by the user.

5. **Tradeoff Comparison Aggregator (`app/experiments/comparison.py`)**:
   - Computes per-model aggregates directly from the stored `model_runs` and `evaluations` rows via the `experiment_runs` join:
     - Mean TTFT (ms)
     - Mean Latency (s)
     - Mean Throughput (tokens/sec)
     - Total Cost (USD)
     - Error & Timeout Rates
     - Mean Scores per Metric (`exact_match`, `json_schema_validity`, `correctness`, `faithfulness`)
     - Pareto Points (`{ quality_score, total_cost, latency_ms }`)
   - Does **not** collapse metrics into a single artificial ranking score, preserving transparent tradeoffs.

6. **REST API Endpoints (`app/api/experiments.py`)**:
   - `GET /api/datasets`: List available benchmark datasets and version metadata.
   - `GET /api/datasets/{id}`: View dataset details and all cases.
   - `POST /api/experiments`: Create an experiment; automatically captures git commit SHA.
   - `GET /api/experiments`: List past experiments with status and model counts.
   - `POST /api/experiments/{id}/run`: Spawns runner as a background asyncio task.
   - `GET /api/experiments/{id}/status`: Live polling endpoint returning case progress.
   - `GET /api/experiments/{id}/results`: Returns aggregated comparison JSON.

7. **Next.js Frontend Integration (`apps/web`)**:
   - **/experiments**: Lists past experiments with status badges (`Completed`, `Running`, `Failed`) and provides a modal form to configure and launch new experiments.
   - **/experiments/[id]**:
     - Live progress bar polling status while the experiment runs.
     - Multi-model tradeoff comparison table.
     - **Pareto-Style Scatter Plot**: Zero-dependency, responsive, dark-mode SVG chart plotting Quality Score ($y$-axis) vs Total Cost ($x$-axis) with interactive tooltips.
     - Per-case breakdown table linking each question and answer to its individual race detail page (`/history/[race_id]`).
   - Added `/experiments` navigation links in the header across all pages.

8. **Automated CI Quality Regression Gate**:
   - **Baseline Configuration (`evals/baselines/ci_baseline.json`)**: Versioned baseline committed to git.
   - **Regression Script (`scripts/run_ci_regression.py`)**: Runs a test subset against `MockProvider`, measures deterministic scores, compares against baseline, and exits with 0 (pass) or 1 (regression failure). Supports `--update-baseline`.
   - **GitHub Actions Workflow (`.github/workflows/regression.yml`)**: Automatically triggers on pull requests touching `apps/api` or `evals`, boots PostgreSQL with pgvector, runs migrations, executes unit tests, and validates the regression gate.

---

## 2. Why We Built It This Way

### Why Are Benchmark Datasets Immutable?
In machine learning and LLM evaluation, **dataset drift** is a silent killer of scientific reproducibility. If a developer edits a benchmark question in place, all historical experiment scores associated with that dataset instantly lose their meaning—you can no longer tell whether a model improved or if the question merely became easier.
By enforcing that datasets are strictly immutable and assigning every edit a new `version` number (`v1`, `v2`, ...), VersusLab guarantees that an experiment referencing dataset `(id, version)` is 100% reproducible forever.

### Why Is LLM Judging Opt-In for Experiments?
Running a 24-case benchmark across 5 models requires:
- **Blind Judge**: 24 judge calls (one call per case, comparing all 5 contenders).
- **Citation Faithfulness**: 6 RAG cases $\times$ 5 models $\times$ 2 citations = 60 calls.
- **Total**: ~84 paid LLM calls per experiment run.
Auto-triggering paid judging on every run would cause surprise cloud bills. Making `include_llm_judge` an explicit opt-in ensures deterministic evaluators (`$0.00` cost) handle routine benchmark runs, while paid judging is reserved for major milestone evaluations.

### Why No Single "Winner" Score?
In enterprise applications, there is rarely a single "best" model. A model that achieves 98% accuracy but costs $0.03 per query and takes 4.5 seconds to stream is useless for a real-time autocomplete feature. Conversely, a local 4B model running at $0.00 cost with 80ms TTFT might achieve 82% accuracy, making it the superior choice for high-volume latency-critical workloads.
Our Pareto-style comparison dashboard lets users inspect the **tradeoff frontier** (Quality vs Cost vs Latency) rather than forcing an arbitrary weighted score.

### Why Hermetic CI Testing Against MockProvider?
CI pipelines must be:
1. **Deterministic**: No flaky failures caused by external network jitter or rate limits.
2. **Free**: Pull requests must not consume paid API credits.
3. **Secret-Free**: Forked PRs cannot access organization secrets.
By running CI regression against `MockProvider` with canned responses, the mock baseline has zero natural variance ($\sigma = 0$). Any drop below the baseline indicates a real software regression (e.g. broken event loop task cancellation, prompt parsing bugs, or corrupted evaluator logic).

### Why Native SVG for the Pareto Chart?
Introducing heavy charting libraries (e.g. `recharts` or `chart.js`) often creates dependency bloat, SSR hydration mismatches, and peer dependency conflicts with Next.js 16 and React 19. A pure SVG chart requires 0 external dependencies, renders instantly, supports custom dark-mode styling, and scales cleanly on any screen resolution.

---

## 3. Files Touched

### Backend (`apps/api`):
- `app/db/models.py`: Added `BenchmarkDataset`, `BenchmarkCase`, `Experiment`, `ExperimentRun`.
- `migrations/versions/005_add_experiments_and_benchmarks.py`: Alembic migration for all 4 tables.
- `app/providers/mock.py`: Added support for optional `canned_responses` in `MockProvider`.
- `app/experiments/comparison.py`: Multi-model tradeoff aggregator and Pareto point generator.
- `app/experiments/runner.py`: Benchmark runner coordinating races and automated evaluators.
- `app/api/experiments.py`: Endpoints for datasets, experiments, status polling, and results.
- `app/main.py`: Mounted `experiments_router`.
- `tests/test_experiments.py`: 5 hermetic unit tests covering aggregation, endpoints, and error handling.

### Frontend (`apps/web`):
- `lib/types.ts`: Added TypeScript interfaces for datasets, cases, experiments, and Pareto points.
- `lib/race-client.ts`: Added client fetch helpers for datasets, experiments, runner, and results.
- `app/experiments/page.tsx`: Experiment list view and "+ New Experiment" modal form.
- `app/experiments/[id]/page.tsx`: Live progress bar, comparison table, Pareto SVG scatter plot, and case breakdowns.
- `app/page.tsx` & `app/history/page.tsx`: Added navigation links to `/experiments`.

### Evals, Scripts & CI:
- `evals/datasets/seed_benchmark.json`: Hand-authored 24-case benchmark dataset across 4 categories.
- `evals/baselines/ci_baseline.json`: Versioned baseline metrics for CI quality gating.
- `scripts/load_benchmark_dataset.py`: Immutability-enforcing dataset loader script.
- `scripts/run_ci_regression.py`: CI regression check script with `--update-baseline` support.
- `.github/workflows/regression.yml`: GitHub Actions workflow validating tests and regression gate on PRs.

---

## 4. How to Run and Verify

### Step 1: Run All Hermetic Unit Tests (53 passed)
```powershell
cd apps/api
.\.venv\Scripts\pytest -v
```
*Expected: `53 passed in ~10s`.*

### Step 2: Run the CI Quality Regression Gate Locally
```powershell
python scripts/run_ci_regression.py
```
*Expected Output:*
```text
==================================================
 Running VersusLab CI Regression Suite
==================================================
Metric           | Measured   | Baseline   | Status
----------------------------------------------------
exact_match      | 1.0000     | 1.0000     | PASS
error_rate       | 0.0000     | 0.0000     | PASS
timeout_rate     | 0.0000     | 0.0000     | PASS
==================================================
 CI Regression Gate: PASSED (Quality sustained)
==================================================
```

### Step 3: Apply the Migration & Load the Seed Dataset
With your Postgres container running:
```powershell
cd apps/api
.\.venv\Scripts\alembic upgrade head
python ..\..\scripts\load_benchmark_dataset.py
```
*Expected Output:*
```text
==================================================
 VersusLab Benchmark Dataset Loaded Successfully
==================================================
 Name        : VersusLab Core Seed Benchmark
 Version     : 1
 Dataset ID  : <uuid>
 Total Cases : 24
==================================================
```

### Step 4: Create and Run an Experiment via the API
1. Start the API server:
   ```powershell
   cd apps/api
   .\.venv\Scripts\uvicorn app.main:app --reload --port 8000
   ```
2. Get the loaded `dataset_id`:
   ```powershell
   $datasets = Invoke-RestMethod -Uri "http://localhost:8000/api/datasets"
   $datasetId = $datasets[0].id
   Write-Host "Dataset ID: $datasetId"
   ```
3. Create an experiment with mock models:
   ```powershell
   $body = @{
       name = "Sprint 9 Mock Evaluation"
       dataset_id = $datasetId
       models = @("mock:mock-1", "mock:mock-slow-1")
       include_llm_judge = $false
   } | ConvertTo-Json

   $exp = Invoke-RestMethod -Uri "http://localhost:8000/api/experiments" -Method Post -ContentType "application/json" -Body $body
   $expId = $exp.id
   Write-Host "Experiment ID: $expId"
   ```
4. Trigger the background run:
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/api/experiments/$expId/run" -Method Post
   ```
5. Poll the status until completed:
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/api/experiments/$expId/status"
   ```
6. View the aggregated comparison results:
   ```powershell
   $results = Invoke-RestMethod -Uri "http://localhost:8000/api/experiments/$expId/results"
   $results.models_stats | Format-Table model_id, runs_count, error_rate, mean_ttft_ms, total_cost
   ```

### Step 5: Verify in the Web UI
1. Run the frontend:
   ```powershell
   cd apps/web
   npm run dev
   ```
2. Open `http://localhost:3000/experiments` in your browser.
3. Click **"+ New Experiment"**, select the dataset and models, and launch.
4. Watch the progress bar advance, then inspect the **Performance & Quality Summary Table** and the **Pareto Tradeoff Frontier Chart**.

---

## 5. 5 Concepts to Understand

### 1. Benchmark Datasets & Dataset Drift
A benchmark dataset is a standardized set of test inputs paired with expected outputs used to evaluate models under identical conditions. **Dataset drift** occurs when the evaluation questions or formatting change over time without versioning. If questions change silently, historical model comparison is invalid. Enforcing dataset immutability ensures all comparisons are scientifically valid.

### 2. Pareto Frontier & Multi-Objective Tradeoffs
In multi-objective optimization, a solution is on the **Pareto frontier** if no other solution is strictly better across all criteria. For LLMs, the criteria are typically quality, financial cost, and latency. A fast, cheap model with good accuracy and a slow, expensive model with perfect accuracy can both sit on the Pareto frontier. Evaluating models across this frontier helps engineers choose the right model for their specific latency and budget constraints.

### 3. Background Task Orchestration & Concurrency Semaphores
Running an experiment across 30 cases and 5 models triggers 150 individual model stream requests. If spawned all at once, they would exhaust operating system sockets and trigger rate limits. By combining sequential case execution with an `asyncio.Semaphore` (`MAX_CONCURRENT_MODEL_CALLS`), VersusLab executes large benchmark suites stably in the background while allowing users to poll progress.

### 4. CI Quality Regression Gating
A quality regression gate is an automated test in continuous integration that fails a pull request if a performance or accuracy metric drops below an agreed baseline. This prevents code changes (such as prompt refactoring or tokenization changes) from silently degrading model output quality before merging into production.

### 5. Relational Tracing via Join Tables
Rather than building an isolated evaluation runner that bypasses the core application, the `experiment_runs` join table links high-level benchmark cases directly to low-level `races`. This means every single benchmark evaluation can be traced back to its raw SSE token events, exact timing logs, and HTTP request deltas, making results fully auditable.
