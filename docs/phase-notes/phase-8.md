# Phase 8: LLM Evaluation Framework & Cost Calculator

Welcome to the Phase 8 notes for **VersusLab**! This document explains how we transformed VersusLab from a multi-model streaming chatbot into a full-fledged **LLM evaluation platform**. 

In this phase, we implemented:
1. Confirmed multi-provider token cost calculation with exact Decimal precision.
2. Fast deterministic evaluators (exact match, regex, JSON schema validity).
3. A narrow citation faithfulness evaluator verifying model claims against retrieved RAG chunks.
4. A blind LLM-as-a-judge scoring anonymous answers on correctness, relevance, completeness, and instruction-following.
5. Standard Information Retrieval (IR) metrics (Recall@K, Precision@K, MRR) benchmarked against a hand-authored gold dataset fixture.
6. Database persistence for evaluations and token costs per model run.
7. An evaluation trigger button and results display in the frontend history UI.

---

## 1. Confirmed Provider Pricing Table

Before writing any cost logic, we consulted official documentation for each provider (September 2026 / current rates). Ollama models running on local hardware have no API per-token fees and are explicitly priced at **$0.00**.

| Provider | Model Spec | Input Cost (per 1M tokens) | Output Cost (per 1M tokens) | Input Rate / 1k | Output Rate / 1k | Source |
|---|---|---|---|---|---|---|
| **OpenAI** | `gpt-4o-mini` | $0.15 | $0.60 | $0.000150 | $0.000600 | [OpenAI Pricing](https://openai.com/api/pricing) |
| **Anthropic** | `claude-3-5-haiku-20241022` | $0.80 | $4.00 | $0.000800 | $0.004000 | [Anthropic Pricing](https://docs.anthropic.com) |
| **Google Gemini** | `gemini-2.5-flash` | $0.30 | $2.50 | $0.000300 | $0.002500 | [Google AI Studio Pricing](https://ai.google.dev/pricing) |
| **xAI Grok** | `grok-2-1212` | $2.00 | $10.00 | $0.002000 | $0.010000 | [xAI Documentation](https://docs.x.ai) |
| **Ollama** | Local models (e.g. `qwen3:4b`) | $0.00 | $0.00 | $0.000000 | $0.000000 | Local hardware / open-weights |
| **Mock** | `mock-1`, `mock-slow-1`, etc. | $0.00 | $0.00 | $0.000000 | $0.000000 | Hermetic test stubs |

*Note: For unconfirmed models or missing token counts, VersusLab returns `None` with a `TODO(owner)` fallback, strictly adhering to Rule 9 (never invent numbers).*

---

## 2. What We Built

### 1. Database Schema & Alembic Migration (`004_add_evaluations_and_costs.py`)
- **`evaluations` Table**:
  - `id`: UUID primary key.
  - `model_run_id`: Foreign key referencing `model_runs.id` (with `CASCADE` delete).
  - `metric`: String identifying the evaluation metric (`"correctness"`, `"relevance"`, `"completeness"`, `"instruction_following"`, `"citation_faithfulness"`, `"faithfulness"`).
  - `score`: Float score normalized to `[0.0, 1.0]`.
  - `judge_model`: Nullable string recording the model used for judging (e.g., `"openai:gpt-4o-mini"`).
  - `reason`: Nullable text providing judge justification.
  - `created_at`: UTC timestamp.
- **`model_runs` Additions**:
  - `input_cost`, `output_cost`, `total_cost`: Stored as exact `Numeric(10, 6)` in PostgreSQL to prevent binary floating-point rounding errors.
- **`races` Additions**:
  - `document_id`: Foreign key referencing `documents.id` for linking races to the knowledge base document used during RAG.

### 2. Provider-Independent Cost Calculator (`app/evaluation/cost.py`)
- Mapped provider pricing to `(input_price_per_1k, output_price_per_1k)` using Python's `Decimal`.
- Built pure function `calculate_costs(model_id, input_tokens, output_tokens)`.
- Wired cost calculation into the existing model run finalization point in `RacePersistenceTracker.record_event` (Phase 5). No second write path was created.

### 3. Fast Deterministic Evaluators (`app/evaluation/deterministic.py`)
- **`exact_match(answer, expected, strip_whitespace=True, ignore_case=False)`**: Tests whether generated text exactly equals the gold standard answer.
- **`regex_match(answer, pattern)`**: Tests whether generated text matches an expected regular expression format.
- **`json_schema_validity(answer, schema=None)`**: Parses JSON answers, automatically strips Markdown code fences (e.g. ````json ... ````), and validates structure and data types against a JSON Schema.

### 4. Citation Faithfulness Evaluator (`app/evaluation/citation_faithfulness.py`)
- Builds on Phase 7's heuristic existence check (`citation_check.py`).
- Inspects cited source tokens (`[S1]`, `[S2]`) and fetches the specific evidence chunk text.
- Issues an LLM call to a configurable judge (`Settings.judge_model`) with a narrow, focused prompt:
  *"Does this cited evidence directly and factually support this specific claim in the model's answer?"*
- Produces:
  - One `evaluations` record per checked citation (`metric="citation_faithfulness"`).
  - One aggregate `evaluations` record per contender (`metric="faithfulness"`, averaged across all cited claims).

### 5. Blind LLM-as-a-Judge (`app/evaluation/judge.py`)
- General-purpose blind evaluator comparing contender answers side-by-side:
  - **Blinding**: Strips all provider and model names. Labels contenders anonymously as `[Answer A]`, `[Answer B]`, etc.
  - **Single LLM Call**: Sends all candidate answers together to the judge model in one call, asking it to rate each answer on four metrics (0.0 to 1.0):
    1. `correctness`
    2. `relevance`
    3. `completeness`
    4. `instruction_following`
  - **Unblinding in Application Code**: The judge only outputs scores for `Answer A`, `Answer B`. VersusLab's Python code maps the scores back to the true `model_run_id` and persists the records.
- **Explicit Evaluation Endpoint**:
  - `POST /api/races/{race_id}/evaluate`: Runs blind judging (and citation faithfulness when RAG was used) on completed races.
  - Judging is intentionally an **explicit, user-triggered step** rather than automatic, ensuring users do not incur unexpected API costs.

### 6. Information Retrieval Metrics (`app/evaluation/retrieval_metrics.py`)
- Measures RAG retrieval quality against a hand-authored gold benchmark dataset (`evals/fixtures/gold_retrieval_set.json`):
  - **Recall@K**: Proportion of relevant chunks retrieved in top $K$.
  - **Precision@K**: Proportion of top $K$ retrieved chunks that are relevant.
  - **Mean Reciprocal Rank (MRR)**: Evaluates how high up the first relevant chunk appears ($\frac{1}{\text{rank}}$).
- Runnable standalone via `python -m app.evaluation.retrieval_metrics`.

### 7. Frontend Integration (`apps/web`)
- **Race Details View (`/history/[race_id]`)**:
  - **Cost Visibility**: Metrics bar updated to display `EST. COST` per contender and `Total Est. Cost` for the entire race.
  - **Evaluation Scores**: Color-coded badges for scores ($\ge 0.8$ green, $\ge 0.5$ yellow, $< 0.5$ red), displaying metric name, judge model, and reasoning.
  - **"Evaluate Race (LLM Judge)" Button**: Triggers `POST /api/races/{race_id}/evaluate` and refreshes the page with persisted evaluations.

---

## 3. Why We Built It This Way

### Why Decimal for Currency?
Floating-point numbers in computers use IEEE 754 binary fractions. Numbers like `0.1` cannot be represented precisely in binary (e.g. `0.1 + 0.2 == 0.30000000000000004`). When multiplying millions of tokens by tiny per-token rates, floating-point error accumulates and creates discrepancies on invoices. Python's `Decimal` and PostgreSQL's `Numeric(10, 6)` store exact base-10 decimals, eliminating rounding bugs.

### Why Blind Judging?
LLMs possess significant "brand bias" and self-preference: OpenAI models often rate other OpenAI models higher, Anthropic models often prefer Claude's tone, and open models are biased toward familiar formats. By stripping model identifiers and presenting them as `[Answer A]` and `[Answer B]`, the judge cannot favor models based on name or brand.
> **Honest Disclaimer**: While blinding eliminates brand bias, it does not eliminate *length bias* (judges often prefer verbose answers) or *style bias* (judges favoring writing quirks of their own model family).

### Why Separate Citation Faithfulness from the Blind Judge?
A general-purpose blind judge compares all answers against the user prompt. In contrast, citation faithfulness is a narrow, factual groundedness check that requires cross-referencing a specific sentence against a specific evidence chunk. Bundling retrieved evidence for multiple contenders into a single multi-turn blind prompt creates context clutter and confusion. Keeping citation faithfulness separate ensures high precision.

---

## 4. Files Touched

- `apps/api/app/core/config.py`: Added `judge_model` setting (`openai:gpt-4o-mini`).
- `apps/api/app/db/models.py`: Added `Evaluation` model, cost fields (`Numeric(10, 6)`) on `ModelRun`, and `document_id` on `Race`.
- `apps/api/migrations/versions/004_add_evaluations_and_costs.py`: Alembic migration for evaluations, costs, and foreign keys.
- `apps/api/app/evaluation/cost.py`: Confirmed pricing dictionary and `calculate_costs` function.
- `apps/api/app/evaluation/deterministic.py`: `exact_match`, `regex_match`, `json_schema_validity`.
- `apps/api/app/evaluation/citation_faithfulness.py`: NLI-style claim vs evidence faithfulness evaluator.
- `apps/api/app/evaluation/judge.py`: Blind LLM-as-a-judge and response parser.
- `apps/api/app/evaluation/retrieval_metrics.py`: Recall@K, Precision@K, and MRR calculators.
- `apps/api/app/evaluation/__init__.py`: Exported evaluation utilities.
- `evals/fixtures/gold_retrieval_set.json`: Hand-authored benchmark test fixture.
- `apps/api/app/db/service.py`: Added `save_evaluations`, updated `mark_model_finished` with cost persistence.
- `apps/api/app/db/tracker.py`: Wired cost calculations into finalization event.
- `apps/api/app/api/race.py`: Added `POST /api/races/{race_id}/evaluate` and cost/evaluations to `GET /api/races/{race_id}`.
- `apps/api/tests/test_evaluations.py`: 11 hermetic unit tests covering all evaluation components.
- `apps/web/lib/types.ts`: Added `EvaluationDetail` and cost fields.
- `apps/web/lib/race-client.ts`: Added `evaluateRace(raceId)`.
- `apps/web/app/history/[race_id]/page.tsx`: Added cost metrics, evaluations display, and evaluation trigger button.

---

## 5. How to Run and Verify

### Step 1: Apply the New Alembic Migration
Make sure your PostgreSQL container is running:
```powershell
docker compose -f infra/docker-compose.yml up -d
```
Then run the migration in `apps/api`:
```powershell
.\.venv\Scripts\alembic upgrade head
```
*Expected output: Upgrades through `004_add_evaluations_and_costs` successfully.*

### Step 2: Run All Tests (48 passing hermetic tests)
```powershell
.\.venv\Scripts\pytest -v
```
*Expected output: `48 passed`.*

### Step 3: Run the Retrieval Metrics Benchmark Simulation
```powershell
.\.venv\Scripts\python -m app.evaluation.retrieval_metrics
```
*Expected output:*
```text
==================================================
 VersusLab Phase 8 Retrieval Benchmark Metrics
==================================================
 RECALL@3        : 1.0000
 PRECISION@3     : 0.3333
 MRR             : 1.0000
==================================================
```

### Step 4: Run a Normal Race and Evaluate It
1. Start the API server:
```powershell
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```
2. Start a race with mock contenders:
```powershell
$body = @{
    prompt = "Explain quantum superposition in simple terms."
    models = @("mock:model-a", "mock:model-b")
    temperature = 0.7
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/races" -Method Post -ContentType "application/json" -Body $body
```
3. Get the `race_id` from history:
```powershell
$history = Invoke-RestMethod -Uri "http://localhost:8000/api/races?limit=1"
$raceId = $history.items[0].id
Write-Host "Race ID: $raceId"
```
4. Trigger the blind judge evaluation:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/races/$raceId/evaluate" -Method Post
```
5. Inspect the stored evaluations and costs:
```powershell
$detail = Invoke-RestMethod -Uri "http://localhost:8000/api/races/$raceId"
$detail.model_runs | ForEach-Object {
    Write-Host "Model:" $_.model_id "Total Cost:" $_.total_cost
    $_.evaluations | ForEach-Object {
        Write-Host "  - Metric:" $_.metric "Score:" $_.score "Reason:" $_.reason
    }
}
```

### Step 5: Test via the Web UI
1. Run Next.js in `apps/web`:
```powershell
npm run dev
```
2. Visit `http://localhost:3000/history/[race_id]`.
3. Observe the `EST. COST` column in the contender cards and the `Total Est. Cost` in the race summary.
4. Click **"⚡ Evaluate Race (LLM Judge)"** to trigger evaluation and view the color-coded score cards.

---

## 6. 5 Concepts to Understand

### 1. LLM-as-a-Judge & Evaluator Bias
Using a high-capacity model (like GPT-4o or Claude 3.5 Sonnet) to evaluate other models is fast and scalable compared to human evaluation. However, judges suffer from three known biases:
- **Position Bias**: Preferring the first answer (`Answer A`) regardless of quality.
- **Verbosity / Length Bias**: Rating longer, detailed answers higher even when they contain hallucinations or fluff.
- **Self-Enhancement Bias**: A model rating its own family's generation higher due to stylistic similarities.

### 2. Blind Evaluation (Anonymization & Unblinding)
Blinding is the experimental practice of removing identifying labels before scoring. In VersusLab, model answers are stripped of names like `"gpt-4o-mini"` or `"claude"` and labeled `Answer A`, `Answer B`. The judge returns evaluations for those labels, and VersusLab maps them back to the real model IDs in memory. This eliminates brand bias.

### 3. Faithfulness vs. Answer Relevance in RAG
In RAG evaluation (often called the RAG Triad):
- **Relevance**: Does the answer address what the user asked?
- **Groundedness / Faithfulness**: Is every factual claim in the answer backed by the retrieved reference text?
A model can produce an answer that is 100% relevant to the user prompt, yet 0% faithful because it fabricated all the facts. Measuring faithfulness specifically checks for hallucinations.

### 4. Information Retrieval Metrics (Recall@K, Precision@K, MRR)
When retrieving documents:
- **Recall@K**: Did the top $K$ results contain the documents needed to answer the question?
- **Precision@K**: How much noise or irrelevant context was included in the top $K$?
- **MRR (Mean Reciprocal Rank)**: Where was the *first* correct document located? If it was rank 1, score is $1.0$; rank 2 is $0.5$; rank 3 is $0.33$. Higher MRR means the user or LLM sees the best answer immediately.

### 5. Fixed-Point Decimal Arithmetic vs. Floating-Point
Computers store floating-point numbers in base-2, which cannot represent numbers like `0.1` or `0.000150` exactly. For scientific computing, tiny rounding variations are acceptable, but for billing and financial metrics, they cause accounting discrepancies. Fixed-point `Decimal` arithmetic enforces base-10 precision and controlled rounding modes (e.g. `ROUND_HALF_UP`).
