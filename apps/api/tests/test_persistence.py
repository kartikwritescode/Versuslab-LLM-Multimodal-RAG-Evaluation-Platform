import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import ModelRun, Race
from app.db.tracker import RacePersistenceTracker
from app.main import app
from app.providers.types import Usage
from app.race.events import RaceEvent


@pytest.mark.asyncio
async def test_list_races_endpoint():
    """Tests GET /api/races endpoint returning paginated races."""
    fake_items = [
        {
            "id": "race-1",
            "prompt": "Test prompt",
            "temperature": 0.7,
            "max_tokens": 100,
            "status": "completed",
            "model_count": 2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    ]

    with patch("app.api.race.list_races", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = (fake_items, 1)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/races?limit=10&offset=0")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            assert data["items"][0]["id"] == "race-1"
            assert data["items"][0]["model_count"] == 2


@pytest.mark.asyncio
async def test_get_race_endpoint_found():
    """Tests GET /api/races/{race_id} returning a race with its model_runs."""
    fake_race = Race(
        id="race-abc",
        prompt="Explain async",
        temperature=0.7,
        max_tokens=None,
        status="completed",
        created_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    fake_run = ModelRun(
        id="run-1",
        race_id="race-abc",
        model_id="mock:mock-1",
        status="done",
        ttft_ms=50,
        latency_ms=250,
        input_tokens=10,
        output_tokens=25,
        finish_reason="stop",
        error_message=None,
        response_text="Async explanation",
    )
    fake_race.model_runs = [fake_run]

    with patch("app.api.race.get_race_detail", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = fake_race

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/races/race-abc")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == "race-abc"
            assert data["status"] == "completed"
            assert len(data["model_runs"]) == 1
            assert data["model_runs"][0]["model_id"] == "mock:mock-1"
            assert data["model_runs"][0]["ttft_ms"] == 50
            assert data["model_runs"][0]["response_text"] == "Async explanation"


@pytest.mark.asyncio
async def test_get_race_endpoint_not_found():
    """Tests GET /api/races/{race_id} returning 404 when race does not exist."""
    with patch("app.api.race.get_race_detail", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/races/nonexistent-race")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Race not found"


@pytest.mark.asyncio
async def test_race_persistence_tracker_lifecycle():
    """Tests that RacePersistenceTracker properly computes metrics and updates DB."""
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = mock_session
    mock_factory.return_value.__aexit__.return_value = None

    race_id = "test-race-id"
    tracker = RacePersistenceTracker(race_id=race_id, session_factory=mock_factory)

    base_time_ns = time.time_ns()

    with (
        patch("app.db.tracker.mark_model_started", new_callable=AsyncMock) as mock_started,
        patch("app.db.tracker.mark_model_finished", new_callable=AsyncMock) as mock_finished,
        patch("app.db.tracker.mark_race_finished", new_callable=AsyncMock) as mock_race_finished,
    ):
        # 1. model.started event
        start_event = RaceEvent(
            type="model.started",
            race_id=race_id,
            model_id="mock:mock-1",
            timestamp_ns=base_time_ns,
        )
        await tracker.record_event(start_event)
        mock_started.assert_called_once_with(mock_session, race_id, "mock:mock-1")

        # 2. model.delta events (accumulating text, zero DB writes)
        delta_1 = RaceEvent(
            type="model.delta",
            race_id=race_id,
            model_id="mock:mock-1",
            text="Hello ",
            timestamp_ns=base_time_ns + 100_000_000,  # 100ms later
        )
        await tracker.record_event(delta_1)

        delta_2 = RaceEvent(
            type="model.delta",
            race_id=race_id,
            model_id="mock:mock-1",
            text="world!",
            timestamp_ns=base_time_ns + 250_000_000,
        )
        await tracker.record_event(delta_2)

        # Ensure no additional DB write occurred during deltas
        assert mock_finished.call_count == 0

        # 3. model.completed event
        complete_event = RaceEvent(
            type="model.completed",
            race_id=race_id,
            model_id="mock:mock-1",
            timestamp_ns=base_time_ns + 300_000_000,  # 300ms total latency
            finish_reason="stop",
            usage=Usage(input_tokens=5, output_tokens=2),
        )
        await tracker.record_event(complete_event)

        mock_finished.assert_called_once()
        _, kwargs = mock_finished.call_args
        assert kwargs["race_id"] == race_id
        assert kwargs["model_id"] == "mock:mock-1"
        assert kwargs["status"] == "done"
        assert kwargs["ttft_ms"] == 100  # 100ms
        assert kwargs["latency_ms"] == 300  # 300ms
        assert kwargs["input_tokens"] == 5
        assert kwargs["output_tokens"] == 2
        assert kwargs["response_text"] == "Hello world!"

        # 4. race.completed event
        race_done_event = RaceEvent(
            type="race.completed",
            race_id=race_id,
            timestamp_ns=base_time_ns + 350_000_000,
        )
        await tracker.record_event(race_done_event)
        mock_race_finished.assert_called_once_with(mock_session, race_id, "completed")


@pytest.mark.asyncio
async def test_race_persistence_tracker_error_isolation():
    """Tests that DB failures inside tracker log warning but do not raise."""
    mock_factory = MagicMock()
    mock_factory.side_effect = RuntimeError("DB connection dropped")

    tracker = RacePersistenceTracker(race_id="r1", session_factory=mock_factory)

    event = RaceEvent(
        type="model.started",
        race_id="r1",
        model_id="mock:mock-1",
    )
    # Should not raise exception
    await tracker.record_event(event)
