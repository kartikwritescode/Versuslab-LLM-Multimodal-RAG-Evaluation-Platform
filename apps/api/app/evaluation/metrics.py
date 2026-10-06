"""Enhanced metrics calculation for model runs.

This module provides comprehensive metrics calculation including:
- Performance: tokens/second, TPOT, input processing speed
- Cost efficiency: cost per 1K tokens, cost per second
- Response analysis: word/character/sentence counts
- Quality: aggregate scores, confidence indicators
- Context utilization
"""
import re
from decimal import ROUND_HALF_UP, Decimal

# Hedge/qualifier words that indicate uncertainty
HEDGE_WORDS = {
    "maybe", "might", "possibly", "perhaps", "probably", "likely",
    "could", "may", "seems", "appears", "suggests", "potentially",
    "arguably", "presumably", "supposedly", "allegedly", "reportedly",
    "apparently", "seemingly", "essentially", "basically", "generally",
    "typically", "usually", "often", "sometimes", "occasionally",
}

# Model context limits (in tokens) - used for context utilization calculation
MODEL_MAX_CONTEXT = {
    "openai:gpt-4o-mini": 128000,
    "openai:gpt-4o": 128000,
    "openai:gpt-4-turbo": 128000,
    "anthropic:claude-3-5-haiku-20241022": 200000,
    "anthropic:claude-3-5-sonnet-20241022": 200000,
    "anthropic:claude-3-opus-20240229": 200000,
    "gemini:gemini-2.5-flash": 1048576,
    "gemini:gemini-3.5-flash": 1048576,
    "gemini:gemini-3-flash-preview": 1048576,
    "grok:grok-2-1212": 131072,
    "xai:grok-2-1212": 131072,
    "deepseek:deepseek-chat": 64000,
    "deepseek:deepseek-reasoner": 64000,
}


def get_model_max_context(model_id: str) -> int | None:
    """Returns the maximum context window size for a model."""
    if model_id in MODEL_MAX_CONTEXT:
        return MODEL_MAX_CONTEXT[model_id]

    # Try provider-level fallback
    provider_name = model_id.split(":")[0] if ":" in model_id else model_id

    # Ollama models typically have smaller contexts
    if provider_name == "ollama":
        return 8192  # Conservative estimate for local models

    # Default for unknown models
    return None


def calculate_tokens_per_second(
    output_tokens: int | None,
    latency_ms: int | None,
) -> float | None:
    """Calculates generation throughput in tokens per second.

    Formula: output_tokens / (latency_ms / 1000)
    """
    if output_tokens is None or latency_ms is None or latency_ms <= 0:
        return None

    return round(output_tokens / (latency_ms / 1000.0), 2)


def calculate_time_per_output_token(
    ttft_ms: int | None,
    latency_ms: int | None,
    output_tokens: int | None,
) -> float | None:
    """Calculates average time per output token (TPOT).

    Formula: (latency_ms - ttft_ms) / output_tokens
    """
    if ttft_ms is None or latency_ms is None or output_tokens is None or output_tokens <= 0:
        return None

    generation_time = latency_ms - ttft_ms
    if generation_time <= 0:
        return None

    return round(generation_time / output_tokens, 2)


def calculate_input_tokens_per_second(
    input_tokens: int | None,
    ttft_ms: int | None,
) -> float | None:
    """Calculates prompt processing speed in tokens per second.

    Formula: input_tokens / (ttft_ms / 1000)
    """
    if input_tokens is None or ttft_ms is None or ttft_ms <= 0:
        return None

    return round(input_tokens / (ttft_ms / 1000.0), 2)


def calculate_cost_per_1k_tokens(
    total_cost: Decimal | None,
    output_tokens: int | None,
) -> Decimal | None:
    """Calculates cost per 1,000 output tokens.

    Formula: (total_cost / output_tokens) * 1000
    """
    if total_cost is None or output_tokens is None or output_tokens <= 0:
        return None

    cost_per_token = total_cost / Decimal(output_tokens)
    cost_per_1k = (cost_per_token * Decimal(1000)).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    return cost_per_1k


def calculate_cost_per_second(
    total_cost: Decimal | None,
    latency_ms: int | None,
) -> Decimal | None:
    """Calculates cost per second of generation time.

    Formula: total_cost / (latency_ms / 1000)
    """
    if total_cost is None or latency_ms is None or latency_ms <= 0:
        return None

    latency_seconds = Decimal(latency_ms) / Decimal(1000)
    cost_per_sec = (total_cost / latency_seconds).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    return cost_per_sec


def calculate_response_length_stats(
    response_text: str | None,
) -> tuple[int, int, int]:
    """Calculates word count, character count, and sentence count.

    Returns:
        (word_count, char_count, sentence_count)
    """
    if not response_text:
        return 0, 0, 0

    # Character count (excluding leading/trailing whitespace)
    char_count = len(response_text.strip())

    # Word count (split on whitespace)
    words = response_text.split()
    word_count = len(words)

    # Sentence count (simple heuristic: count sentence-ending punctuation)
    # This is a rough estimate
    sentence_endings = re.findall(r'[.!?]+', response_text)
    sentence_count = len(sentence_endings) if sentence_endings else 1

    return word_count, char_count, sentence_count


def calculate_aggregate_quality_score(
    evaluations: list[dict[str, float]],
) -> float | None:
    """Calculates weighted average of all evaluation scores.

    Args:
        evaluations: List of dicts with 'score' key (0.0-1.0)

    Returns:
        Average score scaled to 0-10, or None if no evaluations
    """
    if not evaluations:
        return None

    scores = [ev.get("score", 0.0) for ev in evaluations]
    if not scores:
        return None

    avg_score = sum(scores) / len(scores)
    # Scale from 0-1 to 0-10
    return round(avg_score * 10, 2)


def calculate_confidence_and_qualifiers(
    response_text: str | None,
) -> tuple[float | None, int]:
    """Calculates confidence score and qualifier (hedge word) count.

    Lower hedge word density = higher confidence.
    Returns:
        (confidence_score, qualifier_count)
        where confidence_score is 0.0-1.0 (or None if no text),
        and qualifier_count is the integer count of hedge words.
    """
    if not response_text:
        return None, 0

    words = response_text.lower().split()
    if not words:
        return None, 0

    hedge_count = sum(1 for word in words if word.strip(".,!?;:") in HEDGE_WORDS)
    hedge_ratio = hedge_count / len(words)

    # Convert ratio to confidence score (inverse relationship)
    if hedge_ratio >= 0.10:
        confidence = 0.0
    else:
        confidence = 1.0 - (hedge_ratio * 10)

    return round(max(0.0, min(1.0, confidence)), 3), hedge_count


def calculate_confidence_score(
    response_text: str | None,
) -> float | None:
    """Calculates confidence score based on hedge word frequency (0.0 to 1.0)."""
    score, _ = calculate_confidence_and_qualifiers(response_text)
    return score


def calculate_cost_quality_ratio(
    aggregate_quality_score: float | None,
    total_cost: Decimal | float | None,
) -> float | None:
    """Calculates quality points per dollar (Metric 15: Cost vs Quality Tradeoff).

    Formula: aggregate_quality_score / total_cost
    Higher is better. If total_cost is 0 or negligible, returns None (representing free/infinite).
    """
    if aggregate_quality_score is None or total_cost is None:
        return None

    cost_val = float(total_cost)
    if cost_val <= 0:
        return None

    return round(aggregate_quality_score / cost_val, 2)


def calculate_streaming_stability(
    chunk_count: int | None,
    response_char_count: int | None,
) -> tuple[float | None, str | None]:
    """Calculates average chunk size and streaming stability status (Metric 11).

    Returns:
        (avg_chunk_size, stability_status)
    """
    if chunk_count is None or chunk_count <= 0:
        return None, None

    avg_size = round(response_char_count / chunk_count, 1) if response_char_count is not None else None
    status = "Stable"
    return avg_size, status


def calculate_context_utilization(
    input_tokens: int | None,
    model_id: str,
) -> tuple[float | None, int | None]:
    """Calculates percentage of max context window used.

    Returns:
        (utilization_percent, max_context_size)
    """
    max_context = get_model_max_context(model_id)

    if input_tokens is None or max_context is None:
        return None, max_context

    utilization = (input_tokens / max_context) * 100
    return round(utilization, 2), max_context


def calculate_all_metrics(
    model_id: str,
    ttft_ms: int | None,
    latency_ms: int | None,
    input_tokens: int | None,
    output_tokens: int | None,
    response_text: str,
    total_cost: Decimal | float | None,
    evaluations: list[dict[str, float]] | None = None,
    chunk_count: int | None = None,
) -> dict[str, float | Decimal | int | str | None]:
    """Calculates all enhanced metrics for a model run.

    Returns:
        Dictionary with all calculated metrics
    """
    word_count, char_count, sentence_count = calculate_response_length_stats(response_text)
    context_util, max_context = calculate_context_utilization(input_tokens, model_id)
    confidence_score, qualifier_count = calculate_confidence_and_qualifiers(response_text)
    aggregate_score = calculate_aggregate_quality_score(evaluations or [])
    cost_quality_ratio = calculate_cost_quality_ratio(aggregate_score, total_cost)
    avg_chunk_size, _ = calculate_streaming_stability(chunk_count, char_count)

    decimal_cost = Decimal(str(total_cost)) if total_cost is not None else None

    return {
        # Performance metrics
        "tokens_per_second": calculate_tokens_per_second(output_tokens, latency_ms),
        "time_per_output_token": calculate_time_per_output_token(ttft_ms, latency_ms, output_tokens),
        "input_tokens_per_second": calculate_input_tokens_per_second(input_tokens, ttft_ms),

        # Cost efficiency metrics
        "cost_per_1k_tokens": calculate_cost_per_1k_tokens(decimal_cost, output_tokens),
        "cost_per_second": calculate_cost_per_second(decimal_cost, latency_ms),

        # Response length statistics
        "response_word_count": word_count,
        "response_char_count": char_count,
        "response_sentence_count": sentence_count,

        # Quality & certainty metrics
        "aggregate_quality_score": aggregate_score,
        "confidence_score": confidence_score,
        "qualifier_count": qualifier_count,

        # Context utilization
        "context_utilization_percent": context_util,
        "model_max_context": max_context,

        # Streaming stability metrics
        "streaming_chunk_count": chunk_count,
        "avg_chunk_size": avg_chunk_size,

        # Cost vs Quality tradeoff
        "cost_quality_ratio": cost_quality_ratio,
    }

