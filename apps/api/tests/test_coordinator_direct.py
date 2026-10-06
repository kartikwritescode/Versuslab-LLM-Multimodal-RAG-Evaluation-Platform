import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.core.config import settings
from app.providers.types import Message, ModelDelta, ModelRequest, Usage
from app.race.coordinator import RaceTarget, cancel_race, run_race


class ScriptedProvider:
    """Mock provider with explicit scripted behavior for coordinator unit testing."""

    def __init__(
        self,
        deltas: list[ModelDelta] | None = None,
        delay_before_first_token: float = 0.0,
        delay_between_tokens: float = 0.0,
        raise_before_first_token: Exception | None = None,
        raise_after_first_token: Exception | None = None,
    ) -> None:
        self.deltas = deltas or []
        self.delay_before_first_token = delay_before_first_token
        self.delay_between_tokens = delay_between_tokens
        self.raise_before_first_token = raise_before_first_token
        self.raise_after_first_token = raise_after_first_token

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]:
        if self.delay_before_first_token > 0:
            await asyncio.sleep(self.delay_before_first_token)

        if self.raise_before_first_token:
            raise self.raise_before_first_token

        for i, delta in enumerate(self.deltas):
            if i > 0 and self.delay_between_tokens > 0:
                await asyncio.sleep(self.delay_between_tokens)

            if i > 0 and self.raise_after_first_token:
                raise self.raise_after_first_token

            yield delta


@pytest.mark.asyncio
async def test_coordinator_normal_completion() -> None:
    """Directly tests run_race generator for normal multi-model completion."""
    deltas1 = [
        ModelDelta(model_id="m1", sequence=0, text="Hello "),
        ModelDelta(model_id="m1", sequence=1, text="world!"),
        ModelDelta(model_id="m1", sequence=2, finish_reason="stop", usage=Usage(input_tokens=5, output_tokens=2)),
    ]
    deltas2 = [
        ModelDelta(model_id="m2", sequence=0, text="Foo "),
        ModelDelta(model_id="m2", sequence=1, text="bar!"),
        ModelDelta(model_id="m2", sequence=2, finish_reason="stop", usage=Usage(input_tokens=4, output_tokens=2)),
    ]

    t1 = RaceTarget(model_id="provider1:m1", provider=ScriptedProvider(deltas1), model="m1")
    t2 = RaceTarget(model_id="provider2:m2", provider=ScriptedProvider(deltas2), model="m2")
    template = ModelRequest(model="", messages=[Message(role="user", content="ping")])

    events = [e async for e in run_race("direct-race-1", [t1, t2], template)]

    assert events[0].type == "race.started"
    assert events[-1].type == "race.completed"

    event_types = [e.type for e in events]
    assert event_types.count("model.started") == 2
    assert event_types.count("model.completed") == 2

    # Verify monotonic sequencing across all interleaved events
    sequences = [e.sequence for e in events]
    assert sequences == list(range(len(events)))


@pytest.mark.asyncio
async def test_coordinator_first_token_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Directly tests run_race first-token timeout path."""
    monkeypatch.setattr(settings, "first_token_timeout_s", 0.1)

    stuck_provider = ScriptedProvider(delay_before_first_token=5.0)
    target = RaceTarget(model_id="mock:stuck", provider=stuck_provider, model="stuck")
    template = ModelRequest(model="", messages=[Message(role="user", content="ping")])

    events = [e async for e in run_race("timeout-race", [target], template)]
    event_types = [e.type for e in events]

    assert "model.timeout" in event_types
    timeout_event = next(e for e in events if e.type == "model.timeout")
    assert "First token timeout" in (timeout_event.error or "")
    assert events[-1].type == "race.completed"


@pytest.mark.asyncio
async def test_coordinator_total_model_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Directly tests run_race model_timeout_s path after first token is received."""
    monkeypatch.setattr(settings, "first_token_timeout_s", 1.0)
    monkeypatch.setattr(settings, "model_timeout_s", 0.1)

    deltas = [
        ModelDelta(model_id="m1", sequence=0, text="First token ok"),
        ModelDelta(model_id="m1", sequence=1, text="Second token"),
    ]
    # Emits first token quickly, then hangs before second token
    hanging_provider = ScriptedProvider(deltas=deltas, delay_between_tokens=5.0)
    target = RaceTarget(model_id="mock:hang", provider=hanging_provider, model="hang")
    template = ModelRequest(model="", messages=[Message(role="user", content="ping")])

    events = [e async for e in run_race("total-timeout-race", [target], template)]
    event_types = [e.type for e in events]

    assert "model.delta" in event_types
    assert "model.timeout" in event_types
    timeout_event = next(e for e in events if e.type == "model.timeout")
    assert "Total completion timeout" in (timeout_event.error or "")
    assert events[-1].type == "race.completed"


@pytest.mark.asyncio
async def test_coordinator_error_isolation() -> None:
    """Directly tests that an exception raised by a provider yields model.error and does not crash the race."""
    failing_provider = ScriptedProvider(raise_before_first_token=RuntimeError("Simulated provider crash"))
    target = RaceTarget(model_id="mock:failing", provider=failing_provider, model="failing")
    template = ModelRequest(model="", messages=[Message(role="user", content="ping")])

    events = [e async for e in run_race("error-race", [target], template)]
    event_types = [e.type for e in events]

    assert "model.error" in event_types
    error_event = next(e for e in events if e.type == "model.error")
    assert "Simulated provider crash" in (error_event.error or "")
    assert events[-1].type == "race.completed"


@pytest.mark.asyncio
async def test_coordinator_cancellation_path() -> None:
    """Directly tests coordinator handling of cancel_race."""
    deltas = [
        ModelDelta(model_id="m1", sequence=0, text="slow 1"),
        ModelDelta(model_id="m1", sequence=1, text="slow 2"),
    ]
    slow_provider = ScriptedProvider(deltas=deltas, delay_before_first_token=0.05, delay_between_tokens=1.0)
    target = RaceTarget(model_id="mock:slow", provider=slow_provider, model="slow")
    template = ModelRequest(model="", messages=[Message(role="user", content="ping")])

    race_id = "direct-cancel-race"

    async def consume_and_cancel() -> list[Any]:
        collected = []
        async for event in run_race(race_id, [target], template):
            collected.append(event)
            if event.type == "model.started":
                # Trigger cancellation
                cancel_race(race_id)
        return collected

    events = await consume_and_cancel()
    event_types = [e.type for e in events]

    assert "model.cancelled" in event_types
    assert events[-1].type == "race.cancelled"
