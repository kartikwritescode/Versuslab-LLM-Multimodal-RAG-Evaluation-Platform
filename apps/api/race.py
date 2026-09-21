# takes request and: 
# Check that the requested models are valid.
# Convert those model names into RaceTarget objects.
# Create a unique ID for this race.
# Start the race using run_race().
# Stream the race events back to the frontend.
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.providers.registry import DEFAULT_MODELS, PROVIDERS
from app.providers.types import Message
from app.race.coordinator import RaceTarget, run_race

router = APIRouter(prefix="/api")

MAX_CONTENDERS = 8


def parse_target(spec: str) -> RaceTarget:
    provider_name, _, model = spec.partition(":")
    provider = PROVIDERS.get(provider_name)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider_name}")

    model = model or DEFAULT_MODELS[provider_name]
    return RaceTarget(model_id=f"{provider_name}:{model}", provider=provider, model=model)


async def sse_race(
    race_id: str, targets: list[RaceTarget], messages: list[Message]
) -> AsyncIterator[str]:
    async for event in run_race(race_id, targets, messages):
        yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"


@router.get("/race")
async def race(
    prompt: str,
    models: list[str] = Query(...),
) -> StreamingResponse:
    if not 1 <= len(models) <= MAX_CONTENDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Provide between 1 and {MAX_CONTENDERS} models",
        )

    targets = [parse_target(spec) for spec in models]

    ids = [t.model_id for t in targets]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail="Duplicate models in race")

    race_id = uuid.uuid4().hex
    messages = [Message(role="user", content=prompt)]

    return StreamingResponse(
        sse_race(race_id, targets, messages),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )