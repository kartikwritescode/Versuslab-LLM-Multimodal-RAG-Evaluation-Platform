"""Unit tests for Phase 9: Benchmark Datasets, Experiment Runner, and Comparison Aggregation."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import (
    BenchmarkCase,
    BenchmarkDataset,
    Evaluation,
    Experiment,
    ExperimentRun,
    ModelRun,
    Race,
)
from app.experiments.comparison import aggregate_experiment_results
from app.main import app


# ---------------------------------------------------------------------------
# 1. Comparison Aggregator Unit Tests
# ---------------------------------------------------------------------------
def test_aggregate_experiment_results():
    """Verify aggregator calculates means, costs, rates, and Pareto points without collapsing scores."""
    dataset = BenchmarkDataset(
        id="ds-test-1",
        name="Test Benchmark",
        version=1,
    )
    exp = Experiment(
        id="exp-test-1",
        name="Sprint Evaluation",
        dataset_id="ds-test-1",
        models=["mock:model-a", "mock:model-b"],
        git_commit="abc1234",
        status="completed",
        include_llm_judge=False,
        created_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    exp.dataset = dataset

    case1 = BenchmarkCase(
        id="case-1",
        dataset_id="ds-test-1",
        question="What is 2+2?",
        expected_answer="4",
        category="reasoning",
    )
    case2 = BenchmarkCase(
        id="case-2",
        dataset_id="ds-test-1",
        question="What is the capital of France?",
        expected_answer="Paris",
        category="factual",
    )

    # Race 1
    race1 = Race(id="race-1", prompt="What is 2+2?", status="completed")
    run1_a = ModelRun(
        id="r1-a",
        race_id="race-1",
        model_id="mock:model-a",
        status="completed",
        ttft_ms=100,
        latency_ms=500,
        input_tokens=10,
        output_tokens=5,
        total_cost=0.000050,
        response_text="4",
    )
    run1_a.evaluations = [
        Evaluation(id="ev-1", model_run_id="r1-a", metric="exact_match", score=1.0)
    ]
    run1_b = ModelRun(
        id="r1-b",
        race_id="race-1",
        model_id="mock:model-b",
        status="completed",
        ttft_ms=200,
        latency_ms=1000,
        input_tokens=10,
        output_tokens=5,
        total_cost=0.000100,
        response_text="5",
    )
    run1_b.evaluations = [
        Evaluation(id="ev-2", model_run_id="r1-b", metric="exact_match", score=0.0)
    ]
    race1.model_runs = [run1_a, run1_b]

    # Race 2 (with model-b having an error)
    race2 = Race(id="race-2", prompt="What is the capital of France?", status="completed")
    run2_a = ModelRun(
        id="r2-a",
        race_id="race-2",
        model_id="mock:model-a",
        status="completed",
        ttft_ms=120,
        latency_ms=600,
        input_tokens=10,
        output_tokens=10,
        total_cost=0.000060,
        response_text="Paris",
    )
    run2_a.evaluations = [
        Evaluation(id="ev-3", model_run_id="r2-a", metric="exact_match", score=1.0)
    ]
    run2_b = ModelRun(
        id="r2-b",
        race_id="race-2",
        model_id="mock:model-b",
        status="error",
        error_message="Simulated connection drop",
    )
    run2_b.evaluations = []
    race2.model_runs = [run2_a, run2_b]

    exp_runs = [
        ExperimentRun(
            id="er-1",
            experiment_id="exp-test-1",
            benchmark_case_id="case-1",
            race_id="race-1",
        ),
        ExperimentRun(
            id="er-2",
            experiment_id="exp-test-1",
            benchmark_case_id="case-2",
            race_id="race-2",
        ),
    ]
    exp_runs[0].benchmark_case = case1
    exp_runs[0].race = race1
    exp_runs[1].benchmark_case = case2
    exp_runs[1].race = race2

    agg = aggregate_experiment_results(exp, exp_runs)

    assert agg["experiment_id"] == "exp-test-1"
    assert agg["total_cases"] == 2
    assert len(agg["models_stats"]) == 2

    # Model A: 2 runs, 0 errors, mean TTFT = (100+120)/2 = 110.0, Exact Match = 1.0
    stats_a = next(m for m in agg["models_stats"] if m["model_id"] == "mock:model-a")
    assert stats_a["runs_count"] == 2
    assert stats_a["successful_runs"] == 2
    assert stats_a["error_rate"] == 0.0
    assert stats_a["mean_ttft_ms"] == 110.0
    assert stats_a["mean_metrics"]["exact_match"] == 1.0
    assert stats_a["total_cost"] == 0.000110

    # Model B: 2 runs, 1 error (error_rate = 0.5), 1 exact_match score = 0.0
    stats_b = next(m for m in agg["models_stats"] if m["model_id"] == "mock:model-b")
    assert stats_b["runs_count"] == 2
    assert stats_b["successful_runs"] == 1
    assert stats_b["error_rate"] == 0.5
    assert stats_b["mean_metrics"]["exact_match"] == 0.0

    # Verify Pareto points generated for chart
    assert len(agg["pareto_points"]) == 2
    pareto_a = next(p for p in agg["pareto_points"] if p["model_id"] == "mock:model-a")
    assert pareto_a["quality_score"] == 1.0
    assert pareto_a["total_cost"] == 0.000110


# ---------------------------------------------------------------------------
# 2. Datasets & Experiments API Endpoints Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_datasets_endpoint():
    """Verify GET /api/datasets returns datasets."""
    from unittest.mock import MagicMock

    from app.db.base import get_session
    ds = BenchmarkDataset(
        id="ds-1",
        name="Core Benchmark",
        version=1,
        description="Seed benchmark",
        created_at=datetime.now(timezone.utc),
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [(ds, 24)]
    mock_session.execute.return_value = mock_result

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/datasets")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["name"] == "Core Benchmark"
            assert data[0]["version"] == 1
            assert data[0]["case_count"] == 24
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_experiment_endpoint():
    """Verify POST /api/experiments creates a pending experiment record."""
    from unittest.mock import MagicMock

    from app.db.base import get_session
    ds = BenchmarkDataset(
        id="ds-1",
        name="Core Benchmark",
        version=1,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = ds
    mock_session.execute.return_value = mock_result
    mock_session.commit = AsyncMock()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        payload = {
            "name": "Sprint 9 Multi-Model Run",
            "dataset_id": "ds-1",
            "models": ["mock:mock-1", "mock:mock-slow-1"],
            "include_llm_judge": False,
        }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/experiments", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "Sprint 9 Multi-Model Run"
            assert data["dataset_id"] == "ds-1"
            assert data["status"] == "pending"
            assert data["include_llm_judge"] is False
            assert len(data["models"]) == 2
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_experiment_nonexistent_dataset():
    """Verify POST /api/experiments returns 404 when dataset does not exist."""
    from unittest.mock import MagicMock

    from app.db.base import get_session
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        payload = {
            "name": "Invalid Experiment",
            "dataset_id": "nonexistent-id",
            "models": ["mock:mock-1"],
        }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/experiments", json=payload)
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_start_experiment_run_endpoint():
    """Verify POST /api/experiments/{id}/run kicks off background runner."""
    from unittest.mock import MagicMock

    from app.db.base import get_session
    exp = Experiment(
        id="exp-123",
        name="Test Run",
        dataset_id="ds-1",
        models=["mock:mock-1"],
        status="pending",
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = exp
    mock_session.execute.return_value = mock_result

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        with patch("app.api.experiments.run_experiment", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/api/experiments/exp-123/run")
                assert resp.status_code == 200
                data = resp.json()
                assert data["experiment_id"] == "exp-123"
                assert data["status"] == "running"
    finally:
        app.dependency_overrides.clear()
