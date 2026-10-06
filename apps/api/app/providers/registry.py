from app.core.config import settings
from app.providers.anthropic import AnthropicProvider
from app.providers.base import ModelProvider
from app.providers.deepseek import DeepSeekProvider
from app.providers.gemini import GeminiProvider
from app.providers.grok import GrokProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai import OpenAIProvider

# Central provider registry decouples endpoint routing from specific provider instantiations
PROVIDERS: dict[str, ModelProvider] = {
    "mock": MockProvider(),
    "mock-slow": MockProvider(first_token_delay=1.0, tokens_per_second=4.0),
    "mock-broken": MockProvider(fail_after_tokens=3),
    "mock-stuck": MockProvider(first_token_delay=999.0),
    "ollama": OllamaProvider(settings.ollama_base_url, think=settings.ollama_think),
    "openai": OpenAIProvider(base_url=settings.openai_base_url, api_key=settings.openai_api_key),
    "anthropic": AnthropicProvider(base_url=settings.anthropic_base_url, api_key=settings.anthropic_api_key),
    "gemini": GeminiProvider(base_url=settings.gemini_base_url, api_key=settings.gemini_api_key),
    "grok": GrokProvider(base_url=settings.xai_base_url, api_key=settings.xai_api_key),
    "deepseek": DeepSeekProvider(base_url=settings.deepseek_base_url, api_key=settings.deepseek_api_key),
}

# Current smallest/cheapest general-purpose chat model IDs verified from official docs
DEFAULT_MODELS: dict[str, str] = {
    "mock": "mock-1",
    "mock-slow": "mock-slow-1",
    "mock-broken": "mock-broken-1",
    "mock-stuck": "mock-stuck-1",
    "ollama": settings.ollama_chat_model,
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "gemini": "gemini-3.5-flash",
    "grok": "grok-2-1212",
    "deepseek": "deepseek-chat",
}
