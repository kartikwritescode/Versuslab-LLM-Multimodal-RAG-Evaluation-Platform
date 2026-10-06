"""Aggregates multi-model experiment results into comparison metrics and Pareto tradeoff points."""
from typing import Any


def aggregate_experiment_results(
    experiment: Any,
    experiment_runs: list[Any],
) -> dict[str, Any]:
    """Computes per-model aggregates without collapsing into a single ranking score.

    Per AGENTS.md design rules, users must be able to inspect real tradeoffs
    between latency, throughput, cost, and distinct quality metrics.
    """
    models_configured = list(experiment.models)
    model_stats_map: dict[str, dict[str, Any]] = {}

    for model_id in models_configured:
        model_stats_map[model_id] = {
            "model_id": model_id,
            "runs_count": 0,
            "successful_runs": 0,
            "error_count": 0,
            "timeout_count": 0,
            "ttft_ms_list": [],
            "latency_ms_list": [],
            "throughput_list": [],
            "input_tokens_list": [],
            "output_tokens_list": [],
            "input_cost_total": 0.0,
            "output_cost_total": 0.0,
            "cost_total": 0.0,
            "metric_scores": {},  # metric_name -> list of floats
        }

    case_breakdowns: list[dict[str, Any]] = []

    for exp_run in experiment_runs:
        case = exp_run.benchmark_case
        race = exp_run.race
        if not race:
            continue

        case_item = {
            "case_id": case.id if case else "",
            "category": case.category if case else "general",
            "question": case.question if case else race.prompt,
            "expected_answer": case.expected_answer if case else None,
            "race_id": race.id,
            "models": {},
        }

        for run in race.model_runs:
            mid = run.model_id
            if mid not in model_stats_map:
                model_stats_map[mid] = {
                    "model_id": mid,
                    "runs_count": 0,
                    "successful_runs": 0,
                    "error_count": 0,
                    "timeout_count": 0,
                    "ttft_ms_list": [],
                    "latency_ms_list": [],
                    "throughput_list": [],
                    "input_tokens_list": [],
                    "output_tokens_list": [],
                    "input_cost_total": 0.0,
                    "output_cost_total": 0.0,
                    "cost_total": 0.0,
                    "metric_scores": {},
                }

            stats = model_stats_map[mid]
            stats["runs_count"] += 1

            if run.status in ("done", "completed"):
                stats["successful_runs"] += 1
            elif run.status == "error":
                stats["error_count"] += 1
            elif run.status == "timeout":
                stats["timeout_count"] += 1

            if run.ttft_ms is not None:
                stats["ttft_ms_list"].append(run.ttft_ms)

            if run.latency_ms is not None:
                stats["latency_ms_list"].append(run.latency_ms)
                if run.output_tokens and run.latency_ms > 0:
                    tps = (run.output_tokens / (run.latency_ms / 1000.0))
                    stats["throughput_list"].append(tps)

            if run.input_tokens is not None:
                stats["input_tokens_list"].append(run.input_tokens)
            if run.output_tokens is not None:
                stats["output_tokens_list"].append(run.output_tokens)

            if run.input_cost is not None:
                stats["input_cost_total"] += float(run.input_cost)
            if run.output_cost is not None:
                stats["output_cost_total"] += float(run.output_cost)
            if run.total_cost is not None:
                stats["cost_total"] += float(run.total_cost)

            run_eval_map: dict[str, float] = {}
            for ev in getattr(run, "evaluations", []):
                metric_name = ev.metric
                stats["metric_scores"].setdefault(metric_name, []).append(ev.score)
                run_eval_map[metric_name] = ev.score

            case_item["models"][mid] = {
                "status": run.status,
                "response_text": run.response_text,
                "ttft_ms": run.ttft_ms,
                "latency_ms": run.latency_ms,
                "evaluations": run_eval_map,
            }

        case_breakdowns.append(case_item)

    # Compute averages per model
    models_stats: list[dict[str, Any]] = []
    pareto_points: list[dict[str, Any]] = []

    for model_id, raw in model_stats_map.items():
        count = raw["runs_count"]
        error_rate = round(raw["error_count"] / count, 4) if count > 0 else 0.0
        timeout_rate = round(raw["timeout_count"] / count, 4) if count > 0 else 0.0

        mean_ttft = (
            round(sum(raw["ttft_ms_list"]) / len(raw["ttft_ms_list"]), 2)
            if raw["ttft_ms_list"]
            else None
        )
        mean_latency = (
            round(sum(raw["latency_ms_list"]) / len(raw["latency_ms_list"]), 2)
            if raw["latency_ms_list"]
            else None
        )
        mean_tps = (
            round(sum(raw["throughput_list"]) / len(raw["throughput_list"]), 2)
            if raw["throughput_list"]
            else None
        )

        mean_metrics: dict[str, float] = {}
        for mname, scores in raw["metric_scores"].items():
            if scores:
                mean_metrics[mname] = round(sum(scores) / len(scores), 4)

        stat_record = {
            "model_id": model_id,
            "runs_count": count,
            "successful_runs": raw["successful_runs"],
            "error_rate": error_rate,
            "timeout_rate": timeout_rate,
            "mean_ttft_ms": mean_ttft,
            "mean_latency_ms": mean_latency,
            "mean_tokens_per_sec": mean_tps,
            "total_input_tokens": sum(raw["input_tokens_list"]),
            "total_output_tokens": sum(raw["output_tokens_list"]),
            "total_cost": round(raw["cost_total"], 6),
            "mean_metrics": mean_metrics,
        }
        models_stats.append(stat_record)

        # Determine representative quality score for Pareto visualization
        # Prioritize exact_match if available, then correctness, then faithfulness
        primary_quality = (
            mean_metrics.get("exact_match")
            if "exact_match" in mean_metrics
            else mean_metrics.get("correctness")
            if "correctness" in mean_metrics
            else mean_metrics.get("faithfulness")
            if "faithfulness" in mean_metrics
            else 0.0
        )

        pareto_points.append(
            {
                "model_id": model_id,
                "quality_score": primary_quality,
                "total_cost": round(raw["cost_total"], 6),
                "mean_latency_ms": mean_latency or 0.0,
            }
        )

    dataset = getattr(experiment, "dataset", None)

    return {
        "experiment_id": experiment.id,
        "name": experiment.name,
        "dataset_id": experiment.dataset_id,
        "dataset_name": dataset.name if dataset else "Unknown",
        "dataset_version": dataset.version if dataset else 1,
        "status": experiment.status,
        "git_commit": experiment.git_commit,
        "include_llm_judge": experiment.include_llm_judge,
        "created_at": experiment.created_at.isoformat() if experiment.created_at else None,
        "finished_at": experiment.finished_at.isoformat() if experiment.finished_at else None,
        "total_cases": len(case_breakdowns),
        "models_stats": models_stats,
        "pareto_points": pareto_points,
        "cases": case_breakdowns,
    }
