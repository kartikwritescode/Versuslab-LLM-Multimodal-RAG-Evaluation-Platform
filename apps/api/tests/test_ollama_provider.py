import json
from typing import Any

import httpx
import pytest

from app.providers.ollama import OllamaProvider
from app.providers.types import Message, ModelRequest


@pytest.mark.asyncio
async def test_ollama_provider_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = [
        # Empty thinking / preamble chunk (should be skipped)
        json.dumps({"message": {"role": "assistant", "content": ""}, "done": False}),
        # Actual content chunk
        json.dumps({"message": {"role": "assistant", "content": "The sky is blue."}, "done": False}),
        # Completion chunk with done_reason and usage
        json.dumps({
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 6,
            "eval_count": 4,
        }),
    ]
    raw_content = ("\n".join(lines) + "\n").encode("utf-8")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        payload = json.loads(request.read())
        assert payload.get("think") is False
        return httpx.Response(status_code=200, content=raw_content)

    transport = httpx.MockTransport(mock_handler)

    # Monkeypatch AsyncClient to use our fake MockTransport so no real network requests are made
    orig_async_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = OllamaProvider(base_url="http://fake-ollama:11434", think=False)
    request = ModelRequest(
        model="qwen3:4b",
        messages=[Message(role="user", content="why is the sky blue?")],
    )

    deltas = [d async for d in provider.stream(request)]

    # 1 text delta + 1 completion delta (empty chunk was skipped)
    assert len(deltas) == 2

    text_delta = deltas[0]
    assert text_delta.sequence == 0
    assert text_delta.text == "The sky is blue."

    final_delta = deltas[1]
    assert final_delta.sequence == 1
    assert final_delta.finish_reason == "stop"
    assert final_delta.usage is not None
    assert final_delta.usage.input_tokens == 6
    assert final_delta.usage.output_tokens == 4


@pytest.mark.asyncio
async def test_ollama_provider_thinking_chunk_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that thinking chunks from reasoning models are captured as deltas rather than dropped."""
    lines = [
        # Thinking chunk with content=""
        json.dumps({"message": {"role": "assistant", "content": "", "thinking": "Let me think..."}, "done": False}),
        # Regular content chunk
        json.dumps({"message": {"role": "assistant", "content": "42"}, "done": False}),
        # Done
        json.dumps({
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 5,
            "eval_count": 2,
        }),
    ]
    raw_content = ("\n".join(lines) + "\n").encode("utf-8")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(status_code=200, content=raw_content)

    transport = httpx.MockTransport(mock_handler)
    orig_async_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = OllamaProvider(base_url="http://fake-ollama:11434", think=True)
    request = ModelRequest(
        model="qwen3:8b",
        messages=[Message(role="user", content="what is 6 * 7?")],
    )

    deltas = [d async for d in provider.stream(request)]
    assert len(deltas) == 3

    assert deltas[0].text == "Let me think..."
    assert deltas[1].text == "42"
    assert deltas[2].finish_reason == "stop"


@pytest.mark.asyncio
async def test_ollama_provider_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, content=b"Internal Server Error")

    transport = httpx.MockTransport(mock_handler)
    orig_async_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = OllamaProvider(base_url="http://fake-ollama:11434")
    request = ModelRequest(
        model="qwen3:4b",
        messages=[Message(role="user", content="trigger 500")],
    )

    with pytest.raises(RuntimeError, match=r"Ollama error \(500\): Internal Server Error"):
        async for _ in provider.stream(request):
            pass


@pytest.mark.asyncio
async def test_ollama_provider_model_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404, json={"error": "model 'qwen3:missing' not found, try pulling it first"})

    transport = httpx.MockTransport(mock_handler)
    orig_async_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    provider = OllamaProvider(base_url="http://fake-ollama:11434")
    request = ModelRequest(
        model="qwen3:missing",
        messages=[Message(role="user", content="hello")],
    )

    with pytest.raises(RuntimeError, match=r"model 'qwen3:missing' not found"):
        async for _ in provider.stream(request):
            pass


@pytest.mark.asyncio
async def test_ollama_embedding_provider_mock_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies OllamaEmbeddingProvider using fake HTTP transport."""
    from app.providers.embeddings import OllamaEmbeddingProvider

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        data = json.loads(request.read())
        assert data["model"] == "nomic-embed-text"
        inputs = data["input"]
        # Return fake 768-dim embeddings for each input
        fake_vectors = [[0.1] * 768 for _ in inputs]
        return httpx.Response(status_code=200, json={"embeddings": fake_vectors})

    transport = httpx.MockTransport(mock_handler)
    orig_async_client = httpx.AsyncClient

    def fake_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return orig_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    embedder = OllamaEmbeddingProvider(base_url="http://fake-ollama:11434", model="nomic-embed-text")
    vectors = await embedder.embed_documents(["document chunk 1", "document chunk 2"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 768

    query_vec = await embedder.embed_query("test search query")
    assert len(query_vec) == 768
