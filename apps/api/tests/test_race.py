import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_race_validation_errors() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Unknown provider returns 400
        resp = await client.post(
            "/api/races",
            json={"prompt": "hello", "models": ["unknown_provider:model1"]},
        )
        assert resp.status_code == 400
        assert "Unknown provider" in resp.json()["detail"]

        # Duplicate resulting model_ids return 400
        resp = await client.post(
            "/api/races",
            json={"prompt": "hello", "models": ["mock:m1", "mock:m1"]},
        )
        assert resp.status_code == 400
        assert "Duplicate models" in resp.json()["detail"]

        # Duplicate via default model fallback returns 400
        resp = await client.post(
            "/api/races",
            json={"prompt": "hello", "models": ["mock", "mock:mock-1"]},
        )
        assert resp.status_code == 400
        assert "Duplicate models" in resp.json()["detail"]

        # Empty prompt or models list fails Pydantic validation (422)
        resp = await client.post(
            "/api/races",
            json={"prompt": "", "models": ["mock:m1"]},
        )
        assert resp.status_code == 422

        resp = await client.post(
            "/api/races",
            json={"prompt": "hello", "models": []},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_race_happy_path_mock() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/races",
            json={"prompt": "ping pong", "models": ["mock:m1", "mock:m2"]},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert response.headers.get("cache-control") == "no-cache"
        assert response.headers.get("x-accel-buffering") == "no"

        # Parse SSE events
        lines = response.text.split("\n")
        data_lines = [line.removeprefix("data: ").strip() for line in lines if line.startswith("data: ")]
        events = [json.loads(line) for line in data_lines]

        assert len(events) > 0
        assert events[0]["type"] == "race.started"
        assert events[-1]["type"] == "race.completed"

        # Verify centralized strictly increasing monotonic sequence numbers (0, 1, 2, ...)
        sequences = [e["sequence"] for e in events]
        assert sequences == list(range(len(events)))

        # Verify model completion events contain usage and finish_reason
        completions = [e for e in events if e["type"] == "model.completed"]
        assert len(completions) == 2
        for comp in completions:
            assert comp["finish_reason"] == "stop"
            assert comp["usage"]["input_tokens"] == 2


@pytest.mark.asyncio
async def test_race_mixed_contenders_failure_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    # Use 0.6s first-token deadline: normal mock emits at 0.4s, mock-stuck (999s) times out at 0.6s
    monkeypatch.setattr(settings, "first_token_timeout_s", 0.6)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/races",
            json={
                "prompt": "alpha beta gamma delta",
                "models": ["mock:fast", "mock-broken", "mock-stuck"],
            },
        )
        assert response.status_code == 200

        lines = response.text.split("\n")
        events = [json.loads(line.removeprefix("data: ").strip()) for line in lines if line.startswith("data: ")]

        event_types = [e["type"] for e in events]
        assert "race.started" in event_types
        assert "model.started" in event_types
        assert "model.delta" in event_types

        # mock:fast should complete successfully
        completed_models = [e["model_id"] for e in events if e["type"] == "model.completed"]
        assert "mock:fast" in completed_models

        # mock-broken should emit model.error after 3 tokens without crashing other models
        error_events = [e for e in events if e["type"] == "model.error"]
        assert len(error_events) == 1
        assert error_events[0]["model_id"] == "mock-broken:mock-broken-1"
        assert "RuntimeError" in error_events[0]["error"]

        # mock-stuck should emit model.timeout
        timeout_events = [e for e in events if e["type"] == "model.timeout"]
        assert len(timeout_events) == 1
        assert timeout_events[0]["model_id"] == "mock-stuck:mock-stuck-1"
        assert "First token timeout exceeded" in timeout_events[0]["error"]

        # Race must end with race.completed
        assert events[-1]["type"] == "race.completed"

        # Sequence must be monotonic with no gaps
        sequences = [e["sequence"] for e in events]
        assert sequences == list(range(len(events)))


@pytest.mark.asyncio
async def test_race_midstream_cancellation_and_404() -> None:
    transport = ASGITransport(app=app)
    race_id = "test-cancel-race-id"

    with patch("app.api.race.create_race_record", new_callable=AsyncMock):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Start slow race in background task
            stream_task = asyncio.create_task(
                client.post(
                    "/api/races",
                    json={
                        "race_id": race_id,
                        "prompt": "one two three four five six seven eight",
                        "models": ["mock-slow:m1", "mock-slow:m2"],
                    },
                )
            )

            # Allow initial deltas to start streaming
            await asyncio.sleep(0.1)

            # Cancel the race mid-stream
            cancel_resp = await client.post(f"/api/races/{race_id}/cancel")
            assert cancel_resp.status_code == 200
            assert cancel_resp.json() == {"status": "cancelled", "race_id": race_id}

            # Await the stream response and parse events
            response = await stream_task
            assert response.status_code == 200

            lines = response.text.split("\n")
            events = [json.loads(line.removeprefix("data: ").strip()) for line in lines if line.startswith("data: ")]

            event_types = [e["type"] for e in events]
            # Should observe model.cancelled and race.cancelled
            assert "model.cancelled" in event_types
            assert events[-1]["type"] == "race.cancelled"

            # A second cancel request for the same race_id must return 404 (race deregistered)
            cancel_resp_2 = await client.post(f"/api/races/{race_id}/cancel")
            assert cancel_resp_2.status_code == 404
            assert "Race not found" in cancel_resp_2.json()["detail"]


@pytest.mark.asyncio
async def test_race_unconfigured_cloud_provider_error() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request unconfigured cloud provider alongside a mock
        response = await client.post(
            "/api/races",
            json={"prompt": "hi", "models": ["openai", "mock:m1"]},
        )
        assert response.status_code == 200

        lines = response.text.split("\n")
        events = [json.loads(line.removeprefix("data: ").strip()) for line in lines if line.startswith("data: ")]

        # OpenAI should emit a clean model.error without crashing the race
        error_events = [e for e in events if e["type"] == "model.error"]
        assert len(error_events) == 1
        assert "OPENAI_API_KEY" in error_events[0]["error"]

        # Mock model should still complete normally
        completed_events = [e for e in events if e["type"] == "model.completed"]
        assert len(completed_events) == 1
        assert completed_events[0]["model_id"] == "mock:m1"

        assert events[-1]["type"] == "race.completed"


@pytest.mark.asyncio
async def test_coordinator_connection_retry_policy() -> None:
    from collections.abc import AsyncIterator

    import httpx

    from app.providers.types import ModelDelta, ModelRequest, Usage
    from app.race.coordinator import RaceTarget, run_race

    class FlakyConnectProvider:
        def __init__(self, fail_first_times: int, fail_after_token: bool = False) -> None:
            self.calls = 0
            self.fail_first_times = fail_first_times
            self.fail_after_token = fail_after_token

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]:
            self.calls += 1
            if self.fail_after_token:
                yield ModelDelta(model_id=request.model, sequence=0, text="token1")
                raise httpx.ConnectError("Mid-stream connection drop")

            if self.calls <= self.fail_first_times:
                raise httpx.ConnectError("Transient connection failure")

            yield ModelDelta(model_id=request.model, sequence=0, text="recovered")
            yield ModelDelta(
                model_id=request.model,
                sequence=1,
                finish_reason="stop",
                usage=Usage(input_tokens=1, output_tokens=1),
            )

    # 1. Transient failure before tokens: should retry and succeed
    retry_provider = FlakyConnectProvider(fail_first_times=1)
    target1 = RaceTarget(model_id="flaky:retry", provider=retry_provider, model="retry-model")
    template = ModelRequest(model="", messages=[])

    events1 = [e async for e in run_race("retry-race", [target1], template)]
    event_types1 = [e.type for e in events1]
    assert retry_provider.calls == 2
    assert "model.completed" in event_types1
    assert "model.error" not in event_types1

    # 2. Failure after tokens streamed: should NOT retry (non-idempotent) and emit model.error
    no_retry_provider = FlakyConnectProvider(fail_first_times=0, fail_after_token=True)
    target2 = RaceTarget(model_id="flaky:no-retry", provider=no_retry_provider, model="no-retry-model")

    events2 = [e async for e in run_race("no-retry-race", [target2], template)]
    event_types2 = [e.type for e in events2]
    assert no_retry_provider.calls == 1
    assert "model.error" in event_types2
    assert "model.completed" not in event_types2
