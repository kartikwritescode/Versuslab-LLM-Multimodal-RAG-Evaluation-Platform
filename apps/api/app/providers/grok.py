from collections.abc import AsyncIterator

from app.providers.openai import OpenAIProvider
from app.providers.types import ModelDelta, ModelRequest

# Architecture Decision:
# According to xAI's official developer documentation (https://docs.x.ai/), the xAI API
# is fully compatible with OpenAI's Chat Completions endpoint.
# Requests to https://api.x.ai/v1/chat/completions use the identical payload shape
# (messages, stream=True, stream_options={"include_usage": True}) and SSE response format.
# Therefore, GrokProvider delegates directly to OpenAIProvider rather than duplicating
# the streaming, parsing, and usage accounting logic.


class GrokProvider:
    """Provider adapter for xAI Grok models, delegating to the OpenAI-compatible engine."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self._delegate = OpenAIProvider(base_url=base_url, api_key=api_key, provider_name="grok")

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]:
        async for delta in self._delegate.stream(request):
            yield delta
