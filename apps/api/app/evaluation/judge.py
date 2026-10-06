import json
import logging
import string
from typing import Any

from app.core.config import settings
from app.evaluation.citation_faithfulness import call_llm

logger = logging.getLogger(__name__)

# Note on Evaluator Bias:
# Blind judging (anonymizing contenders as [Answer A], [Answer B]) removes explicit brand and model
# name bias. However, LLM judges may still exhibit subtle self-preference bias (preferring outputs
# with styles similar to their own model family) or verbosity bias. Blind judging reduces but does
# not completely eliminate evaluator bias.

JUDGE_PROMPT_TEMPLATE = """You are an expert, impartial evaluator evaluating multiple candidate AI answers to a given prompt.
Evaluate each answer strictly on its own merits without bias toward length, style, or perceived origin.

USER PROMPT:
{prompt}

CANDIDATE ANSWERS:
{candidate_blocks}

CRITERIA:
Evaluate each candidate answer on a scale from 0.0 to 1.0 (where 1.0 is best) across 4 dimensions:
1. correctness: Is the factual claims and reasoning sound and accurate?
2. relevance: Does the answer directly address the specific question asked?
3. completeness: Does the answer cover all required aspects without omission?
4. instruction_following: Does the answer respect all constraints and formatting in the prompt?

Respond ONLY with valid JSON matching this exact structure:
{{
  "evaluations": {{
{schema_hints}
  }}
}}
"""


def _parse_judge_json(raw_text: str) -> dict[str, dict[str, Any]]:
    """Strips markdown fences and parses the JSON evaluations from the judge."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1 and cleaned.endswith("```"):
            cleaned = cleaned[first_newline + 1 : -3].strip()

    try:
        data = json.loads(cleaned)
        if "evaluations" in data and isinstance(data["evaluations"], dict):
            return data["evaluations"]
        if "answers" in data and isinstance(data["answers"], list):
            res: dict[str, dict[str, Any]] = {}
            for item in data["answers"]:
                label = item.get("label") or item.get("answer")
                if label:
                    res[str(label)] = item
            return res
        if isinstance(data, dict):
            return data
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse blind judge JSON: %s. Response: %s", exc, raw_text[:200])
        return {}


async def run_blind_judge(
    prompt: str,
    contenders: list[dict[str, Any]],
    judge_model: str | None = None,
) -> list[dict[str, Any]]:
    """Runs a general-purpose blind LLM-as-judge across contender answers.

    contenders: list of dicts with keys: 'run_id', 'model_id', 'response_text'

    Returns a flat list of evaluation records for persistence:
    [
      {
        "model_run_id": ...,
        "metric": "correctness" | "relevance" | "completeness" | "instruction_following",
        "score": float,
        "judge_model": str,
        "reason": str
      },
      ...
    ]
    """
    # Filter contenders that produced non-empty responses
    valid_contenders = [c for c in contenders if c.get("response_text", "").strip()]
    if not valid_contenders:
        return []

    judge_spec = judge_model or settings.judge_model

    # 1. Blind the contenders: assign anonymous labels Answer A, Answer B, ...
    label_to_contender: dict[str, dict[str, Any]] = {}
    blocks: list[str] = []
    schema_hint_lines: list[str] = []

    for idx, contender in enumerate(valid_contenders):
        label_letter = string.ascii_uppercase[idx % len(string.ascii_uppercase)]
        label = f"Answer {label_letter}"
        label_to_contender[label] = contender

        block = f"[{label}]\n{contender['response_text'].strip()}"
        blocks.append(block)

        hint = (
            f'    "{label}": {{\n'
            f'      "correctness": 0.9,\n'
            f'      "relevance": 0.9,\n'
            f'      "completeness": 0.9,\n'
            f'      "instruction_following": 0.9,\n'
            f'      "reason": "Brief justification"\n'
            f'    }}'
        )
        schema_hint_lines.append(hint)

    prompt_payload = JUDGE_PROMPT_TEMPLATE.format(
        prompt=prompt,
        candidate_blocks="\n\n".join(blocks),
        schema_hints=",\n".join(schema_hint_lines),
    )

    try:
        raw_judge_output, active_judge_id = await call_llm(judge_spec, prompt_payload)
        parsed_evals = _parse_judge_json(raw_judge_output)
    except Exception as exc:  # noqa: BLE001
        logger.error("Blind judge execution failed: %s", exc)
        return []

    # 2. Unblind and map scores back to real model_run_ids in application code
    results: list[dict[str, Any]] = []
    metrics = ["correctness", "relevance", "completeness", "instruction_following"]

    for label, contender in label_to_contender.items():
        run_id = contender.get("run_id") or contender.get("id") or ""
        model_id = contender.get("model_id", "")
        eval_data = parsed_evals.get(label, {})
        reason = eval_data.get("reason", "No justification provided.")

        for metric in metrics:
            score = float(eval_data.get(metric, 0.0))
            # Clamp between 0.0 and 1.0
            score = max(0.0, min(1.0, score))
            results.append(
                {
                    "model_run_id": run_id,
                    "model_id": model_id,
                    "metric": metric,
                    "score": score,
                    "judge_model": active_judge_id,
                    "reason": reason,
                }
            )

    return results
