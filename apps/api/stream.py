# Takes response from ai provider and sends it to frontend as it is generated live
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.providers.base import ModelProvider
from app.providers.registry import DEFAULT_MODELS, PROVIDERS
from app.providers.types import Message, ModelRequest

router = APIRouter(prefix="/api")


async def sse_events(
    provider: ModelProvider, request: ModelRequest
) -> AsyncIterator[str]:
    async for delta in provider.stream(request):
        yield f"data: {delta.model_dump_json()}\n\n"


@router.get("/stream")
async def stream(
    prompt: str,
    provider: str = "mock",
    model: str | None = None,
) -> StreamingResponse:
    impl = PROVIDERS.get(provider)
    if impl is None:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    request = ModelRequest(
        model=model or DEFAULT_MODELS[provider],
        messages=[Message(role="user", content=prompt)],
    )
    return StreamingResponse(
        sse_events(impl, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )