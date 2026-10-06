import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.providers.types import ModelDelta, ModelRequest, Usage

# TODO(owner): Model pricing and context windows belong in a centralized configuration file,
# not hardcoded inside provider adapters.


class GeminiProvider:
    """Provider adapter for Google Gemini REST API using streamGenerateContent?alt=sse."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]:
        if not self._api_key or self._api_key.startswith("your_"):
            raise RuntimeError(
                "Provider 'gemini' requires an API key. "
                "Please configure GEMINI_API_KEY in apps/api/.env."
            )

        # Convert messages to Gemini's format: system messages become systemInstruction,
        # 'assistant' role maps to 'model'
        contents: list[dict[str, Any]] = []
        system_instruction: dict[str, Any] | None = None

        for m in request.messages:
            if m.role == "system":
                system_instruction = {"parts": [{"text": m.content}]}
            else:
                role = "user" if m.role == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m.content}]})

        generation_config: dict[str, Any] = {"temperature": request.temperature}
        if request.max_tokens is not None:
            generation_config["maxOutputTokens"] = request.max_tokens

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
        sequence = 0
        prompt_tokens = 0
        output_tokens = 0
        last_finish_reason: str | None = None

        # Resolve model endpoint: Google AI Studio serves Gemini 3 Flash under 'gemini-3-flash-preview'.
        # Alias 'gemini-3.5-flash' / 'gemini-3-flash' to this active production endpoint so requests stream instantly
        # rather than hitting the queued 503/timeout behavior of unserved catalog names.
        target_model = request.model
        if target_model in ("gemini-3.5-flash", "gemini-3-flash"):
            endpoint_model = "gemini-3-flash-preview"
        else:
            endpoint_model = target_model

        endpoint = f"{self._base_url}/v1beta/models/{endpoint_model}:streamGenerateContent?alt=sse"

        async with httpx.AsyncClient(timeout=timeout) as client:
            attempt = 0
            while True:
                async with client.stream("POST", endpoint, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        # Transient retry on 503 high demand spikes
                        if response.status_code == 503 and attempt < 1:
                            attempt += 1
                            await asyncio.sleep(1.0)
                            continue

                        raw_body = await response.aread()
                        err_msg = f"Gemini API returned HTTP {response.status_code}"
                        try:
                            err_json = json.loads(raw_body)
                            if "error" in err_json:
                                error_obj = err_json["error"]
                                if isinstance(error_obj, dict):
                                    msg = error_obj.get("message")
                                    status_text = error_obj.get("status")
                                    if msg:
                                        err_msg = f"Gemini error ({status_text or response.status_code}): {msg}"
                                elif isinstance(error_obj, str):
                                    err_msg = f"Gemini error ({response.status_code}): {error_obj}"
                        except (json.JSONDecodeError, ValueError, TypeError):
                            text = raw_body.decode("utf-8", errors="replace").strip()
                            if text:
                                err_msg = f"Gemini error ({response.status_code}): {text[:200]}"
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

                        # Candidates list provides generated text parts and finish reasons
                        candidates = chunk.get("candidates")
                        if candidates and isinstance(candidates, list) and len(candidates) > 0:
                            cand = candidates[0] if isinstance(candidates[0], dict) else {}
                            content_obj = cand.get("content") if isinstance(cand.get("content"), dict) else {}
                            parts = content_obj.get("parts") or []

                            raw_finish = cand.get("finishReason")
                            if raw_finish:
                                # Normalize Gemini's "STOP" to lowercase "stop"
                                last_finish_reason = str(raw_finish).lower()

                            for part in parts:
                                if isinstance(part, dict) and "text" in part:
                                    text = part.get("text")
                                    if text:
                                        yield ModelDelta(
                                            model_id=request.model,
                                            sequence=sequence,
                                            text=str(text),
                                        )
                                        sequence += 1

                        # usageMetadata tracks input and output token consumption
                        usage_meta = chunk.get("usageMetadata")
                        if usage_meta and isinstance(usage_meta, dict):
                            prompt_tokens = int(usage_meta.get("promptTokenCount") or prompt_tokens)
                            output_tokens = int(usage_meta.get("candidatesTokenCount") or output_tokens)

                    # Stream finished cleanly
                    break

        # Final delta summarizing completion and token usage
        yield ModelDelta(
            model_id=request.model,
            sequence=sequence,
            finish_reason=last_finish_reason or "stop",
            usage=Usage(
                input_tokens=prompt_tokens,
                output_tokens=output_tokens,
            ),
        )
