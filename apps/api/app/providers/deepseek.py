from collections.abc import AsyncIterator

from app.providers.openai import OpenAIProvider
from app.providers.types import ModelDelta, ModelRequest


class DeepSeekProvider:
    """Provider adapter for DeepSeek models, delegating to the OpenAI-compatible engine.

    DeepSeek's API (https://api.deepseek.com) follows the standard OpenAI Chat
    Completions protocol (/chat/completions) with SSE streaming.
    """

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self._delegate = OpenAIProvider(base_url=base_url, api_key=api_key, provider_name="deepseek")

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]:
        async for delta in self._delegate.stream(request):
            yield delta
