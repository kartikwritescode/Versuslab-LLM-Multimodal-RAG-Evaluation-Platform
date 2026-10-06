from decimal import ROUND_HALF_UP, Decimal

# Pricing per 1,000 tokens in USD (Decimal)
# Sourced from official provider pricing documentation:
# - OpenAI: https://openai.com/api/pricing (gpt-4o-mini: $0.15/1M in, $0.60/1M out)
# - Anthropic: https://docs.anthropic.com (claude-3-5-haiku-20241022: $0.80/1M in, $4.00/1M out)
# - Google Gemini: https://ai.google.dev/pricing (gemini-2.5-flash: $0.30/1M in, $2.50/1M out)
# - xAI Grok: https://docs.x.ai (grok-2-1212 launch pricing: $2.00/1M in, $10.00/1M out)
# - Ollama & Mocks: explicitly $0.000000
MODEL_PRICING_PER_1K: dict[str, tuple[Decimal, Decimal]] = {
    # OpenAI
    "openai:gpt-4o-mini": (Decimal("0.000150"), Decimal("0.000600")),
    "openai": (Decimal("0.000150"), Decimal("0.000600")),
    # Anthropic
    "anthropic:claude-3-5-haiku-20241022": (Decimal("0.000800"), Decimal("0.004000")),
    "anthropic": (Decimal("0.000800"), Decimal("0.004000")),
    # Google Gemini
    "gemini:gemini-3.5-flash": (Decimal("0.000300"), Decimal("0.002500")),
    "gemini:gemini-3-flash-preview": (Decimal("0.000300"), Decimal("0.002500")),
    "gemini:gemini-2.5-flash": (Decimal("0.000300"), Decimal("0.002500")),
    "gemini": (Decimal("0.000300"), Decimal("0.002500")),
    # xAI Grok
    "grok:grok-2-1212": (Decimal("0.002000"), Decimal("0.010000")),
    "xai:grok-2-1212": (Decimal("0.002000"), Decimal("0.010000")),
    "grok": (Decimal("0.002000"), Decimal("0.010000")),
    "xai": (Decimal("0.002000"), Decimal("0.010000")),
    # DeepSeek (official docs: $0.14/1M input, $0.28/1M output for deepseek-chat)
    "deepseek:deepseek-chat": (Decimal("0.000140"), Decimal("0.000280")),
    "deepseek:deepseek-reasoner": (Decimal("0.000550"), Decimal("0.002190")),
    "deepseek": (Decimal("0.000140"), Decimal("0.000280")),
    # Ollama (local models on local hardware; API token cost is explicitly $0.00)
    "ollama:qwen3:8b": (Decimal("0.000000"), Decimal("0.000000")),
    "ollama:qwen3:4b": (Decimal("0.000000"), Decimal("0.000000")),
    "ollama": (Decimal("0.000000"), Decimal("0.000000")),
    # Mock providers for offline testing
    "mock": (Decimal("0.000000"), Decimal("0.000000")),
    "mock-slow": (Decimal("0.000000"), Decimal("0.000000")),
    "mock-broken": (Decimal("0.000000"), Decimal("0.000000")),
    "mock-stuck": (Decimal("0.000000"), Decimal("0.000000")),
}

COST_DECIMAL_PLACES = Decimal("0.000001")


def get_model_rates(model_id: str) -> tuple[Decimal, Decimal] | None:
    """Looks up (input_price_per_1k, output_price_per_1k) for a model spec.

    Checks exact spec first, then provider fallback prefix. If unconfirmed,
    returns None rather than guessing a number.
    """
    if not model_id:
        return None

    if model_id in MODEL_PRICING_PER_1K:
        return MODEL_PRICING_PER_1K[model_id]

    provider_name, _, _ = model_id.partition(":")
    if provider_name == "ollama":
        return Decimal("0.000000"), Decimal("0.000000")

    if provider_name.startswith("mock"):
        return Decimal("0.000000"), Decimal("0.000000")

    if provider_name in MODEL_PRICING_PER_1K:
        return MODEL_PRICING_PER_1K[provider_name]

    # TODO(owner): Configure rates for unconfirmed new models/providers
    return None


def calculate_costs(
    model_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Calculates input_cost, output_cost, and total_cost in USD from token counts.

    Returns:
        (input_cost, output_cost, total_cost) as Decimals quantized to 6 places,
        or (None, None, None) if the model pricing is unconfirmed.
    """
    rates = get_model_rates(model_id)
    if rates is None:
        return None, None, None

    input_rate_1k, output_rate_1k = rates

    in_cost: Decimal | None = None
    if input_tokens is not None:
        in_cost = ((Decimal(input_tokens) / Decimal(1000)) * input_rate_1k).quantize(
            COST_DECIMAL_PLACES, rounding=ROUND_HALF_UP
        )

    out_cost: Decimal | None = None
    if output_tokens is not None:
        out_cost = ((Decimal(output_tokens) / Decimal(1000)) * output_rate_1k).quantize(
            COST_DECIMAL_PLACES, rounding=ROUND_HALF_UP
        )

    total_cost: Decimal | None = None
    if in_cost is not None or out_cost is not None:
        total_cost = (in_cost or Decimal(0)) + (out_cost or Decimal(0))
        total_cost = total_cost.quantize(COST_DECIMAL_PLACES, rounding=ROUND_HALF_UP)

    return in_cost, out_cost, total_cost
