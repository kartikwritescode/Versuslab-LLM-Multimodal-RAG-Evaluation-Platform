import logging

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import DocumentChunk
from app.providers.embeddings import EmbeddingProvider, get_embedding_provider
from app.retrieval.rerank import Reranker, get_reranker, rerank_chunks

logger = logging.getLogger(__name__)


async def vector_search(
    session: AsyncSession,
    document_id: str,
    query: str,
    embedding_provider: EmbeddingProvider,
    limit: int = 20,
) -> list[DocumentChunk]:
    """Retrieves chunks by semantic similarity using pgvector cosine distance (<=>)."""
    try:
        query_vector = await embedding_provider.embed_query(query)
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        result = await session.scalars(stmt)
        return list(result.all())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector search failed for document %s: %s", document_id, exc)
        return []


async def lexical_search(
    session: AsyncSession,
    document_id: str,
    query: str,
    limit: int = 20,
) -> list[DocumentChunk]:
    """Retrieves chunks by lexical relevance using PostgreSQL 17 FTS (websearch_to_tsquery and ts_rank_cd)."""
    if not query.strip():
        return []

    try:
        tsquery = func.websearch_to_tsquery("english", query)
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.tsv.op("@@")(tsquery),
            )
            .order_by(desc(func.ts_rank_cd(DocumentChunk.tsv, tsquery)))
            .limit(limit)
        )
        result = await session.scalars(stmt)
        return list(result.all())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lexical search failed for document %s: %s", document_id, exc)
        return []


def reciprocal_rank_fusion(
    vector_results: list[DocumentChunk],
    lexical_results: list[DocumentChunk],
    k: int = 60,
) -> list[DocumentChunk]:
    """Combines vector and lexical search rankings using Reciprocal Rank Fusion (RRF).

    Formula:
        RRF_Score(d) = sum(1.0 / (k + rank_m(d))) for m in {vector, lexical}
    where rank_m(d) is 1-based.
    """
    scores: dict[str, float] = {}
    chunk_map: dict[str, DocumentChunk] = {}

    for rank, chunk in enumerate(vector_results, start=1):
        scores[chunk.id] = scores.get(chunk.id, 0.0) + (1.0 / (k + rank))
        chunk_map[chunk.id] = chunk

    for rank, chunk in enumerate(lexical_results, start=1):
        scores[chunk.id] = scores.get(chunk.id, 0.0) + (1.0 / (k + rank))
        chunk_map[chunk.id] = chunk

    # Sort descending by fused RRF score
    sorted_chunk_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
    return [chunk_map[cid] for cid in sorted_chunk_ids]


async def hybrid_retrieve(
    session: AsyncSession,
    document_id: str,
    query: str,
    embedding_provider: EmbeddingProvider | None = None,
    reranker: Reranker | None = None,
    top_k: int | None = None,
    fetch_k: int | None = None,
) -> list[DocumentChunk]:
    """Executes full hybrid retrieval pipeline:

    1. Concurrent vector search (pgvector) + lexical search (PostgreSQL 17 tsvector).
    2. Reciprocal Rank Fusion (RRF) combining both candidate sets.
    3. Cross-encoder reranking (via asyncio.to_thread).
    4. Top-K truncation.
    """
    embed_prov = embedding_provider or get_embedding_provider()
    ranker = reranker or get_reranker()
    k_fetch = fetch_k or settings.hybrid_fetch_k
    k_final = top_k or settings.rag_top_k
    rrf_smoothing = settings.rrf_k

    # Retrieve candidates from both sources
    vector_candidates = await vector_search(
        session=session,
        document_id=document_id,
        query=query,
        embedding_provider=embed_prov,
        limit=k_fetch,
    )

    lexical_candidates = await lexical_search(
        session=session,
        document_id=document_id,
        query=query,
        limit=k_fetch,
    )

    # Fuse candidate lists with RRF
    fused_candidates = reciprocal_rank_fusion(
        vector_results=vector_candidates,
        lexical_results=lexical_candidates,
        k=rrf_smoothing,
    )

    if not fused_candidates:
        return []

    # Cross-encoder reranking (CPU-bound, scheduled on thread pool)
    final_chunks = await rerank_chunks(
        reranker=ranker,
        query=query,
        chunks=fused_candidates,
        top_k=k_final,
    )

    return final_chunks
