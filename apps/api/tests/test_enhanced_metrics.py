"""Unit tests for enhanced performance, economic, quality, and content metrics."""
from decimal import Decimal

from app.evaluation.metrics import (
    calculate_aggregate_quality_score,
    calculate_all_metrics,
    calculate_confidence_and_qualifiers,
    calculate_confidence_score,
    calculate_context_utilization,
    calculate_cost_per_1k_tokens,
    calculate_cost_per_second,
    calculate_cost_quality_ratio,
    calculate_input_tokens_per_second,
    calculate_response_length_stats,
    calculate_streaming_stability,
    calculate_time_per_output_token,
    calculate_tokens_per_second,
)


def test_metric_1_tokens_per_second():
    # Happy path: 100 tokens in 2000ms = 50.0 tok/s
    assert calculate_tokens_per_second(100, 2000) == 50.0
    # Zero or None failure paths
    assert calculate_tokens_per_second(None, 2000) is None
    assert calculate_tokens_per_second(100, None) is None
    assert calculate_tokens_per_second(100, 0) is None
    assert calculate_tokens_per_second(100, -10) is None


def test_metric_2_time_per_output_token():
    # Happy path: latency 1200ms, ttft 200ms, 50 tokens -> 1000ms / 50 = 20.0 ms/tok
    assert calculate_time_per_output_token(200, 1200, 50) == 20.0
    # Boundary/failure paths
    assert calculate_time_per_output_token(None, 1200, 50) is None
    assert calculate_time_per_output_token(200, None, 50) is None
    assert calculate_time_per_output_token(200, 1200, None) is None
    assert calculate_time_per_output_token(200, 1200, 0) is None
    assert calculate_time_per_output_token(1200, 200, 50) is None  # negative generation time


def test_metric_3_cost_efficiency_metrics():
    cost = Decimal("0.005000")
    # Cost per 1K output tokens: (0.005 / 500) * 1000 = 0.010000
    assert calculate_cost_per_1k_tokens(cost, 500) == Decimal("0.010000")
    assert calculate_cost_per_1k_tokens(None, 500) is None
    assert calculate_cost_per_1k_tokens(cost, 0) is None

    # Cost per second: 0.005 / (2500 / 1000) = 0.002000
    assert calculate_cost_per_second(cost, 2500) == Decimal("0.002000")
    assert calculate_cost_per_second(None, 2500) is None
    assert calculate_cost_per_second(cost, 0) is None


def test_metric_4_response_length_stats():
    text = "VersusLab is fast and reliable! It evaluates models seamlessly. Compare them now."
    words, chars, sentences = calculate_response_length_stats(text)
    assert words == 12
    assert chars == len(text.strip())
    assert sentences == 3

    # Empty text
    w, c, s = calculate_response_length_stats("")
    assert (w, c, s) == (0, 0, 0)
    assert calculate_response_length_stats(None) == (0, 0, 0)


def test_metric_5_aggregate_quality_score():
    evals = [{"score": 0.8}, {"score": 0.9}]
    # Average: 0.85 -> scaled to 10 is 8.5
    assert calculate_aggregate_quality_score(evals) == 8.5
    assert calculate_aggregate_quality_score([]) is None
    assert calculate_aggregate_quality_score(None) is None


def test_metric_8_confidence_and_qualifiers():
    # Assertive text without hedge words
    assertive_text = "The speed of light in vacuum is exactly 299,792,458 meters per second."
    score, count = calculate_confidence_and_qualifiers(assertive_text)
    assert score == 1.0
    assert count == 0

    # Uncertain text with hedge words
    uncertain_text = "Maybe this could possibly be true, perhaps it might happen."
    score_unc, count_unc = calculate_confidence_and_qualifiers(uncertain_text)
    assert score_unc < 0.5
    assert count_unc >= 4
    assert calculate_confidence_score(uncertain_text) == score_unc

    # Empty text
    assert calculate_confidence_and_qualifiers("") == (None, 0)
    assert calculate_confidence_score(None) is None


def test_metric_9_input_tokens_per_second():
    # 500 input tokens processed in 250ms = 2000 tok/s
    assert calculate_input_tokens_per_second(500, 250) == 2000.0
    assert calculate_input_tokens_per_second(None, 250) is None
    assert calculate_input_tokens_per_second(500, 0) is None


def test_metric_10_context_utilization():
    # openai:gpt-4o has 128,000 max context
    util, max_ctx = calculate_context_utilization(1280, "openai:gpt-4o")
    assert util == 1.0  # 1%
    assert max_ctx == 128000

    # Unknown model fallback
    u_none, ctx_none = calculate_context_utilization(100, "unknown:custom-model")
    assert u_none is None
    assert ctx_none is None


def test_metric_11_streaming_stability():
    avg_size, status = calculate_streaming_stability(10, 250)
    assert avg_size == 25.0
    assert status == "Stable"

    # Edge cases
    assert calculate_streaming_stability(0, 250) == (None, None)
    assert calculate_streaming_stability(None, 250) == (None, None)


def test_metric_15_cost_quality_ratio():
    # 8.0 quality score, $0.004 cost -> 2000 quality pts / dollar
    assert calculate_cost_quality_ratio(8.0, 0.004) == 2000.0
    assert calculate_cost_quality_ratio(8.0, Decimal("0.004")) == 2000.0

    # Zero cost (free model like local Ollama)
    assert calculate_cost_quality_ratio(8.0, 0.0) is None
    assert calculate_cost_quality_ratio(None, 0.004) is None
    assert calculate_cost_quality_ratio(8.0, None) is None


def test_calculate_all_metrics():
    metrics = calculate_all_metrics(
        model_id="openai:gpt-4o",
        ttft_ms=300,
        latency_ms=1500,
        input_tokens=600,
        output_tokens=60,
        response_text="VersusLab delivers superior LLM evaluation metrics quickly.",
        total_cost=Decimal("0.003000"),
        evaluations=[{"score": 0.9}],
        chunk_count=12,
    )

    assert metrics["tokens_per_second"] == 40.0
    assert metrics["time_per_output_token"] == 20.0
    assert metrics["input_tokens_per_second"] == 2000.0
    assert metrics["cost_per_1k_tokens"] == Decimal("0.050000")
    assert metrics["cost_per_second"] == Decimal("0.002000")
    assert metrics["response_word_count"] == 7
    assert metrics["response_sentence_count"] == 1
    assert metrics["aggregate_quality_score"] == 9.0
    assert metrics["confidence_score"] == 1.0
    assert metrics["qualifier_count"] == 0
    assert metrics["model_max_context"] == 128000
    assert metrics["streaming_chunk_count"] == 12
    assert metrics["avg_chunk_size"] is not None
    assert metrics["cost_quality_ratio"] == 3000.0
