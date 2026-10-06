"""VersusLab Evaluation Package."""
from app.evaluation.citation_check import verify_citations
from app.evaluation.citation_faithfulness import evaluate_citation_faithfulness
from app.evaluation.cost import calculate_costs, get_model_rates
from app.evaluation.deterministic import exact_match, json_schema_validity, regex_match
from app.evaluation.judge import run_blind_judge
from app.evaluation.retrieval_metrics import (
    evaluate_dataset,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

__all__ = [
    "calculate_costs",
    "evaluate_citation_faithfulness",
    "evaluate_dataset",
    "exact_match",
    "get_model_rates",
    "json_schema_validity",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "regex_match",
    "run_blind_judge",
    "verify_citations",
]
