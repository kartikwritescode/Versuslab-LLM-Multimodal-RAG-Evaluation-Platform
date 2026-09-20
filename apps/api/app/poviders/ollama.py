import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.providers.types import ModelDelta, ModelRequest, Usage


class OllamaProvider:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]:
        options: dict[str, Any] = {"temperature": request.temperature}
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": True,
            "options": options,
        }

        timeout = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
        sequence = 0

        async with httpx.AsyncClient(base_url=self._base_url, timeout=timeout) as client:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    chunk = json.loads(line)

                    text = chunk.get("message", {}).get("content", "")
                    if text:
                        yield ModelDelta(
                            model_id=request.model,
                            sequence=sequence,
                            text=text,
                        )
                        sequence += 1

                    if chunk.get("done"):
                        yield ModelDelta(
                            model_id=request.model,
                            sequence=sequence,
                            finish_reason=chunk.get("done_reason", "stop"),
                            usage=Usage(
                                input_tokens=chunk.get("prompt_eval_count", 0),
                                output_tokens=chunk.get("eval_count", 0),
                            ),
                        )
                        return