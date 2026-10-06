import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.providers.types import ModelDelta, ModelRequest, Usage

# TODO(owner): Model pricing and context windows belong in a centralized configuration file,
# not hardcoded inside provider adapters.


class OpenAIProvider:
    """Provider adapter for OpenAI-compatible Chat Completions streaming APIs."""

    def __init__(self, base_url: str, api_key: str | None = None, provider_name: str = "openai") -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._provider_name = provider_name

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]:
        if not self._api_key or self._api_key.startswith("your_"):
            if self._provider_name == "grok":
                env_var = "XAI_API_KEY"
            elif self._provider_name == "deepseek":
                env_var = "DEEPSEEK_API_KEY"
            else:
                env_var = "OPENAI_API_KEY"
            raise RuntimeError(
                f"Provider '{self._provider_name}' requires an API key. "
                f"Please configure {env_var} in apps/api/.env."
            )

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": True,
            # stream_options.include_usage requests a final usage chunk reporting prompt & completion tokens
            "stream_options": {"include_usage": True},
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # Differentiated timeouts: fast failure if API gateway is down, generous read timeout for long generations
        timeout = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
        sequence = 0
        last_finish_reason: str | None = None
        has_emitted_final = False

        endpoint = f"{self._base_url}/chat/completions"

        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("POST", endpoint, json=payload, headers=headers) as response,
        ):
            if response.status_code >= 400:
                raw_body = await response.aread()
                p_label = self._provider_name.capitalize()
                err_msg = f"{p_label} API returned HTTP {response.status_code}"
                try:
                    err_json = json.loads(raw_body)
                    if "error" in err_json:
                        err_obj = err_json["error"]
                        if isinstance(err_obj, dict):
                            msg = err_obj.get("message")
                            code = err_obj.get("code")
                            if msg:
                                err_msg = f"{p_label} error ({code or response.status_code}): {msg}"
                        elif isinstance(err_obj, str):
                            err_msg = f"{p_label} error ({response.status_code}): {err_obj}"
                    elif "message" in err_json:
                        err_msg = f"{p_label} error ({response.status_code}): {err_json['message']}"
                except (json.JSONDecodeError, ValueError, TypeError):
                    text = raw_body.decode("utf-8", errors="replace").strip()
                    if text:
                        err_msg = f"{p_label} error ({response.status_code}): {text[:200]}"
                raise RuntimeError(err_msg)

            async for line in response.aiter_lines():
                if not line or not line.strip():
                    continue

                line_text = line.strip()
                if not line_text.startswith("data: "):
                    continue

                raw_data = line_text.removeprefix("data: ").strip()
                if raw_data == "[DONE]":
                    break

                chunk = json.loads(raw_data)

                # Defensive extraction: choices list may be empty in usage-only chunks
                choices = chunk.get("choices")
                if choices and isinstance(choices, list) and len(choices) > 0:
                    choice = choices[0] if isinstance(choices[0], dict) else {}
                    delta_obj = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                    content = delta_obj.get("content")
                    finish_reason = choice.get("finish_reason")

                    if finish_reason:
                        last_finish_reason = str(finish_reason)

                    if content:
                        yield ModelDelta(
                            model_id=request.model,
                            sequence=sequence,
                            text=str(content),
                        )
                        sequence += 1

                # Final usage chunk with include_usage enabled
                usage_dict = chunk.get("usage")
                if usage_dict and isinstance(usage_dict, dict):
                    yield ModelDelta(
                        model_id=request.model,
                        sequence=sequence,
                        finish_reason=last_finish_reason or "stop",
                        usage=Usage(
                            input_tokens=int(usage_dict.get("prompt_tokens") or 0),
                            output_tokens=int(usage_dict.get("completion_tokens") or 0),
                        ),
                    )
                    has_emitted_final = True
                    return

        # Fallback if provider didn't emit a usage chunk
        if not has_emitted_final:
            yield ModelDelta(
                model_id=request.model,
                sequence=sequence,
                finish_reason=last_finish_reason or "stop",
            )
