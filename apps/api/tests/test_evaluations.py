import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import DocumentChunk, ModelRun, Race
from app.evaluation.citation_faithfulness import evaluate_citation_faithfulness
from app.evaluation.cost import calculate_costs
from app.evaluation.deterministic import exact_match, json_schema_validity, regex_match
from app.evaluation.judge import run_blind_judge
from app.evaluation.retrieval_metrics import (
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.main import app


# ---------------------------------------------------------------------------
# 1. Cost Calculator Tests
# ---------------------------------------------------------------------------
def test_cost_calculation_real_providers():
    """Verify costs calculate accurately using Decimal precision for confirmed provider rates."""
    # OpenAI gpt-4o-mini: $0.15/1M in, $0.60/1M out
    # 10,000 in -> $0.0015, 5,000 out -> $0.003
    in_cost, out_cost, total_cost = calculate_costs("openai:gpt-4o-mini", 10_000, 5_000)
    assert in_cost == Decimal("0.001500")
    assert out_cost == Decimal("0.003000")
    assert total_cost == Decimal("0.004500")

    # Anthropic claude-3-5-haiku-20241022: $0.80/1M in, $4.00/1M out
    in_cost, out_cost, total_cost = calculate_costs("anthropic:claude-3-5-haiku-20241022", 1_000, 1_000)
    assert in_cost == Decimal("0.000800")
    assert out_cost == Decimal("0.004000")
    assert total_cost == Decimal("0.004800")

    # Gemini 2.5 Flash: $0.30/1M in, $2.50/1M out
    in_cost, out_cost, total_cost = calculate_costs("gemini:gemini-2.5-flash", 1_000, 1_000)
    assert in_cost == Decimal("0.000300")
    assert out_cost == Decimal("0.002500")
    assert total_cost == Decimal("0.002800")

    # xAI grok-2-1212: $2.00/1M in, $10.00/1M out
    in_cost, out_cost, total_cost = calculate_costs("xai:grok-2-1212", 1_000, 1_000)
    assert in_cost == Decimal("0.002000")
    assert out_cost == Decimal("0.010000")
    assert total_cost == Decimal("0.012000")


def test_cost_calculation_free_and_unknown_models():
    """Verify Ollama and mock models are explicitly $0, and unknown models return None."""
    # Ollama
    in_cost, out_cost, total_cost = calculate_costs("ollama:llama3.2", 10_000, 10_000)
    assert in_cost == Decimal("0.000000")
    assert out_cost == Decimal("0.000000")
    assert total_cost == Decimal("0.000000")

    # Mock
    in_cost, out_cost, total_cost = calculate_costs("mock:mock-gpt", 500, 500)
    assert in_cost == Decimal("0.000000")
    assert out_cost == Decimal("0.000000")
    assert total_cost == Decimal("0.000000")

    # Unknown model: cannot confirm rates -> returns None
    in_cost, out_cost, total_cost = calculate_costs("unknown:super-llm", 1_000, 1_000)
    assert in_cost is None
    assert out_cost is None
    assert total_cost is None

    # Missing token counts -> returns None
    in_cost, out_cost, total_cost = calculate_costs("openai:gpt-4o-mini", None, 100)
    assert in_cost is None


def test_cost_calculation_edge_cases_and_matrix():
    """Verify edge cases: 0 tokens, large token counts, and prefix fallbacks."""
    # 0 tokens = $0.000000
    in_cost, out_cost, total_cost = calculate_costs("openai:gpt-4o-mini", 0, 0)
    assert in_cost == Decimal("0.000000")
    assert out_cost == Decimal("0.000000")
    assert total_cost == Decimal("0.000000")

    # High token volume (10 Million input, 2 Million output on Anthropic Haiku)
    # Haiku: $0.80 / 1M in -> $8.00; $4.00 / 1M out -> $8.00; total = $16.00
    in_c, out_c, tot_c = calculate_costs("anthropic:claude-3-5-haiku-20241022", 10_000_000, 2_000_000)
    assert in_c == Decimal("8.000000")
    assert out_c == Decimal("8.000000")
    assert tot_c == Decimal("16.000000")

    # None output tokens: in_cost calculated, out_cost None, total_cost matches in_cost
    in_c, out_c, tot_c = calculate_costs("gemini:gemini-2.5-flash", 1000, None)
    assert in_c == Decimal("0.000300")
    assert out_c is None
    assert tot_c == Decimal("0.000300")


# ---------------------------------------------------------------------------
# 2. Deterministic Evaluators Tests
# ---------------------------------------------------------------------------
def test_exact_match():
    assert exact_match("VersusLab", "VersusLab") == 1.0
    assert exact_match("VersusLab", "versuslab", ignore_case=False) == 0.0
    assert exact_match("VersusLab", "versuslab", ignore_case=True) == 1.0
    assert exact_match("  VersusLab \n", "VersusLab", strip_whitespace=True) == 1.0
    assert exact_match("Different", "VersusLab") == 0.0


def test_regex_match():
    assert regex_match("Confidence: 98%", r"Confidence:\s*\d+%") == 1.0
    assert regex_match("Confidence: High", r"Confidence:\s*\d+%") == 0.0
    assert regex_match("Answer", r"[invalid(regex") == 0.0


def test_json_schema_validity():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "score": {"type": "number"},
        },
        "required": ["name", "score"],
    }

    # Valid raw JSON
    valid_json = '{"name": "gpt-4", "score": 9.5}'
    assert json_schema_validity(valid_json, schema) == 1.0

    # Valid JSON inside Markdown markdown code fences
    fenced_json = '```json\n{"name": "claude", "score": 9.8}\n```'
    assert json_schema_validity(fenced_json, schema) == 1.0

    # Invalid JSON structure
    assert json_schema_validity('{"name": "gpt-4", score: 9}', schema) == 0.0

    # Missing required field
    assert json_schema_validity('{"name": "gpt-4"}', schema) == 0.0

    # Wrong data type
    assert json_schema_validity('{"name": "gpt-4", "score": "not_a_number"}', schema) == 0.0


# ---------------------------------------------------------------------------
# 3. Blind LLM-as-Judge Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_blind_judge():
    """Verify judge prompt contains blind labels only and unblinds results to correct model IDs."""
    contenders = [
        {"model_id": "openai:gpt-4o-mini", "response_text": "Answer from GPT"},
        {"model_id": "anthropic:claude-3-5-haiku-latest", "response_text": "Answer from Claude"},
    ]

    mock_judge_response = json.dumps({
        "answers": [
            {
                "label": "Answer A",
                "correctness": 0.9,
                "relevance": 0.85,
                "completeness": 0.95,
                "instruction_following": 1.0,
                "reason": "Strong answer",
            },
            {
                "label": "Answer B",
                "correctness": 0.8,
                "relevance": 0.8,
                "completeness": 0.7,
                "instruction_following": 0.9,
                "reason": "Decent answer",
            },
        ]
    })

    async def fake_call_llm(provider_spec: str, prompt: str):
        # Verify blindness: provider names and model IDs must NOT appear in prompt
        assert "openai" not in prompt
        assert "gpt-4o-mini" not in prompt
        assert "anthropic" not in prompt
        assert "claude-3-5-haiku-latest" not in prompt
        assert "[Answer A]" in prompt
        assert "[Answer B]" in prompt
        return mock_judge_response, "openai:gpt-4o-mini"

    with patch("app.evaluation.judge.call_llm", side_effect=fake_call_llm):
        results = await run_blind_judge(
            prompt="Explain quantum entanglement",
            contenders=contenders,
            judge_model="openai:gpt-4o-mini",
        )

        assert len(results) == 8  # 4 metrics * 2 contenders
        model_ids = {r["model_id"] for r in results}
        assert model_ids == {"openai:gpt-4o-mini", "anthropic:claude-3-5-haiku-latest"}

        # Find correctness for first model
        gpt_correctness = next(
            r for r in results if r["model_id"] == "openai:gpt-4o-mini" and r["metric"] == "correctness"
        )
        assert gpt_correctness["score"] == 0.9
        assert gpt_correctness["judge_model"] == "openai:gpt-4o-mini"


# ---------------------------------------------------------------------------
# 4. Citation Faithfulness Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_evaluate_citation_faithfulness_no_citations():
    """Returns empty list when response contains no citations."""
    chunk = DocumentChunk(
        id="c1",
        document_id="d1",
        chunk_index=0,
        text="VersusLab is fast.",
        embedding=[0.1] * 768,
    )
    results = await evaluate_citation_faithfulness(
        prompt="What is VersusLab?",
        answer="VersusLab is fast without citations.",
        retrieved_chunks=[chunk],
    )
    assert results == []


@pytest.mark.asyncio
async def test_evaluate_citation_faithfulness_with_citations():
    """Evaluates citations against retrieved chunks and computes aggregate faithfulness."""
    answer = "VersusLab supports multiplexed SSE streaming [S1]."
    chunk = DocumentChunk(
        id="chunk-1",
        document_id="doc-1",
        chunk_index=0,
        text="VersusLab multiplexes all model streams over a single SSE connection.",
        embedding=[0.1] * 768,
    )

    mock_llm_json = json.dumps({"faithfulness_score": 1.0, "reason": "Directly supported by chunk-1."})

    with patch("app.evaluation.citation_faithfulness.call_llm", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = (mock_llm_json, "openai:gpt-4o-mini")

        evals = await evaluate_citation_faithfulness(
            prompt="How does streaming work?",
            answer=answer,
            retrieved_chunks=[chunk],
            judge_model="openai:gpt-4o-mini",
        )

        # 1 citation eval + 1 aggregate faithfulness eval
        assert len(evals) == 2
        cit_eval = next(e for e in evals if e["metric"] == "citation_faithfulness")
        assert cit_eval["score"] == 1.0
        assert "Directly supported" in cit_eval["reason"]

        agg_eval = next(e for e in evals if e["metric"] == "faithfulness")
        assert agg_eval["score"] == 1.0


# ---------------------------------------------------------------------------
# 5. Retrieval Metrics Tests
# ---------------------------------------------------------------------------
def test_retrieval_ranking_metrics():
    retrieved = ["doc1", "doc2", "doc3", "doc4"]
    gold = ["doc2", "doc4"]

    # Recall@K
    assert recall_at_k(retrieved, gold, k=1) == 0.0  # doc1 not in gold
    assert recall_at_k(retrieved, gold, k=2) == 0.5  # doc2 in gold (1/2)
    assert recall_at_k(retrieved, gold, k=4) == 1.0  # doc2 and doc4 (2/2)

    # Precision@K
    assert precision_at_k(retrieved, gold, k=2) == 0.5  # 1 hit in top 2 (1/2)
    assert precision_at_k(retrieved, gold, k=4) == 0.5  # 2 hits in 4 (2/4)

    # Reciprocal Rank (first hit is doc2 at rank 2 -> 1/2 = 0.5)
    assert reciprocal_rank(retrieved, gold) == 0.5


def test_evaluate_dataset_fixture():
    """Verify gold_retrieval_set fixture evaluates successfully with retrieval simulation."""
    from app.evaluation.retrieval_metrics import run_benchmark_simulation
    results = run_benchmark_simulation(k=3)
    assert "recall@3" in results
    assert "precision@3" in results
    assert "mrr" in results
    assert results["recall@3"] >= 0.5
    assert results["mrr"] > 0.5


# ---------------------------------------------------------------------------
# 6. API Evaluate Endpoint Test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_evaluate_race_endpoint():
    """Tests POST /api/races/{race_id}/evaluate with mocked judge."""
    fake_race = Race(
        id="race-eval-test",
        prompt="Explain neural networks",
        temperature=0.7,
        max_tokens=256,
        status="completed",
    )
    fake_run = ModelRun(
        id="run-eval-1",
        race_id="race-eval-test",
        model_id="mock:mock-model",
        response_text="Neural networks are inspired by biological neurons.",
        status="completed",
    )
    fake_race.model_runs = [fake_run]

    mock_judge_output = json.dumps({
        "answers": [
            {
                "label": "Answer A",
                "correctness": 0.95,
                "relevance": 0.90,
                "completeness": 0.85,
                "instruction_following": 1.0,
                "reason": "Clear and accurate.",
            }
        ]
    })

    with patch("app.api.race.get_race_detail", new_callable=AsyncMock) as mock_get_race, \
         patch("app.evaluation.judge.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("app.api.race.save_evaluations", new_callable=AsyncMock) as mock_save_evals:

        mock_get_race.return_value = fake_race
        mock_llm.return_value = (mock_judge_output, "openai:gpt-4o-mini")
        mock_save_evals.return_value = None

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/races/race-eval-test/evaluate")
            assert resp.status_code == 200
            data = resp.json()
            assert data["evaluated"] is True
            assert data["evaluations_count"] == 4
            assert mock_save_evals.called
