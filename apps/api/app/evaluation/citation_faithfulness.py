import json
import logging
import re
from typing import Any

from app.core.config import settings
from app.db.models import DocumentChunk
from app.providers.registry import DEFAULT_MODELS, PROVIDERS
from app.providers.types import Message, ModelRequest

logger = logging.getLogger(__name__)

FAITHFULNESS_PROMPT_TEMPLATE = """You are an impartial evaluator assessing citation faithfulness in a generated text.

USER PROMPT:
{prompt}

MODEL ANSWER:
{answer}

CITED SOURCE [{citation_id}]:
{chunk_text}

TASK:
Determine whether the cited source text directly and factually supports the statement or claim associated with [{citation_id}] in the model's answer.

Respond strictly in valid JSON matching this schema:
{{
  "faithfulness_score": <float between 0.0 and 1.0, where 1.0 means fully supported and 0.0 means completely unsupported or contradicted>,
  "reason": "<short 1-2 sentence explanation>"
}}
"""


async def call_llm(provider_spec: str, prompt_text: str) -> tuple[str, str]:
    """Invokes a provider using the streaming protocol to receive a complete text response."""
    provider_name, sep, model = provider_spec.partition(":")
    provider = PROVIDERS.get(provider_name)
    if provider is None:
        raise ValueError(f"Unknown provider in spec: {provider_spec}")

    chosen_model = model if (sep and model) else DEFAULT_MODELS.get(provider_name, "")
    if not chosen_model:
        raise ValueError(f"No default model configured for provider: {provider_name}")

    resolved_id = f"{provider_name}:{chosen_model}"
    request = ModelRequest(
        model=chosen_model,
        messages=[Message(role="user", content=prompt_text)],
        temperature=0.0,
    )

    deltas: list[str] = []
    async for delta in provider.stream(request):
        if delta.text:
            deltas.append(delta.text)

    return "".join(deltas), resolved_id


def _parse_faithfulness_json(raw_text: str) -> tuple[float, str]:
    """Parses JSON response containing faithfulness_score and reason."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1 and cleaned.endswith("```"):
            cleaned = cleaned[first_newline + 1 : -3].strip()

    try:
        data = json.loads(cleaned)
        score = float(data.get("faithfulness_score", 0.0))
        # Clamp score between 0.0 and 1.0
        score = max(0.0, min(1.0, score))
        reason = str(data.get("reason", "No reason provided."))
        return score, reason
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse faithfulness JSON from response '%s': %s", raw_text, exc)
        return 0.0, f"Malformed judge output: {raw_text[:100]}"


async def evaluate_citation_faithfulness(
    prompt: str,
    answer: str,
    retrieved_chunks: list[DocumentChunk],
    judge_model: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluates citation faithfulness: whether cited sources support specific claims.

    Returns a list of evaluation dicts ready for persistence:
    - One evaluation per checked citation (metric="citation_faithfulness")
    - One aggregate evaluation (metric="faithfulness", averaged)
    """
    if not answer or not retrieved_chunks:
        return []

    judge_spec = judge_model or settings.judge_model

    # Build map of citation IDs [S1], [S2] ... to DocumentChunk instances
    chunk_map: dict[str, DocumentChunk] = {
        f"S{idx + 1}": chunk for idx, chunk in enumerate(retrieved_chunks)
    }

    # Extract all cited source IDs
    cited_ids = sorted(set(re.findall(r"\[(S\d+)\]", answer)))
    if not cited_ids:
        return []

    evaluations: list[dict[str, Any]] = []
    scores: list[float] = []
    active_judge_id: str = judge_spec

    for cid in cited_ids:
        chunk = chunk_map.get(cid)
        if chunk is None:
            # The model cited a non-existent source
            evaluations.append(
                {
                    "metric": "citation_faithfulness",
                    "score": 0.0,
                    "judge_model": active_judge_id,
                    "reason": f"[{cid}]: Source ID was cited but does not exist in retrieved evidence.",
                }
            )
            scores.append(0.0)
            continue

        prompt_payload = FAITHFULNESS_PROMPT_TEMPLATE.format(
            prompt=prompt,
            answer=answer,
            citation_id=cid,
            chunk_text=chunk.text.strip(),
        )

        try:
            judge_output, active_judge_id = await call_llm(judge_spec, prompt_payload)
            score, reason = _parse_faithfulness_json(judge_output)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to execute citation faithfulness judge: %s", exc)
            score, reason = 0.0, f"Judge execution failure: {exc}"

        scores.append(score)
        evaluations.append(
            {
                "metric": "citation_faithfulness",
                "score": score,
                "judge_model": active_judge_id,
                "reason": f"[{cid}]: {reason}",
            }
        )

    # Calculate overall aggregate faithfulness
    if scores:
        avg_score = round(sum(scores) / len(scores), 4)
        evaluations.append(
            {
                "metric": "faithfulness",
                "score": avg_score,
                "judge_model": active_judge_id,
                "reason": f"Average citation faithfulness across {len(scores)} cited sources.",
            }
        )

    return evaluations
