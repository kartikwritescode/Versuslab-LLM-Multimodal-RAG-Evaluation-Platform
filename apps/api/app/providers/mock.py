import asyncio
from collections.abc import AsyncIterator

from app.providers.types import ModelDelta, ModelRequest, Usage


class MockProvider:
    """Deterministic mock provider for predictable testing and benchmarking."""

    def __init__(
        self,
        first_token_delay: float = 0.4,
        tokens_per_second: float = 15.0,
        fail_after_tokens: int | None = None,
        canned_responses: dict[str, str] | None = None,
    ) -> None:
        self._first_token_delay = first_token_delay
        self._token_delay = 1.0 / tokens_per_second
        # fail_after_tokens allows tests to simulate mid-stream provider disconnections or crashes
        self._fail_after_tokens = fail_after_tokens
        self._canned_responses = canned_responses or {}

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]:
        prompt = request.messages[-1].content if request.messages else ""
        if prompt in self._canned_responses:
            answer = self._canned_responses[prompt]
        else:
            answer = f"This is a mock answer to: {prompt}"
        words = answer.split()

        for i, word in enumerate(words):
            if self._fail_after_tokens is not None and i >= self._fail_after_tokens:
                raise RuntimeError("mock provider failure")

            # Simulate realistic time-to-first-token delay followed by inter-token generation speed
            await asyncio.sleep(self._first_token_delay if i == 0 else self._token_delay)
            yield ModelDelta(
                model_id=request.model,
                sequence=i,
                text=word + " ",
            )

        # Final delta indicates completion and supplies token consumption metrics
        yield ModelDelta(
            model_id=request.model,
            sequence=len(words),
            finish_reason="stop",
            usage=Usage(
                input_tokens=len(prompt.split()),
                output_tokens=len(words),
            ),
        )
