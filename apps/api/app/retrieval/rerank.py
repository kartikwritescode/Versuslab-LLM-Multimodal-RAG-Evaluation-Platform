import asyncio
import logging
import tempfile
from typing import Protocol

from app.core.config import settings
from app.db.models import DocumentChunk

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    """Protocol for reranking candidate document chunks against a query."""

    def rerank(
        self,
        query: str,
        chunks: list[DocumentChunk],
        top_k: int,
    ) -> list[DocumentChunk]:
        """Scores and reorders candidate chunks, returning the top_k chunks."""
        ...


class MockReranker:
    """Deterministic mock reranker for offline testing without external weights or network calls.

    Adheres strictly to AGENTS.md rule: tests must never call paid APIs or real network.
    """

    def rerank(
        self,
        query: str,
        chunks: list[DocumentChunk],
        top_k: int,
    ) -> list[DocumentChunk]:
        if not chunks:
            return []

        q_terms = [t.lower() for t in query.split() if len(t) > 1]

        def rank_key(c: DocumentChunk) -> tuple[int, int]:
            # Count query term matches in text, break ties with chunk index
            matches = sum(1 for term in q_terms if term in c.text.lower())
            return (matches, -c.chunk_index)

        sorted_chunks = sorted(chunks, key=rank_key, reverse=True)
        return sorted_chunks[:top_k]


class FlashRankReranker:
    """Cross-encoder reranker utilizing FlashRank (ONNX runtime on CPU).

    Note on Rule 2 (Async Everywhere):
    Reranking inference is CPU-bound. Invocations must be scheduled using
    `rerank_chunks(..., asyncio.to_thread)` to avoid blocking the FastAPI event loop.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.reranker_model
        self._ranker = None

    def _get_ranker(self):
        if self._ranker is None:
            from flashrank import Ranker

            cache_dir = tempfile.gettempdir()
            self._ranker = Ranker(model_name=self.model_name, cache_dir=cache_dir)
        return self._ranker

    def rerank(
        self,
        query: str,
        chunks: list[DocumentChunk],
        top_k: int,
    ) -> list[DocumentChunk]:
        if not chunks:
            return []
        if len(chunks) <= 1:
            return chunks[:top_k]

        from flashrank import RerankRequest

        ranker = self._get_ranker()
        passages = [{"id": c.id, "text": c.text} for c in chunks]
        request = RerankRequest(query=query, passages=passages)
        results = ranker.rerank(request)

        # Map ranked results back to original DocumentChunk instances
        chunk_map = {c.id: c for c in chunks}
        reranked: list[DocumentChunk] = []
        for item in results:
            cid = item.get("id")
            if cid in chunk_map:
                reranked.append(chunk_map[cid])

        # Preserve any unranked items at the end as fallback
        for c in chunks:
            if c not in reranked:
                reranked.append(c)

        return reranked[:top_k]


async def rerank_chunks(
    reranker: Reranker,
    query: str,
    chunks: list[DocumentChunk],
    top_k: int,
) -> list[DocumentChunk]:
    """Asynchronously runs CPU-bound cross-encoder reranking in a worker thread."""
    if not chunks:
        return []
    return await asyncio.to_thread(reranker.rerank, query, chunks, top_k)


_RERANKER: Reranker | None = None


def get_reranker() -> Reranker:
    """Returns the globally configured reranker (default: FlashRankReranker)."""
    global _RERANKER
    if _RERANKER is None:
        _RERANKER = FlashRankReranker()
    return _RERANKER


def set_reranker(reranker: Reranker | None) -> None:
    """Overrides the global reranker (useful for tests with MockReranker)."""
    global _RERANKER
    _RERANKER = reranker
