import json
from typing import Any

import httpx
import pytest

from app.providers.anthropic import AnthropicProvider
from app.providers.deepseek import DeepSeekProvider
from app.providers.gemini import GeminiProvider
from app.providers.grok import GrokProvider
from app.providers.openai import OpenAIProvider
from app.providers.types import Message, ModelRequest


@pytest.mark.asyncio
async def test_providers_raise_runtime_error_when_no_api_key() -> None:
    req = ModelRequest(model="test", messages=[Message(role="user", content="hi")])

    # OpenAI missing key
    openai_prov = OpenAIProvider(base_url="http://test", api_key=None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        async for _ in openai_prov.stream(req):
            pass

    # Anthropic missing key
    anthropic_prov = AnthropicProvider(base_url="http://test", api_key=None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        async for _ in anthropic_prov.stream(req):
            pass

    # Gemini missing key
    gemini_prov = GeminiProvider(base_url="http://test", api_key=None)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        async for _ in gemini_prov.stream(req):
            pass

    # Grok missing key
    grok_prov = GrokProvider(base_url="http://test", api_key=None)
    with pytest.raises(RuntimeError, match="XAI_API_KEY"):
        async for _ in grok_prov.stream(req):
            pass

    # DeepSeek missing key
    deepseek_prov = DeepSeekProvider(base_url="http://test", api_key=None)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        async for _ in deepseek_prov.stream(req):
            pass


@pytest.mark.asyncio
async def test_openai_provider_streaming_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [
        json.dumps({"choices": [{"delta": {"content": "Hello "}, "finish_reason": None}], "usage": None}),
        json.dumps({"choices": [{"delta": {"content": "world!"}, "finish_reason": "stop"}], "usage": None}),
        json.dumps({"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}}),
    ]
    sse_body = "".join(f"data: {c}\n\n" for c in chunks) + "data: [DONE]\n\n"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert "Bearer test-openai-key" in request.headers.get("Authorization", "")
        body = json.loads(request.read())
        assert body["stream_options"] == {"include_usage": True}
        return httpx.Response(status_code=200, content=sse_body.encode("utf-8"))

    transport = httpx.MockTransport(mock_handler)
    orig_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = OpenAIProvider(base_url="https://api.openai.com/v1", api_key="test-openai-key")
    req = ModelRequest(model="gpt-4o-mini", messages=[Message(role="user", content="hello")])

    deltas = [d async for d in provider.stream(req)]
    assert len(deltas) == 3
    assert deltas[0].text == "Hello "
    assert deltas[1].text == "world!"
    assert deltas[2].finish_reason == "stop"
    assert deltas[2].usage is not None
    assert deltas[2].usage.input_tokens == 7
    assert deltas[2].usage.output_tokens == 2


@pytest.mark.asyncio
async def test_anthropic_provider_streaming_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    sse_lines = [
        'data: {"type": "message_start", "message": {"usage": {"input_tokens": 15}}}',
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Claude here."}}',
        'data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 5}}',
        'data: {"type": "message_stop"}',
    ]
    raw_content = ("\n\n".join(sse_lines) + "\n\n").encode("utf-8")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        assert request.headers.get("x-api-key") == "test-anthropic-key"
        assert request.headers.get("anthropic-version") == "2023-06-01"
        body = json.loads(request.read())
        assert body["max_tokens"] == 4096
        return httpx.Response(status_code=200, content=raw_content)

    transport = httpx.MockTransport(mock_handler)
    orig_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = AnthropicProvider(base_url="https://api.anthropic.com", api_key="test-anthropic-key")
    req = ModelRequest(
        model="claude-3-5-haiku-20241022",
        messages=[
            Message(role="system", content="Be helpful"),
            Message(role="user", content="hello"),
        ],
    )

    deltas = [d async for d in provider.stream(req)]
    assert len(deltas) == 2
    assert deltas[0].text == "Claude here."
    assert deltas[1].finish_reason == "end_turn"
    assert deltas[1].usage is not None
    assert deltas[1].usage.input_tokens == 15
    assert deltas[1].usage.output_tokens == 5


@pytest.mark.asyncio
async def test_gemini_provider_streaming_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    chunk_data = json.dumps({
        "candidates": [{
            "content": {"parts": [{"text": "Gemini response."}], "role": "model"},
            "finishReason": "STOP",
        }],
        "usageMetadata": {
            "promptTokenCount": 11,
            "candidatesTokenCount": 4,
            "totalTokenCount": 15,
        },
    })
    sse_body = f"data: {chunk_data}\n\n".encode()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert "streamGenerateContent" in request.url.path
        assert request.url.query == b"alt=sse"
        assert request.headers.get("x-goog-api-key") == "test-gemini-key"
        return httpx.Response(status_code=200, content=sse_body)

    transport = httpx.MockTransport(mock_handler)
    orig_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = GeminiProvider(base_url="https://generativelanguage.googleapis.com", api_key="test-gemini-key")
    req = ModelRequest(model="gemini-2.5-flash", messages=[Message(role="user", content="hello")])

    deltas = [d async for d in provider.stream(req)]
    assert len(deltas) == 2
    assert deltas[0].text == "Gemini response."
    assert deltas[1].finish_reason == "stop"
    assert deltas[1].usage is not None
    assert deltas[1].usage.input_tokens == 11
    assert deltas[1].usage.output_tokens == 4


@pytest.mark.asyncio
async def test_grok_provider_delegation() -> None:
    grok = GrokProvider(base_url="https://api.x.ai/v1", api_key="test-grok-key")
    assert grok._delegate._base_url == "https://api.x.ai/v1"
    assert grok._delegate._api_key == "test-grok-key"
    assert grok._delegate._provider_name == "grok"


@pytest.mark.asyncio
async def test_grok_provider_streaming_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies GrokProvider streaming with fake HTTP transport."""
    chunks = [
        json.dumps({"choices": [{"delta": {"content": "Grok "}, "finish_reason": None}], "usage": None}),
        json.dumps({"choices": [{"delta": {"content": "speaks!"}, "finish_reason": "stop"}], "usage": None}),
        json.dumps({"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}),
    ]
    sse_body = "".join(f"data: {c}\n\n" for c in chunks) + "data: [DONE]\n\n"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert "Bearer test-grok-key" in request.headers.get("Authorization", "")
        return httpx.Response(status_code=200, content=sse_body.encode("utf-8"))

    transport = httpx.MockTransport(mock_handler)
    orig_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = GrokProvider(base_url="https://api.x.ai/v1", api_key="test-grok-key")
    req = ModelRequest(model="grok-2-1212", messages=[Message(role="user", content="hello grok")])

    deltas = [d async for d in provider.stream(req)]
    assert len(deltas) == 3
    assert deltas[0].text == "Grok "
    assert deltas[1].text == "speaks!"
    assert deltas[2].finish_reason == "stop"
    assert deltas[2].usage is not None


@pytest.mark.asyncio
async def test_deepseek_provider_delegation() -> None:
    ds = DeepSeekProvider(base_url="https://api.deepseek.com", api_key="test-deepseek-key")
    assert ds._delegate._base_url == "https://api.deepseek.com"
    assert ds._delegate._api_key == "test-deepseek-key"
    assert ds._delegate._provider_name == "deepseek"


@pytest.mark.asyncio
async def test_deepseek_provider_streaming_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies DeepSeekProvider streaming with fake HTTP transport."""
    chunks = [
        json.dumps({"choices": [{"delta": {"content": "DeepSeek "}, "finish_reason": None}], "usage": None}),
        json.dumps({"choices": [{"delta": {"content": "thinks!"}, "finish_reason": "stop"}], "usage": None}),
        json.dumps({"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}}),
    ]
    sse_body = "".join(f"data: {c}\n\n" for c in chunks) + "data: [DONE]\n\n"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions"
        assert "Bearer test-deepseek-key" in request.headers.get("Authorization", "")
        return httpx.Response(status_code=200, content=sse_body.encode("utf-8"))

    transport = httpx.MockTransport(mock_handler)
    orig_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = DeepSeekProvider(base_url="https://api.deepseek.com", api_key="test-deepseek-key")
    req = ModelRequest(model="deepseek-chat", messages=[Message(role="user", content="hello deepseek")])

    deltas = [d async for d in provider.stream(req)]
    assert len(deltas) == 3
    assert deltas[0].text == "DeepSeek "
    assert deltas[1].text == "thinks!"
    assert deltas[2].finish_reason == "stop"
    assert deltas[2].usage is not None
    assert deltas[2].usage.input_tokens == 10
    assert deltas[2].usage.output_tokens == 4


@pytest.mark.asyncio
async def test_gemini_provider_maps_gemini_3_5_flash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that gemini-3.5-flash requests map to the active gemini-3-flash-preview endpoint."""
    chunk_data = json.dumps({
        "candidates": [{
            "content": {"parts": [{"text": "Gemini 3.5 Flash response."}], "role": "model"},
            "finishReason": "STOP",
        }],
        "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 5},
    })
    sse_body = f"data: {chunk_data}\n\n".encode()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert "models/gemini-3-flash-preview:streamGenerateContent" in request.url.path
        return httpx.Response(status_code=200, content=sse_body)

    transport = httpx.MockTransport(mock_handler)
    orig_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = GeminiProvider(base_url="https://generativelanguage.googleapis.com", api_key="test-gemini-key")
    req = ModelRequest(model="gemini-3.5-flash", messages=[Message(role="user", content="hello")])

    deltas = [d async for d in provider.stream(req)]
    assert len(deltas) == 2
    assert deltas[0].model_id == "gemini-3.5-flash"
    assert deltas[0].text == "Gemini 3.5 Flash response."
    assert deltas[1].model_id == "gemini-3.5-flash"
    assert deltas[1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_gemini_provider_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that GeminiProvider extracts JSON error messages from non-200 responses."""
    err_body = json.dumps({
        "error": {
            "code": 400,
            "message": "API key not valid. Please pass a valid API key.",
            "status": "INVALID_ARGUMENT",
        }
    }).encode()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=400, content=err_body)

    transport = httpx.MockTransport(mock_handler)
    orig_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = GeminiProvider(base_url="https://generativelanguage.googleapis.com", api_key="test-gemini-key")
    req = ModelRequest(model="gemini-3.5-flash", messages=[Message(role="user", content="hello")])

    with pytest.raises(RuntimeError, match=r"API key not valid"):
        async for _ in provider.stream(req):
            pass


@pytest.mark.asyncio
async def test_deepseek_provider_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that DeepSeekProvider extracts JSON error messages (e.g. Insufficient Balance)."""
    err_body = json.dumps({
        "error": {
            "message": "Insufficient Balance",
            "type": "deepseek_error",
            "code": "invalid_request_error",
        }
    }).encode()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=402, content=err_body)

    transport = httpx.MockTransport(mock_handler)
    orig_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = DeepSeekProvider(base_url="https://api.deepseek.com", api_key="test-deepseek-key")
    req = ModelRequest(model="deepseek-chat", messages=[Message(role="user", content="hello")])

    with pytest.raises(RuntimeError, match=r"Insufficient Balance"):
        async for _ in provider.stream(req):
            pass
