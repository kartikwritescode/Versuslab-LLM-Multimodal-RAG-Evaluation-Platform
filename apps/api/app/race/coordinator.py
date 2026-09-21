# Runs multiple AI models simultaneously, collects their streamed responses, and sends events back as they happen.
import asyncio
import itertools
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from app.providers.base import ModelProvider
from app.providers.types import Message, ModelRequest
from app.race.events import EventType, RaceEvent


@dataclass(frozen=True)
class RaceTarget:
    model_id: str
    provider: ModelProvider
    model: str


async def _run_model(
    target: RaceTarget,
    messages: list[Message],
    race_id: str,
    queue: asyncio.Queue[RaceEvent | None],
) -> None:
    def emit(event_type: EventType, **fields: Any) -> None:
        '''Helper function that creates and puts an event into the queue.'''
        queue.put_nowait(
            RaceEvent(
                type=event_type,
                race_id=race_id,
                model_id=target.model_id,
                **fields,
            )
        )

    try:
        emit("model.started")
        request = ModelRequest(model=target.model, messages=messages)

        async for delta in target.provider.stream(request):
            if delta.text:
                emit("model.delta", text=delta.text)
            if delta.finish_reason is not None:
                emit(
                    "model.completed",
                    finish_reason=delta.finish_reason,
                    usage=delta.usage,
                )
    except Exception as exc:
        emit("model.error", error=f"{type(exc).__name__}: {exc}")
    finally:
        queue.put_nowait(None)


async def run_race(
    race_id: str,
    targets: list[RaceTarget],
    messages: list[Message],
) -> AsyncIterator[RaceEvent]:
    queue: asyncio.Queue[RaceEvent | None] = asyncio.Queue()
    counter = itertools.count()

    def stamp(event: RaceEvent) -> RaceEvent:
        event.sequence = next(counter)
        return event

    
    yield stamp(RaceEvent(type="race.started", race_id=race_id))

    tasks = [
        asyncio.create_task(_run_model(target, messages, race_id, queue))
        for target in targets
    ]
    remaining = len(tasks)

    try:
        while remaining > 0:
            item = await queue.get()
            if item is None:
                remaining -= 1
                continue
            yield stamp(item)
    finally:
        for task in tasks:
            task.cancel()

    yield stamp(RaceEvent(type="race.completed", race_id=race_id))