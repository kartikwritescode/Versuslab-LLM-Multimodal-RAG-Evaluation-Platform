import asyncio
from collections.abc import AsyncIterator

from app.providers.types import ModelDelta, ModelRequest, Usage


class MockProvider:
    def __init__(
        self,
        first_token_delay: float = 0.4,
        tokens_per_second: float = 15.0,
        fail_after_tokens: int | None = None,
    ) -> None:
        self._first_token_delay = first_token_delay
        self._token_delay = 1.0 / tokens_per_second
        self._fail_after_tokens = fail_after_tokens

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]:
        prompt = request.messages[-1].content
        words = f"This is a mock answer to: {prompt}".split()

        for i, word in enumerate(words):
            if self._fail_after_tokens is not None and i >= self._fail_after_tokens:
                raise RuntimeError("mock provider failure")
            await asyncio.sleep(self._first_token_delay if i == 0 else self._token_delay)
            yield ModelDelta(
                model_id=request.model,
                sequence=i,
                text=word + " ",
            )

        yield ModelDelta(
            model_id=request.model,
            sequence=len(words),
            finish_reason="stop",
            usage=Usage(
                input_tokens=len(prompt.split()),
                output_tokens=len(words),
            ),
        )