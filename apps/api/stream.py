from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.providers.base import ModelProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider
from app.providers.types import Message, ModelRequest

router = APIRouter(prefix="/api")

PROVIDERS: dict[str, ModelProvider] = {
    "mock": MockProvider(),
    "ollama": OllamaProvider(settings.ollama_base_url),
}

DEFAULT_MODELS: dict[str, str] = {
    "mock": "mock-1",
    "ollama": settings.ollama_chat_model,
}


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