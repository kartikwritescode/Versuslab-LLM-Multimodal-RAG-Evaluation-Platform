import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.providers.types import ModelDelta, ModelRequest, Usage


class OllamaProvider:
    """Provider adapter for local models running via Ollama's HTTP API."""

    def __init__(self, base_url: str, think: bool = False) -> None:
        self._base_url = base_url.rstrip("/")
        self._think = think

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]:
        options: dict[str, Any] = {"temperature": request.temperature}
        if request.max_tokens is not None:
            # Ollama uses 'num_predict' for maximum generation tokens
            options["num_predict"] = request.max_tokens

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": True,
            "options": options,
            "think": self._think,
        }

        # Differentiate connection timeout (fail fast if daemon is down) from read timeout (local models can think slowly)
        timeout = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
        sequence = 0

        async with (
            httpx.AsyncClient(base_url=self._base_url, timeout=timeout) as client,
            client.stream("POST", "/api/chat", json=payload) as response,
        ):
            if response.status_code >= 400:
                raw_body = await response.aread()
                err_msg = f"Ollama API returned HTTP {response.status_code}"
                try:
                    err_json = json.loads(raw_body)
                    if "error" in err_json:
                        err_msg = f"Ollama error ({response.status_code}): {err_json['error']}"
                except (json.JSONDecodeError, ValueError, TypeError):
                    text = raw_body.decode("utf-8", errors="replace").strip()
                    if text:
                        err_msg = f"Ollama error ({response.status_code}): {text[:200]}"
                raise RuntimeError(err_msg)
            async for line in response.aiter_lines():
                if not line or not line.strip():
                    continue

                chunk = json.loads(line)

                # Defensive .get() access: handle standard content as well as reasoning models with 'thinking'
                raw_msg = chunk.get("message")
                content = raw_msg.get("content", "") if isinstance(raw_msg, dict) else ""
                thinking = raw_msg.get("thinking", "") if isinstance(raw_msg, dict) else ""
                text = content or thinking

                # Skip empty chunks so pure metadata frames do not yield empty deltas
                if text:
                    yield ModelDelta(
                        model_id=request.model,
                        sequence=sequence,
                        text=text,
                    )
                    sequence += 1

                if chunk.get("done") is True:
                    yield ModelDelta(
                        model_id=request.model,
                        sequence=sequence,
                        finish_reason=str(chunk.get("done_reason") or "stop"),
                        usage=Usage(
                            input_tokens=int(chunk.get("prompt_eval_count") or 0),
                            output_tokens=int(chunk.get("eval_count") or 0),
                        ),
                    )
                    return

