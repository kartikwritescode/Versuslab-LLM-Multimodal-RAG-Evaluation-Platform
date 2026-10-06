import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.providers.types import ModelDelta, ModelRequest, Usage

# TODO(owner): Model pricing and context windows belong in a centralized configuration file,
# not hardcoded inside provider adapters.


class AnthropicProvider:
    """Provider adapter for Anthropic's Messages streaming API."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]:
        if not self._api_key or self._api_key.startswith("your_"):
            raise RuntimeError(
                "Provider 'anthropic' requires an API key. "
                "Please configure ANTHROPIC_API_KEY in apps/api/.env."
            )

        # Anthropic separates top-level system prompts from the conversation messages
        system_prompts = [m.content for m in request.messages if m.role == "system"]
        conversation = [
            {"role": m.role, "content": m.content}
            for m in request.messages
            if m.role in ("user", "assistant")
        ]

        # Anthropic's Messages API requires max_tokens to be specified
        max_tokens = request.max_tokens or 4096

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": conversation,
            "max_tokens": max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
        sequence = 0
        input_tokens = 0
        output_tokens = 0
        stop_reason: str | None = None
        has_emitted_final = False

        endpoint = f"{self._base_url}/v1/messages"

        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("POST", endpoint, json=payload, headers=headers) as response,
        ):
            if response.status_code >= 400:
                raw_body = await response.aread()
                err_msg = f"Anthropic API returned HTTP {response.status_code}"
                try:
                    err_json = json.loads(raw_body)
                    if "error" in err_json and isinstance(err_json["error"], dict):
                        msg = err_json["error"].get("message")
                        err_type = err_json["error"].get("type")
                        if msg:
                            err_msg = f"Anthropic error ({err_type or response.status_code}): {msg}"
                except (json.JSONDecodeError, ValueError, TypeError):
                    text = raw_body.decode("utf-8", errors="replace").strip()
                    if text:
                        err_msg = f"Anthropic error ({response.status_code}): {text[:200]}"
                raise RuntimeError(err_msg)

            async for line in response.aiter_lines():
                if not line or not line.strip():
                    continue

                line_text = line.strip()
                if not line_text.startswith("data: "):
                    continue

                raw_data = line_text.removeprefix("data: ").strip()
                if not raw_data:
                    continue

                chunk = json.loads(raw_data)
                event_type = chunk.get("type")

                # Initial event provides message metadata and input token count
                if event_type == "message_start":
                    msg_obj = chunk.get("message")
                    if isinstance(msg_obj, dict):
                        usage_obj = msg_obj.get("usage")
                        if isinstance(usage_obj, dict):
                            input_tokens = int(usage_obj.get("input_tokens") or 0)

                # Incremental text delta event
                elif event_type == "content_block_delta":
                    delta_obj = chunk.get("delta")
                    if isinstance(delta_obj, dict):
                        text = delta_obj.get("text")
                        if text:
                            yield ModelDelta(
                                model_id=request.model,
                                sequence=sequence,
                                text=str(text),
                            )
                            sequence += 1

                # Final update with completion token count and finish reason
                elif event_type == "message_delta":
                    delta_obj = chunk.get("delta")
                    if isinstance(delta_obj, dict):
                        stop_reason = delta_obj.get("stop_reason")

                    usage_obj = chunk.get("usage")
                    if isinstance(usage_obj, dict):
                        output_tokens = int(usage_obj.get("output_tokens") or 0)

                # End of message event
                elif event_type == "message_stop":
                    yield ModelDelta(
                        model_id=request.model,
                        sequence=sequence,
                        finish_reason=str(stop_reason or "stop"),
                        usage=Usage(
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                        ),
                    )
                    has_emitted_final = True
                    return

        if not has_emitted_final:
            yield ModelDelta(
                model_id=request.model,
                sequence=sequence,
                finish_reason=str(stop_reason or "stop"),
                usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
            )
