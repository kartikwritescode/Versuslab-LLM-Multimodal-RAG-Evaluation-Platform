import prometheus_client
from fastapi import Response

# 1. Race execution counters
RACES_TOTAL = prometheus_client.Counter(
    "versuslab_races_total",
    "Total number of multi-model races initiated in VersusLab",
    ["status"],  # e.g. started, completed, cancelled, failed
)

# 2. Contender model request counters
MODEL_REQUESTS_TOTAL = prometheus_client.Counter(
    "versuslab_model_requests_total",
    "Total contender model requests dispatched by the race coordinator",
    ["provider", "model", "status"],  # status: completed, error, timeout, cancelled
)

# 3. Time To First Token (TTFT) histogram
MODEL_TTFT_SECONDS = prometheus_client.Histogram(
    "versuslab_model_ttft_seconds",
    "Distribution of time to first token (TTFT) in seconds per provider and model",
    ["provider", "model"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# 4. Total Model Latency histogram
MODEL_LATENCY_SECONDS = prometheus_client.Histogram(
    "versuslab_model_latency_seconds",
    "Distribution of total streaming completion latency in seconds per provider and model",
    ["provider", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0],
)

# 5. RAG Retrieval & Reranking Latency histogram
RETRIEVAL_LATENCY_SECONDS = prometheus_client.Histogram(
    "versuslab_retrieval_latency_seconds",
    "Distribution of hybrid retrieval and reranking duration in seconds",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)


def get_metrics_response() -> Response:
    """Generates a text/plain Prometheus exposition response."""
    return Response(
        content=prometheus_client.generate_latest(),
        media_type=prometheus_client.CONTENT_TYPE_LATEST,
    )
