import asyncio
import itertools
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.metrics import (
    MODEL_LATENCY_SECONDS,
    MODEL_REQUESTS_TOTAL,
    MODEL_TTFT_SECONDS,
    RACES_TOTAL,
)
from app.providers.base import ModelProvider
from app.providers.types import ModelRequest
from app.race.events import EventType, RaceEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RaceTarget:
    model_id: str
    provider: ModelProvider
    model: str


@dataclass
class ActiveRace:
    tasks: list[asyncio.Task[None]]
    cancelled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


# In-memory registry of ongoing races to enable cancellation by race_id
RACES: dict[str, ActiveRace] = {}

# Global semaphore to limit concurrent outbound connections across all races
_SEMAPHORE: asyncio.Semaphore | None = None


def get_semaphore() -> asyncio.Semaphore:
    """Returns the global semaphore enforcing MAX_CONCURRENT_MODEL_CALLS."""
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(settings.max_concurrent_model_calls)
    return _SEMAPHORE


def cancel_race(race_id: str) -> bool:
    """Cancels all active tasks for a race. Returns True if found, False otherwise."""
    race = RACES.get(race_id)
    if race is None:
        return False

    race.cancelled = True
    for task in race.tasks:
        if not task.done():
            task.cancel()
    return True


async def _run_model(
    target: RaceTarget,
    template: ModelRequest,
    race_id: str,
    queue: asyncio.Queue[RaceEvent | None],
) -> None:
    """Worker task executing one contender's stream loop with concurrency limits,

    per-model deadlines, and safe transient connection retries.
    """
    provider_name = target.model_id.partition(":")[0]
    model_name = target.model
    start_time = time.monotonic()

    def emit(event_type: EventType, **fields: Any) -> None:
        queue.put_nowait(
            RaceEvent(
                type=event_type,
                race_id=race_id,
                model_id=target.model_id,
                **fields,
            )
        )

    emit("model.started")
    logger.info(
        "Model execution started",
        extra={"race_id": race_id, "model_id": target.model_id, "event_type": "model.started"},
    )

    # Rule 6 Fairness: only the model name differs between contender requests
    request = template.model_copy(update={"model": target.model})
    assert request.messages == template.messages, (
        "Fairness violation: contender request mutated shared messages"
    )

    # Acquire concurrency permit so many contenders do not overwhelm outbound sockets
    async with get_semaphore():
        attempt = 0
        max_retries = settings.max_connection_retries

        while True:
            first_token_received = False
            try:
                # Start with strict first-token deadline, reschedule to model_timeout_s on first delta
                async with asyncio.timeout(settings.first_token_timeout_s) as timeout_ctx:
                    async for delta in target.provider.stream(request):
                        if not first_token_received and delta.text:
                            first_token_received = True
                            ttft_seconds = time.monotonic() - start_time
                            MODEL_TTFT_SECONDS.labels(
                                provider=provider_name, model=model_name
                            ).observe(ttft_seconds)
                            logger.info(
                                "Model emitted first token",
                                extra={
                                    "race_id": race_id,
                                    "model_id": target.model_id,
                                    "ttft_ms": round(ttft_seconds * 1000, 2),
                                },
                            )
                            loop = asyncio.get_running_loop()
                            timeout_ctx.reschedule(loop.time() + settings.model_timeout_s)

                        if delta.text:
                            emit("model.delta", text=delta.text)
                        if delta.finish_reason is not None:
                            latency_seconds = time.monotonic() - start_time
                            MODEL_LATENCY_SECONDS.labels(
                                provider=provider_name, model=model_name
                            ).observe(latency_seconds)
                            MODEL_REQUESTS_TOTAL.labels(
                                provider=provider_name, model=model_name, status="completed"
                            ).inc()
                            logger.info(
                                "Model completed response",
                                extra={
                                    "race_id": race_id,
                                    "model_id": target.model_id,
                                    "latency_ms": round(latency_seconds * 1000, 2),
                                    "finish_reason": delta.finish_reason,
                                },
                            )
                            emit(
                                "model.completed",
                                finish_reason=delta.finish_reason,
                                usage=delta.usage,
                            )
                # Stream completed successfully
                break

            except (httpx.ConnectError, httpx.ConnectTimeout) as conn_exc:
                if not first_token_received and attempt < max_retries:
                    attempt += 1
                    logger.warning(
                        "Transient connection failure, retrying contender",
                        extra={"race_id": race_id, "model_id": target.model_id, "attempt": attempt},
                    )
                    await asyncio.sleep(0.5 * attempt)
                    continue

                MODEL_REQUESTS_TOTAL.labels(
                    provider=provider_name, model=model_name, status="error"
                ).inc()
                logger.error(
                    "Model connection error",
                    extra={"race_id": race_id, "model_id": target.model_id, "error": str(conn_exc)},
                )
                emit("model.error", error=f"{type(conn_exc).__name__}: {conn_exc}")
                break

            except TimeoutError:
                timeout_name = "Total completion timeout" if first_token_received else "First token timeout"
                timeout_val = settings.model_timeout_s if first_token_received else settings.first_token_timeout_s
                MODEL_REQUESTS_TOTAL.labels(
                    provider=provider_name, model=model_name, status="timeout"
                ).inc()
                logger.warning(
                    "Model timeout exceeded",
                    extra={"race_id": race_id, "model_id": target.model_id, "timeout_type": timeout_name},
                )
                emit("model.timeout", error=f"{timeout_name} exceeded ({timeout_val}s)")
                break

            except asyncio.CancelledError:
                MODEL_REQUESTS_TOTAL.labels(
                    provider=provider_name, model=model_name, status="cancelled"
                ).inc()
                logger.info(
                    "Model cancelled",
                    extra={"race_id": race_id, "model_id": target.model_id},
                )
                emit("model.cancelled")
                raise

            except Exception as exc:
                MODEL_REQUESTS_TOTAL.labels(
                    provider=provider_name, model=model_name, status="error"
                ).inc()
                logger.exception(
                    "Model unexpected error",
                    extra={"race_id": race_id, "model_id": target.model_id, "error": str(exc)},
                )
                emit("model.error", error=f"{type(exc).__name__}: {exc}")
                break


async def run_race(
    race_id: str,
    targets: list[RaceTarget],
    template: ModelRequest,
) -> AsyncIterator[RaceEvent]:
    """Coordinates concurrent model execution, stamping sequence numbers centrally."""
    RACES_TOTAL.labels(status="started").inc()
    logger.info(
        "Race started",
        extra={
            "race_id": race_id,
            "contenders_count": len(targets),
            "target_models": [t.model_id for t in targets],
        },
    )

    queue: asyncio.Queue[RaceEvent | None] = asyncio.Queue()
    tasks: list[asyncio.Task[None]] = []

    for target in targets:
        task = asyncio.create_task(_run_model(target, template, race_id, queue))
        task.add_done_callback(lambda _t: queue.put_nowait(None))
        tasks.append(task)

    active_race = ActiveRace(tasks=tasks)
    RACES[race_id] = active_race

    # Rule 7: Sequence is stamped in exactly one place (run_race)
    counter = itertools.count()

    def stamp(event: RaceEvent) -> RaceEvent:
        event.sequence = next(counter)
        return event

    yield stamp(RaceEvent(type="race.started", race_id=race_id))

    remaining = len(tasks)
    try:
        while remaining > 0:
            item = await queue.get()
            if item is None:
                remaining -= 1
                continue
            yield stamp(item)

        if active_race.cancelled:
            RACES_TOTAL.labels(status="cancelled").inc()
            logger.info("Race completed as cancelled", extra={"race_id": race_id})
            yield stamp(RaceEvent(type="race.cancelled", race_id=race_id))
        else:
            RACES_TOTAL.labels(status="completed").inc()
            logger.info("Race completed successfully", extra={"race_id": race_id})
            yield stamp(RaceEvent(type="race.completed", race_id=race_id))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        RACES.pop(race_id, None)