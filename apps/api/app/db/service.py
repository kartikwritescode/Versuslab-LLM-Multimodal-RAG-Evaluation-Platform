from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Evaluation, ModelRun, Race


async def create_race_record(
    session: AsyncSession,
    race_id: str,
    prompt: str,
    temperature: float,
    max_tokens: int | None,
    target_model_ids: list[str],
    shared_context_hash: str | None = None,
    document_id: str | None = None,
) -> None:
    """Inserts an initial race record and queued model_runs records in one transaction."""
    race = Race(
        id=race_id,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        status="running",
        shared_context_hash=shared_context_hash,
        document_id=document_id,
        created_at=datetime.now(timezone.utc),
    )
    session.add(race)

    for model_id in target_model_ids:
        run = ModelRun(
            race_id=race_id,
            model_id=model_id,
            status="queued",
            response_text="",
            context_hash=shared_context_hash,
        )
        session.add(run)

    await session.commit()


async def mark_model_started(
    session: AsyncSession,
    race_id: str,
    model_id: str,
) -> None:
    """Updates a model_run's status to streaming."""
    stmt = (
        update(ModelRun)
        .where(ModelRun.race_id == race_id, ModelRun.model_id == model_id)
        .values(status="streaming")
    )
    await session.execute(stmt)
    await session.commit()


async def mark_model_finished(
    session: AsyncSession,
    race_id: str,
    model_id: str,
    status: str,
    ttft_ms: int | None,
    latency_ms: int | None,
    input_tokens: int | None,
    output_tokens: int | None,
    finish_reason: str | None,
    error_message: str | None,
    response_text: str,
    citations_valid: bool | None = None,
    invalid_citations: list[str] | None = None,
    input_cost: Decimal | None = None,
    output_cost: Decimal | None = None,
    total_cost: Decimal | None = None,
    chunk_count: int | None = None,
) -> None:
    """Updates a model_run's final status, timing metrics, token usage, text, citations, and costs."""
    from app.evaluation.metrics import calculate_all_metrics

    # Calculate all enhanced metrics
    metrics = calculate_all_metrics(
        model_id=model_id,
        ttft_ms=ttft_ms,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        response_text=response_text,
        total_cost=total_cost,
        evaluations=None,  # Evaluations are calculated separately later
        chunk_count=chunk_count,
    )

    stmt = (
        update(ModelRun)
        .where(ModelRun.race_id == race_id, ModelRun.model_id == model_id)
        .values(
            status=status,
            ttft_ms=ttft_ms,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=finish_reason,
            error_message=error_message,
            response_text=response_text,
            citations_valid=citations_valid,
            invalid_citations=invalid_citations,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            # Enhanced metrics
            tokens_per_second=metrics["tokens_per_second"],
            time_per_output_token=metrics["time_per_output_token"],
            input_tokens_per_second=metrics["input_tokens_per_second"],
            cost_per_1k_tokens=metrics["cost_per_1k_tokens"],
            cost_per_second=metrics["cost_per_second"],
            response_word_count=metrics["response_word_count"],
            response_char_count=metrics["response_char_count"],
            response_sentence_count=metrics["response_sentence_count"],
            confidence_score=metrics["confidence_score"],
            qualifier_count=metrics["qualifier_count"],
            context_utilization_percent=metrics["context_utilization_percent"],
            model_max_context=metrics["model_max_context"],
            streaming_chunk_count=metrics["streaming_chunk_count"],
            avg_chunk_size=metrics["avg_chunk_size"],
            cost_quality_ratio=metrics["cost_quality_ratio"],
        )
    )
    await session.execute(stmt)
    await session.commit()


async def mark_race_finished(
    session: AsyncSession,
    race_id: str,
    status: str,
) -> None:
    """Updates race status to completed or cancelled with a finished_at timestamp."""
    stmt = (
        update(Race)
        .where(Race.id == race_id)
        .values(
            status=status,
            finished_at=datetime.now(timezone.utc),
        )
    )
    await session.execute(stmt)
    await session.commit()


async def list_races(
    session: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Returns a paginated list of past races ordered newest first, along with total count."""
    count_stmt = select(func.count(Race.id))
    total = (await session.scalar(count_stmt)) or 0

    # Query races with count of model runs
    stmt = (
        select(Race)
        .options(selectinload(Race.model_runs))
        .order_by(desc(Race.created_at))
        .limit(limit)
        .offset(offset)
    )
    result = await session.scalars(stmt)
    races = result.all()

    items = [
        {
            "id": r.id,
            "prompt": r.prompt,
            "temperature": r.temperature,
            "max_tokens": r.max_tokens,
            "status": r.status,
            "model_count": len(r.model_runs),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in races
    ]

    return items, total


async def get_race_detail(
    session: AsyncSession,
    race_id: str,
) -> Race | None:
    """Fetches a single race with all associated model_runs and evaluations loaded."""
    stmt = (
        select(Race)
        .options(
            selectinload(Race.model_runs).selectinload(ModelRun.evaluations)
        )
        .where(Race.id == race_id)
    )
    return await session.scalar(stmt)


async def save_evaluations(
    session: AsyncSession,
    evaluations: list[dict[str, Any]],
) -> None:
    """Inserts evaluation records into PostgreSQL and updates aggregate quality scores."""
    from app.evaluation.metrics import calculate_aggregate_quality_score

    # Insert evaluations
    for item in evaluations:
        eval_record = Evaluation(
            model_run_id=item["model_run_id"],
            metric=item["metric"],
            score=item["score"],
            judge_model=item.get("judge_model"),
            reason=item.get("reason"),
        )
        session.add(eval_record)
    await session.commit()

    # Update aggregate quality scores for affected model runs
    model_run_ids = {item["model_run_id"] for item in evaluations}
    for model_run_id in model_run_ids:
        # Get all evaluations for this model run
        eval_stmt = select(Evaluation).where(Evaluation.model_run_id == model_run_id)
        evals = await session.scalars(eval_stmt)
        eval_list = [{"score": e.score} for e in evals.all()]

        # Calculate aggregate score
        aggregate_score = calculate_aggregate_quality_score(eval_list)

        # Update model run
        if aggregate_score is not None:
            from app.evaluation.metrics import calculate_cost_quality_ratio
            total_cost_val = await session.scalar(
                select(ModelRun.total_cost).where(ModelRun.id == model_run_id)
            )
            ratio = calculate_cost_quality_ratio(aggregate_score, total_cost_val)

            update_stmt = (
                update(ModelRun)
                .where(ModelRun.id == model_run_id)
                .values(
                    aggregate_quality_score=aggregate_score,
                    cost_quality_ratio=ratio,
                )
            )
            await session.execute(update_stmt)

    await session.commit()
