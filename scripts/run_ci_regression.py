"""CI Regression Check Script.

Runs a fixed subset of the benchmark dataset against MockProvider to verify
that no code changes have degraded deterministic evaluation quality or introduced
task failures or event loop drops.

Usage:
    python scripts/run_ci_regression.py [--update-baseline]
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add apps/api to path so imports resolve
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.evaluation.deterministic import exact_match
from app.providers.mock import MockProvider
from app.providers.types import Message, ModelRequest
from app.race.coordinator import RaceTarget, run_race

BASELINE_FILE = REPO_ROOT / "evals" / "baselines" / "ci_baseline.json"
DATASET_FILE = REPO_ROOT / "evals" / "datasets" / "seed_benchmark.json"


def load_dataset_cases() -> list[dict]:
    if not DATASET_FILE.exists():
        raise FileNotFoundError(f"Seed benchmark not found: {DATASET_FILE}")
    with open(DATASET_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])[:6]


async def execute_ci_benchmark() -> dict[str, float]:
    """Runs a 6-case subset of seed benchmark against deterministic mock model."""
    cases = load_dataset_cases()

    # Map expected answers to prompts so MockProvider produces exact matches
    canned_answers: dict[str, str] = {}
    for c in cases:
        if c.get("expected_answer"):
            canned_answers[c["question"]] = c["expected_answer"]

    # Zero delay for rapid CI execution
    ci_mock_provider = MockProvider(
        first_token_delay=0.01,
        tokens_per_second=200.0,
        canned_responses=canned_answers,
    )
    target = RaceTarget(
        model_id="mock:mock-1",
        provider=ci_mock_provider,
        model="mock-1",
    )

    exact_matches: list[float] = []
    errors = 0
    timeouts = 0
    total_runs = len(cases)

    for case in cases:
        prompt = case["question"]
        expected = case.get("expected_answer", "")

        template = ModelRequest(
            model="mock-1",
            messages=[Message(role="user", content=prompt)],
            temperature=0.0,
        )

        accumulated_text: list[str] = []
        had_error = False

        try:
            async for event in run_race("ci-race-test", [target], template):
                if event.type == "model.delta" and event.text:
                    accumulated_text.append(event.text)
                elif event.type == "model.error":
                    errors += 1
                    had_error = True
                elif event.type == "model.timeout":
                    timeouts += 1
                    had_error = True

            final_text = "".join(accumulated_text).strip()
            if not had_error and expected:
                score = exact_match(final_text, expected)
                exact_matches.append(score)
            elif had_error:
                exact_matches.append(0.0)

        except Exception as exc:  # noqa: BLE001
            print(f"Exception during CI race execution: {exc}")
            errors += 1
            exact_matches.append(0.0)

    mean_em = sum(exact_matches) / len(exact_matches) if exact_matches else 0.0
    err_rate = errors / total_runs if total_runs > 0 else 0.0
    tout_rate = timeouts / total_runs if total_runs > 0 else 0.0

    return {
        "exact_match": round(mean_em, 4),
        "error_rate": round(err_rate, 4),
        "timeout_rate": round(tout_rate, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run VersusLab CI Regression Quality Gate")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Update committed baseline file with measured metrics",
    )
    args = parser.parse_args()

    print("==================================================")
    print(" Running VersusLab CI Regression Suite")
    print("==================================================")

    measured = asyncio.run(execute_ci_benchmark())

    if not BASELINE_FILE.exists():
        print(f"Baseline file missing at {BASELINE_FILE}. Creating initial baseline.")
        baseline_data = {
            "dataset_name": "VersusLab Core Seed Benchmark",
            "dataset_version": 1,
            "model": "mock:mock-1",
            "metrics": measured,
            "tolerance": 0.0,
        }
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(baseline_data, f, indent=2)
        print("Initial baseline committed. CI check PASSED.")
        sys.exit(0)

    with open(BASELINE_FILE, encoding="utf-8") as f:
        baseline_data = json.load(f)

    if args.update_baseline:
        baseline_data["metrics"] = measured
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(baseline_data, f, indent=2)
        print("Updated baseline metrics in evals/baselines/ci_baseline.json:")
        print(json.dumps(measured, indent=2))
        sys.exit(0)

    target_metrics = baseline_data.get("metrics", {})
    tolerance = float(baseline_data.get("tolerance", 0.0))

    passed = True
    print(f"{'Metric':<16} | {'Measured':<10} | {'Baseline':<10} | {'Status'}")
    print("-" * 52)

    for metric, base_val in target_metrics.items():
        meas_val = measured.get(metric, 0.0)

        if metric in ("error_rate", "timeout_rate"):
            # Lower is better: measured must be <= baseline + tolerance
            ok = meas_val <= (base_val + tolerance)
        else:
            # Higher is better: measured must be >= baseline - tolerance
            ok = meas_val >= (base_val - tolerance)

        status_str = "PASS" if ok else "FAIL (REGRESSION)"
        if not ok:
            passed = False

        print(f"{metric:<16} | {meas_val:<10.4f} | {base_val:<10.4f} | {status_str}")

    print("==================================================")
    if passed:
        print(" CI Regression Gate: PASSED (Quality sustained)")
        print("==================================================")
        sys.exit(0)
    else:
        print(" CI Regression Gate: FAILED (Quality dropped below baseline)")
        print(" If this change was intentional, update baseline with --update-baseline")
        print("==================================================")
        sys.exit(1)


if __name__ == "__main__":
    main()
