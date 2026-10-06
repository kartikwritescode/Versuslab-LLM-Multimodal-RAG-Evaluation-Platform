from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk
from app.providers.embeddings import EmbeddingProvider


async def retrieve_top_k(
    session: AsyncSession,
    document_id: str,
    query: str,
    embedding_provider: EmbeddingProvider,
    top_k: int = 5,
) -> list[DocumentChunk]:
    """Retrieves the top-K most similar document chunks using pgvector cosine distance."""
    query_vector = await embedding_provider.embed_query(query)

    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
        .limit(top_k)
    )
    result = await session.scalars(stmt)
    return list(result.all())


def format_rag_context(chunks: list[DocumentChunk]) -> str:
    """Formats retrieved chunks into the canonical system prompt context string.

    This format is deterministic and identical for all contenders in a race.
    """
    if not chunks:
        return (
            "The user attached a document, but no matching context was found. "
            "Answer to the best of your general knowledge."
        )

    chunk_blocks = [
        f"[Chunk {idx + 1}]\n{chunk.text.strip()}"
        for idx, chunk in enumerate(chunks)
    ]
    formatted_chunks = "\n\n".join(chunk_blocks)

    return (
        "The following retrieved document context is provided to assist your answer:\n"
        "---\n"
        f"{formatted_chunks}\n"
        "---\n"
        "Answer the user's prompt using the retrieved document context above. "
        "If the context does not contain enough information to answer, state so clearly."
    )
