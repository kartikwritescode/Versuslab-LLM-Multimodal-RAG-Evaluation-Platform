import pytest

from app.providers.mock import MockProvider
from app.providers.types import Message, ModelRequest


@pytest.mark.asyncio
async def test_mock_provider_happy_path() -> None:
    # High tokens_per_second and 0 first_token_delay keeps test execution fast
    provider = MockProvider(first_token_delay=0.0, tokens_per_second=1000.0)
    request = ModelRequest(
        model="mock-test",
        messages=[Message(role="user", content="ping pong")],
    )

    deltas = [d async for d in provider.stream(request)]

    assert len(deltas) > 1
    # Check that word chunks are emitted in order
    words_streamed = [d.text for d in deltas if d.text is not None]
    assert "".join(words_streamed).strip() == "This is a mock answer to: ping pong"

    # Final delta must indicate stop and have valid token counts
    final_delta = deltas[-1]
    assert final_delta.finish_reason == "stop"
    assert final_delta.usage is not None
    assert final_delta.usage.input_tokens == 2
    assert final_delta.usage.output_tokens == len(words_streamed)


@pytest.mark.asyncio
async def test_mock_provider_failure_path() -> None:
    # Fail after 2 tokens to simulate mid-stream network or provider failure
    provider = MockProvider(first_token_delay=0.0, tokens_per_second=1000.0, fail_after_tokens=2)
    request = ModelRequest(
        model="mock-test",
        messages=[Message(role="user", content="long prompt to trigger failure condition")],
    )

    with pytest.raises(RuntimeError, match="mock provider failure"):
        async for _ in provider.stream(request):
            pass
