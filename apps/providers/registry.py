# A registry is just a central place where we keep track of available things
from app.core.config import settings
from app.providers.base import ModelProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider

PROVIDERS: dict[str, ModelProvider] = {
    "mock": MockProvider(),
    "mock-slow": MockProvider(first_token_delay=1.2, tokens_per_second=4.0),
    "mock-broken": MockProvider(fail_after_tokens=3),
    "ollama": OllamaProvider(settings.ollama_base_url),
}

DEFAULT_MODELS: dict[str, str] = {
    "mock": "mock-1",
    "mock-slow": "mock-slow-1",
    "mock-broken": "mock-broken-1",
    "ollama": settings.ollama_chat_model,
}