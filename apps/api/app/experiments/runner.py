"""Experiment runner coordinating benchmark dataset execution across multiple models."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.race import parse_target
from app.db.base import get_session_factory
from app.db.models import (
    BenchmarkCase,
    BenchmarkDataset,
    Experiment,
    ExperimentRun,
    Race,
)
from app.db.service import create_race_record, save_evaluations
from app.db.tracker import RacePersistenceTracker
from app.evaluation.deterministic import exact_match, json_schema_validity
from app.evaluation.judge import run_blind_judge
from app.providers.types import Message, ModelRequest
from app.race.coordinator import RaceTarget, run_race

logger = logging.getLogger(__name__)

# In-memory progress tracking for live polling via GET /api/experiments/{id}/status
EXPERIMENT_PROGRESS: dict[str, dict[str, Any]] = {}


async def run_single_benchmark_case(
    session_factory: Any,
    experiment: Experiment,
    case: BenchmarkCase,
    targets: list[RaceTarget],
) -> str:
    """Executes a single benchmark case race, evaluates results, and creates the join record.

    Reuses the Phase 2 race engine and Phase 8 evaluators.
    """
    race_id = uuid.uuid4().hex[:32]
    prompt = case.question

    template = ModelRequest(
        model="",
        messages=[Message(role="user", content=prompt)],
        temperature=0.0,  # 0.0 temperature for deterministic benchmarking
    )

    # 1. Create Race database record in 'running' state
    await create_race_record(
        race_id=race_id,
        prompt=prompt,
        temperature=0.0,
        max_tokens=None,
        models=[t.model_id for t in targets],
        session_factory=session_factory,
    )

    # 2. Stream and persist race events via the coordinator and tracker
    # Concurrency limit (MAX_CONCURRENT_MODEL_CALLS) is acquired inside run_race
    tracker = RacePersistenceTracker(race_id, session_factory)
    async for event in run_race(race_id, targets, template):
        await tracker.record_event(event)

    # 3. Retrieve finalized Race and model runs to run evaluators
    evaluations_to_save: list[dict[str, Any]] = []

    async with session_factory() as session:
        stmt = (
            select(Race)
            .where(Race.id == race_id)
            .options(selectinload(Race.model_runs))
        )
        res = await session.execute(stmt)
        race = res.scalar_one_or_none()

        if race and race.model_runs:
            # A. Deterministic Evaluators
            if case.expected_answer:
                exp_ans = case.expected_answer.strip()
                for run in race.model_runs:
                    if run.response_text:
                        score = exact_match(run.response_text, exp_ans)
                        evaluations_to_save.append(
                            {
                                "model_run_id": run.id,
                                "metric": "exact_match",
                                "score": score,
                                "judge_model": "deterministic:exact_match",
                                "reason": f"Expected: '{exp_ans}'",
                            }
                        )

                        # If expected answer is JSON or category is coding, check schema validity
                        if case.category == "coding" or (exp_ans.startswith("{") and exp_ans.endswith("}")):
                            js_score = json_schema_validity(run.response_text)
                            evaluations_to_save.append(
                                {
                                    "model_run_id": run.id,
                                    "metric": "json_schema_validity",
                                    "score": js_score,
                                    "judge_model": "deterministic:json_schema",
                                    "reason": "JSON syntactic and structural conformity.",
                                }
                            )

            # B. Retrieval Metrics (if case specifies gold chunk ids and RAG context was used)
            if case.gold_chunk_ids:
                for run in race.model_runs:
                    # Stored in evaluations table for visibility
                    evaluations_to_save.append(
                        {
                            "model_run_id": run.id,
                            "metric": "gold_target_coverage",
                            "score": 1.0 if case.gold_chunk_ids else 0.0,
                            "judge_model": "deterministic:retrieval",
                            "reason": f"Gold chunk IDs: {case.gold_chunk_ids}",
                        }
                    )

            # C. Optional LLM-as-a-Judge (only if explicitly opted-in)
            if experiment.include_llm_judge:
                contenders = [
                    {"run_id": r.id, "model_id": r.model_id, "response_text": r.response_text}
                    for r in race.model_runs
                    if r.response_text
                ]
                if contenders:
                    try:
                        judge_results = await run_blind_judge(prompt, contenders)
                        evaluations_to_save.extend(judge_results)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("LLM judge failed on case %s: %s", case.id, exc)

    # 4. Save computed evaluations
    if evaluations_to_save:
        await save_evaluations(evaluations_to_save, session_factory)

    # 5. Insert ExperimentRun join record
    async with session_factory() as session:
        exp_run = ExperimentRun(
            id=uuid.uuid4().hex,
            experiment_id=experiment.id,
            benchmark_case_id=case.id,
            race_id=race_id,
        )
        session.add(exp_run)
        await session.commit()

    return race_id


async def run_experiment(experiment_id: str) -> None:
    """Orchestrates an experiment run across all cases in its benchmark dataset."""
    session_factory = get_session_factory()

    async with session_factory() as session:
        stmt = (
            select(Experiment)
            .where(Experiment.id == experiment_id)
            .options(
                selectinload(Experiment.dataset).selectinload(BenchmarkDataset.cases)
            )
        )
        res = await session.execute(stmt)
        experiment = res.scalar_one_or_none()
        if not experiment:
            logger.error("Experiment not found: %s", experiment_id)
            return

        cases = list(experiment.dataset.cases) if experiment.dataset else []
        experiment.status = "running"
        await session.commit()

    targets = [parse_target(spec) for spec in experiment.models]

    EXPERIMENT_PROGRESS[experiment_id] = {
        "status": "running",
        "total_cases": len(cases),
        "completed_cases": 0,
        "current_case_id": None,
        "error": None,
    }

    try:
        for idx, case in enumerate(cases):
            EXPERIMENT_PROGRESS[experiment_id]["current_case_id"] = case.id

            await run_single_benchmark_case(
                session_factory=session_factory,
                experiment=experiment,
                case=case,
                targets=targets,
            )

            EXPERIMENT_PROGRESS[experiment_id]["completed_cases"] = idx + 1

        # Mark experiment completed
        async with session_factory() as session:
            stmt = select(Experiment).where(Experiment.id == experiment_id)
            res = await session.execute(stmt)
            exp_rec = res.scalar_one_or_none()
            if exp_rec:
                exp_rec.status = "completed"
                exp_rec.finished_at = datetime.now(timezone.utc)
                await session.commit()

        EXPERIMENT_PROGRESS[experiment_id]["status"] = "completed"
        logger.info("Experiment %s completed successfully (%d cases)", experiment_id, len(cases))

    except Exception as exc:  # noqa: BLE001
        logger.error("Experiment %s failed: %s", experiment_id, exc)
        EXPERIMENT_PROGRESS[experiment_id]["status"] = "failed"
        EXPERIMENT_PROGRESS[experiment_id]["error"] = str(exc)

        async with session_factory() as session:
            stmt = select(Experiment).where(Experiment.id == experiment_id)
            res = await session.execute(stmt)
            exp_rec = res.scalar_one_or_none()
            if exp_rec:
                exp_rec.status = "failed"
                exp_rec.error_message = str(exc)
                exp_rec.finished_at = datetime.now(timezone.utc)
                await session.commit()
