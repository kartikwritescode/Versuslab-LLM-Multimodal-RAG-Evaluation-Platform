import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import RETRIEVAL_LATENCY_SECONDS
from app.core.rate_limit import create_rate_limiter
from app.db.base import get_session, get_session_factory
from app.db.models import DocumentChunk, ModelRun
from app.db.service import (
    create_race_record,
    get_race_detail,
    list_races,
    save_evaluations,
)
from app.db.tracker import RacePersistenceTracker
from app.evaluation.citation_faithfulness import evaluate_citation_faithfulness
from app.evaluation.judge import run_blind_judge
from app.providers.embeddings import get_embedding_provider
from app.providers.registry import DEFAULT_MODELS, PROVIDERS
from app.providers.types import Message, ModelRequest
from app.race.coordinator import RaceTarget, cancel_race, run_race
from app.retrieval.context import canonicalize_context
from app.retrieval.hybrid import hybrid_retrieve

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

MAX_CONTENDERS = 8
race_rate_limiter = create_rate_limiter(settings.race_rate_limit_per_minute)


class RaceRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="User prompt sent to all contender models")
    models: list[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_CONTENDERS,
        description="List of model specs ('provider:model' or 'provider')",
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    race_id: str | None = Field(
        default=None,
        description="Optional custom race ID (auto-generated if omitted)",
    )
    document_id: str | None = Field(
        default=None,
        description="Optional attached document ID for RAG context",
    )


def parse_target(spec: str) -> RaceTarget:
    """Parses a 'provider:model' string, falling back to DEFAULT_MODELS if model is omitted."""
    provider_name, sep, model = spec.partition(":")
    provider = PROVIDERS.get(provider_name)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider_name}")

    default_model = DEFAULT_MODELS.get(provider_name, "")
    chosen_model = model if (sep and model) else default_model
    if not chosen_model:
        raise HTTPException(
            status_code=400,
            detail=f"No default model configured for provider: {provider_name}",
        )

    return RaceTarget(
        model_id=f"{provider_name}:{chosen_model}",
        provider=provider,
        model=chosen_model,
    )


async def sse_race(
    race_id: str,
    targets: list[RaceTarget],
    template: ModelRequest,
    valid_citation_ids: set[str] | None = None,
) -> AsyncIterator[str]:
    """Streams race events formatted into SSE data frames, omitting null fields.

    Maintains persistence in PostgreSQL without adding latency to the live stream.
    """
    tracker = RacePersistenceTracker(
        race_id, get_session_factory(), valid_citation_ids=valid_citation_ids
    )

    async for event in run_race(race_id, targets, template):
        # 1. Yield event frame to SSE client FIRST so client experiences zero added latency
        yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

        # 2. Update database asynchronously in background without blocking stream delivery
        await tracker.record_event(event)


@router.post("/races", dependencies=[Depends(race_rate_limiter)])
async def start_race(
    body: RaceRequest,
) -> StreamingResponse:
    # Resolve and validate targets before starting the SSE stream
    targets = [parse_target(spec) for spec in body.models]

    ids = [t.model_id for t in targets]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail="Duplicate models in race")

    race_id = body.race_id or uuid.uuid4().hex

    messages = [Message(role="user", content=body.prompt)]
    shared_context_hash: str | None = None
    valid_citation_ids: set[str] | None = None

    # If a document is attached, perform hybrid retrieval and prepend canonical system prompt
    if body.document_id:
        try:
            retrieval_start = time.monotonic()
            async with get_session_factory()() as session:
                chunks = await hybrid_retrieve(
                    session=session,
                    document_id=body.document_id,
                    query=body.prompt,
                    embedding_provider=get_embedding_provider(),
                    top_k=settings.rag_top_k,
                )
                RETRIEVAL_LATENCY_SECONDS.observe(time.monotonic() - retrieval_start)
                context_str, shared_context_hash, valid_citation_ids = canonicalize_context(chunks)
                messages = [
                    Message(role="system", content=context_str),
                    Message(role="user", content=body.prompt),
                ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to retrieve document context for race %s: %s", race_id, exc)

    # Rule 6 Fairness: template is created ONCE; only model name is overridden per target
    template = ModelRequest(
        model="",
        messages=messages,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
    )

    # Pre-seed initial race and model_runs in PostgreSQL before stream starts
    try:
        async with get_session_factory()() as session:
            await create_race_record(
                session=session,
                race_id=race_id,
                prompt=body.prompt,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
                target_model_ids=ids,
                shared_context_hash=shared_context_hash,
                document_id=body.document_id,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to create initial DB race record: %s", exc)

    return StreamingResponse(
        sse_race(race_id, targets, template, valid_citation_ids=valid_citation_ids),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/races/{race_id}/cancel")
async def cancel_race_endpoint(
    race_id: str,
) -> dict[str, str]:
    """Cancels an ongoing race and deregisters its background tasks."""
    cancelled = cancel_race(race_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Race not found or already completed")
    return {"status": "cancelled", "race_id": race_id}


@router.get("/races")
async def list_races_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Returns a paginated list of past races ordered newest first."""
    items, total = await list_races(session, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _serialize_model_run(r: ModelRun) -> dict[str, Any]:
    """Serializes a ModelRun record, computing fallback metrics on the fly if not cached in DB."""
    eval_list = [{"score": e.score} for e in (r.evaluations or [])]

    # Check if enhanced metrics need calculation (e.g. for historical runs)
    needs_fallback = (
        r.tokens_per_second is None
        and r.latency_ms is not None
        and r.output_tokens is not None
    ) or (
        r.aggregate_quality_score is None and len(eval_list) > 0
    ) or (
        r.confidence_score is None and bool(r.response_text)
    )

    fb: dict[str, Any] = {}
    if needs_fallback:
        from app.evaluation.metrics import calculate_all_metrics
        fb = calculate_all_metrics(
            model_id=r.model_id,
            ttft_ms=r.ttft_ms,
            latency_ms=r.latency_ms,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            response_text=r.response_text or "",
            total_cost=r.total_cost,
            evaluations=eval_list,
            chunk_count=r.streaming_chunk_count,
        )

    tps = r.tokens_per_second if r.tokens_per_second is not None else fb.get("tokens_per_second")
    tpot = r.time_per_output_token if r.time_per_output_token is not None else fb.get("time_per_output_token")
    input_tps = (
        r.input_tokens_per_second
        if r.input_tokens_per_second is not None
        else fb.get("input_tokens_per_second")
    )
    cost_1k = (
        float(r.cost_per_1k_tokens)
        if r.cost_per_1k_tokens is not None
        else (float(fb["cost_per_1k_tokens"]) if fb.get("cost_per_1k_tokens") is not None else None)
    )
    cost_sec = (
        float(r.cost_per_second)
        if r.cost_per_second is not None
        else (float(fb["cost_per_second"]) if fb.get("cost_per_second") is not None else None)
    )
    words = r.response_word_count if r.response_word_count is not None else fb.get("response_word_count")
    chars = r.response_char_count if r.response_char_count is not None else fb.get("response_char_count")
    sentences = (
        r.response_sentence_count
        if r.response_sentence_count is not None
        else fb.get("response_sentence_count")
    )
    agg_score = (
        r.aggregate_quality_score
        if r.aggregate_quality_score is not None
        else fb.get("aggregate_quality_score")
    )
    conf_score = (
        r.confidence_score if r.confidence_score is not None else fb.get("confidence_score")
    )
    qual_count = (
        r.qualifier_count if r.qualifier_count is not None else fb.get("qualifier_count", 0)
    )
    ctx_util = (
        r.context_utilization_percent
        if r.context_utilization_percent is not None
        else fb.get("context_utilization_percent")
    )
    max_ctx = (
        r.model_max_context if r.model_max_context is not None else fb.get("model_max_context")
    )
    chunk_cnt = (
        r.streaming_chunk_count
        if r.streaming_chunk_count is not None
        else fb.get("streaming_chunk_count")
    )
    avg_chunk = r.avg_chunk_size if r.avg_chunk_size is not None else fb.get("avg_chunk_size")
    cq_ratio = (
        r.cost_quality_ratio if r.cost_quality_ratio is not None else fb.get("cost_quality_ratio")
    )

    return {
        "id": r.id,
        "model_id": r.model_id,
        "status": r.status,
        "context_hash": r.context_hash,
        "citations_valid": r.citations_valid,
        "invalid_citations": r.invalid_citations,
        "ttft_ms": r.ttft_ms,
        "latency_ms": r.latency_ms,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "input_cost": float(r.input_cost) if r.input_cost is not None else None,
        "output_cost": float(r.output_cost) if r.output_cost is not None else None,
        "total_cost": float(r.total_cost) if r.total_cost is not None else None,
        "finish_reason": r.finish_reason,
        "error_message": r.error_message,
        "response_text": r.response_text,
        "evaluations": [
            {
                "id": e.id,
                "metric": e.metric,
                "score": e.score,
                "judge_model": e.judge_model,
                "reason": e.reason,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in (r.evaluations or [])
        ],
        # Enhanced Performance, Economic, Quality & Content Metrics
        "tokens_per_second": tps,
        "time_per_output_token": tpot,
        "input_tokens_per_second": input_tps,
        "cost_per_1k_tokens": cost_1k,
        "cost_per_second": cost_sec,
        "response_word_count": words,
        "response_char_count": chars,
        "response_sentence_count": sentences,
        "aggregate_quality_score": agg_score,
        "confidence_score": conf_score,
        "qualifier_count": qual_count,
        "context_utilization_percent": ctx_util,
        "model_max_context": max_ctx,
        "streaming_chunk_count": chunk_cnt,
        "avg_chunk_size": avg_chunk,
        "cost_quality_ratio": cq_ratio,
    }


@router.get("/races/{race_id}")
async def get_race_endpoint(
    race_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Returns a single race with all associated model_runs."""
    race = await get_race_detail(session, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Race not found")

    return {
        "id": race.id,
        "prompt": race.prompt,
        "temperature": race.temperature,
        "max_tokens": race.max_tokens,
        "status": race.status,
        "shared_context_hash": race.shared_context_hash,
        "document_id": race.document_id,
        "created_at": race.created_at.isoformat() if race.created_at else None,
        "finished_at": race.finished_at.isoformat() if race.finished_at else None,
        "model_runs": [_serialize_model_run(r) for r in race.model_runs],
    }


@router.post("/races/{race_id}/evaluate")
async def evaluate_race_endpoint(
    race_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Runs blind LLM-as-judge and citation faithfulness evaluation for a completed race."""
    race = await get_race_detail(session, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Race not found")

    if race.status not in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail="Race is still running; wait for completion before evaluating")

    contenders = [
        {
            "run_id": r.id,
            "model_id": r.model_id,
            "response_text": r.response_text,
        }
        for r in race.model_runs
        if r.response_text
    ]

    all_evaluations: list[dict[str, Any]] = []

    # 1. Blind LLM-as-judge across all completed contenders
    if contenders:
        judge_evals = await run_blind_judge(
            prompt=race.prompt,
            contenders=contenders,
            judge_model=settings.judge_model,
        )
        all_evaluations.extend(judge_evals)

    # 2. Citation faithfulness evaluation when document context was used
    if race.document_id and contenders:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == race.document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        result = await session.scalars(stmt)
        retrieved_chunks = list(result.all())

        for contender in contenders:
            faithfulness_evals = await evaluate_citation_faithfulness(
                prompt=race.prompt,
                answer=contender["response_text"],
                retrieved_chunks=retrieved_chunks,
                judge_model=settings.judge_model,
            )
            for fe in faithfulness_evals:
                fe["model_run_id"] = contender["run_id"]
                all_evaluations.append(fe)

    # 3. Persist evaluation records in PostgreSQL
    if all_evaluations:
        await save_evaluations(session, all_evaluations)

    return {
        "race_id": race_id,
        "evaluated": True,
        "evaluations_count": len(all_evaluations),
    }