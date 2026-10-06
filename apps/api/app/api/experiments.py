"""API endpoints for benchmark datasets and multi-model experiments."""
import asyncio
import logging
import subprocess
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import get_session
from app.db.models import (
    BenchmarkCase,
    BenchmarkDataset,
    Experiment,
    ExperimentRun,
    ModelRun,
    Race,
)
from app.experiments.comparison import aggregate_experiment_results
from app.experiments.runner import EXPERIMENT_PROGRESS, run_experiment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["experiments"])


def get_git_commit() -> str | None:
    """Captures current git commit SHA if git repository is available."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
        return out.decode("utf-8").strip()[:10]
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class CreateExperimentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Experiment title")
    dataset_id: str = Field(..., description="ID of the immutable benchmark dataset")
    models: list[str] = Field(
        ...,
        min_length=1,
        max_length=16,
        description="List of model specs ('provider:model')",
    )
    include_llm_judge: bool = Field(
        default=False,
        description="Explicit opt-in to run paid blind LLM judging on each benchmark case",
    )


# ---------------------------------------------------------------------------
# Benchmark Datasets Endpoints
# ---------------------------------------------------------------------------
@router.get("/datasets")
async def list_datasets(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict[str, Any]]:
    """Lists all available versioned benchmark datasets."""
    stmt = (
        select(
            BenchmarkDataset,
            func.count(BenchmarkCase.id).label("case_count"),
        )
        .outerjoin(BenchmarkCase, BenchmarkCase.dataset_id == BenchmarkDataset.id)
        .group_by(BenchmarkDataset.id)
        .order_by(BenchmarkDataset.name, desc(BenchmarkDataset.version))
    )
    res = await session.execute(stmt)
    rows = res.all()

    return [
        {
            "id": ds.id,
            "name": ds.name,
            "version": ds.version,
            "description": ds.description,
            "case_count": case_count,
            "created_at": ds.created_at.isoformat() if ds.created_at else None,
        }
        for ds, case_count in rows
    ]


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Retrieves full details and cases for a specific benchmark dataset."""
    stmt = (
        select(BenchmarkDataset)
        .where(BenchmarkDataset.id == dataset_id)
        .options(selectinload(BenchmarkDataset.cases))
    )
    res = await session.execute(stmt)
    ds = res.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return {
        "id": ds.id,
        "name": ds.name,
        "version": ds.version,
        "description": ds.description,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "cases": [
            {
                "id": c.id,
                "category": c.category,
                "question": c.question,
                "expected_answer": c.expected_answer,
                "gold_chunk_ids": c.gold_chunk_ids,
            }
            for c in ds.cases
        ],
    }


# ---------------------------------------------------------------------------
# Experiments Endpoints
# ---------------------------------------------------------------------------
@router.post("/experiments")
async def create_experiment(
    body: CreateExperimentRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Creates a new experiment targeting a dataset and set of models."""
    # Verify dataset exists
    stmt = select(BenchmarkDataset).where(BenchmarkDataset.id == body.dataset_id)
    res = await session.execute(stmt)
    ds = res.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Benchmark dataset not found")

    exp_id = uuid.uuid4().hex
    commit_sha = get_git_commit()

    experiment = Experiment(
        id=exp_id,
        name=body.name,
        dataset_id=body.dataset_id,
        models=body.models,
        git_commit=commit_sha,
        status="pending",
        include_llm_judge=body.include_llm_judge,
    )
    session.add(experiment)
    await session.commit()

    return {
        "id": experiment.id,
        "name": experiment.name,
        "dataset_id": experiment.dataset_id,
        "models": experiment.models,
        "git_commit": experiment.git_commit,
        "status": experiment.status,
        "include_llm_judge": experiment.include_llm_judge,
    }


@router.get("/experiments")
async def list_experiments(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict[str, Any]]:
    """Lists past experiments ordered newest first."""
    stmt = (
        select(Experiment)
        .options(selectinload(Experiment.dataset))
        .order_by(desc(Experiment.created_at))
    )
    res = await session.execute(stmt)
    experiments = res.scalars().all()

    return [
        {
            "id": exp.id,
            "name": exp.name,
            "dataset_id": exp.dataset_id,
            "dataset_name": exp.dataset.name if exp.dataset else "Unknown",
            "dataset_version": exp.dataset.version if exp.dataset else 1,
            "models": exp.models,
            "model_count": len(exp.models),
            "status": exp.status,
            "git_commit": exp.git_commit,
            "include_llm_judge": exp.include_llm_judge,
            "created_at": exp.created_at.isoformat() if exp.created_at else None,
            "finished_at": exp.finished_at.isoformat() if exp.finished_at else None,
        }
        for exp in experiments
    ]


@router.get("/experiments/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Retrieves metadata and status for a single experiment."""
    stmt = (
        select(Experiment)
        .where(Experiment.id == experiment_id)
        .options(selectinload(Experiment.dataset))
    )
    res = await session.execute(stmt)
    exp = res.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    return {
        "id": exp.id,
        "name": exp.name,
        "dataset_id": exp.dataset_id,
        "dataset_name": exp.dataset.name if exp.dataset else "Unknown",
        "dataset_version": exp.dataset.version if exp.dataset else 1,
        "models": exp.models,
        "status": exp.status,
        "git_commit": exp.git_commit,
        "include_llm_judge": exp.include_llm_judge,
        "error_message": exp.error_message,
        "created_at": exp.created_at.isoformat() if exp.created_at else None,
        "finished_at": exp.finished_at.isoformat() if exp.finished_at else None,
    }


@router.post("/experiments/{experiment_id}/run")
async def start_experiment_run(
    experiment_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Triggers the background experiment runner task."""
    stmt = select(Experiment).where(Experiment.id == experiment_id)
    res = await session.execute(stmt)
    exp = res.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    if exp.status == "running":
        return {"experiment_id": experiment_id, "status": "running", "message": "Already running"}

    # Launch background asyncio task
    asyncio.create_task(run_experiment(experiment_id))

    return {
        "experiment_id": experiment_id,
        "status": "running",
        "message": "Experiment run launched in background",
    }


@router.get("/experiments/{experiment_id}/status")
async def get_experiment_status(
    experiment_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Live polling endpoint returning progress for an active or completed experiment."""
    progress = EXPERIMENT_PROGRESS.get(experiment_id)
    if progress:
        return {"experiment_id": experiment_id, **progress}

    # Fall back to database status
    stmt = select(Experiment).where(Experiment.id == experiment_id)
    res = await session.execute(stmt)
    exp = res.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    return {
        "experiment_id": experiment_id,
        "status": exp.status,
        "total_cases": 0,
        "completed_cases": 0,
        "error": exp.error_message,
    }


@router.get("/experiments/{experiment_id}/results")
async def get_experiment_results(
    experiment_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Computes and returns the multi-dimensional comparison results and Pareto tradeoff points."""
    stmt = (
        select(Experiment)
        .where(Experiment.id == experiment_id)
        .options(
            selectinload(Experiment.dataset),
            selectinload(Experiment.experiment_runs)
            .selectinload(ExperimentRun.benchmark_case),
            selectinload(Experiment.experiment_runs)
            .selectinload(ExperimentRun.race)
            .selectinload(Race.model_runs)
            .selectinload(ModelRun.evaluations),
        )
    )
    res = await session.execute(stmt)
    exp = res.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    runs = list(exp.experiment_runs)
    return aggregate_experiment_results(exp, runs)
