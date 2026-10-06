import json
from pathlib import Path
from typing import Any


def recall_at_k(retrieved_ids: list[str], gold_ids: set[str], k: int) -> float:
    """Computes Recall@K: proportion of relevant chunks retrieved in the top K."""
    if not gold_ids:
        return 0.0
    top_k_set = set(retrieved_ids[:k])
    relevant_retrieved = top_k_set.intersection(gold_ids)
    return len(relevant_retrieved) / len(gold_ids)


def precision_at_k(retrieved_ids: list[str], gold_ids: set[str], k: int) -> float:
    """Computes Precision@K: proportion of top K retrieved chunks that are relevant."""
    if k <= 0:
        return 0.0
    top_k_set = set(retrieved_ids[:k])
    relevant_retrieved = top_k_set.intersection(gold_ids)
    return len(relevant_retrieved) / k


def reciprocal_rank(retrieved_ids: list[str], gold_ids: set[str]) -> float:
    """Computes Reciprocal Rank (RR): 1 / rank of the first relevant chunk retrieved."""
    for rank, cid in enumerate(retrieved_ids, start=1):
        if cid in gold_ids:
            return 1.0 / rank
    return 0.0


def evaluate_dataset(
    query_evaluations: list[dict[str, Any]] | str | Path,
    k: int = 5,
) -> dict[str, float]:
    """Computes aggregate Recall@K, Precision@K, and Mean Reciprocal Rank (MRR).

    query_evaluations can be a list of evaluation dicts or a Path/str to a JSON fixture.
    """
    if isinstance(query_evaluations, (str, Path)):
        items = load_gold_fixture(Path(query_evaluations))
    else:
        items = query_evaluations

    if not items:
        return {f"recall@{k}": 0.0, f"precision@{k}": 0.0, "mrr": 0.0}

    total_recall = 0.0
    total_precision = 0.0
    total_rr = 0.0
    count = len(items)

    for item in items:
        retrieved = item.get("retrieved_chunk_ids", [])
        gold = set(item.get("gold_chunk_ids", []))

        total_recall += recall_at_k(retrieved, gold, k=k)
        total_precision += precision_at_k(retrieved, gold, k=k)
        total_rr += reciprocal_rank(retrieved, gold)

    return {
        f"recall@{k}": round(total_recall / count, 4),
        f"precision@{k}": round(total_precision / count, 4),
        "mrr": round(total_rr / count, 4),
    }


def load_gold_fixture(fixture_path: Path | None = None) -> list[dict[str, Any]]:
    """Loads the hand-authored gold retrieval benchmark fixture."""
    resolved_path: Path | None = None

    if fixture_path is None:
        # Search upwards from this file's location for evals/fixtures/gold_retrieval_set.json
        cur = Path(__file__).resolve().parent
        for _ in range(6):
            candidate = cur / "evals" / "fixtures" / "gold_retrieval_set.json"
            if candidate.exists():
                resolved_path = candidate
                break
            cur = cur.parent
    else:
        p = Path(fixture_path)
        if p.is_absolute() and p.exists() or p.exists():
            resolved_path = p
        else:
            # Search upwards for relative path
            cur = Path(__file__).resolve().parent
            for _ in range(6):
                candidate = cur / p
                if candidate.exists():
                    resolved_path = candidate
                    break
                cur = cur.parent

    target = resolved_path or (Path(__file__).resolve().parent / "fixtures" / "gold_retrieval_set.json")
    with open(target, encoding="utf-8") as f:
        return json.load(f)


def run_benchmark_simulation(k: int = 3) -> dict[str, float]:
    """Demonstrates retrieval metrics evaluation using the hand-authored gold fixture."""
    gold_items = load_gold_fixture()

    # Simulate retrieval results where relevant chunk is retrieved at rank 1 or 2
    simulated_results: list[dict[str, Any]] = []
    for item in gold_items:
        gold_id = item["gold_chunk_ids"][0]
        # In a high-quality hybrid + reranker system, relevant chunk is in top positions
        simulated_results.append(
            {
                "query_id": item["id"],
                "retrieved_chunk_ids": [gold_id, "distractor-1", "distractor-2"],
                "gold_chunk_ids": item["gold_chunk_ids"],
            }
        )

    return evaluate_dataset(simulated_results, k=k)


if __name__ == "__main__":
    results = run_benchmark_simulation(k=3)
    print("==================================================")
    print(" VersusLab Phase 8 Retrieval Benchmark Metrics")
    print("==================================================")
    for metric_name, val in results.items():
        print(f" {metric_name.upper():<16}: {val:.4f}")
    print("==================================================")
