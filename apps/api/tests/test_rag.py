from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.base import get_session
from app.db.models import Document, DocumentChunk
from app.main import app
from app.providers.embeddings import MockEmbeddingProvider, set_embedding_provider
from app.retrieval.basic import format_rag_context
from app.retrieval.chunking import chunk_text


@pytest.fixture(autouse=True)
def use_mock_embeddings():
    """Ensure all tests use the deterministic MockEmbeddingProvider."""
    provider = MockEmbeddingProvider(dimensions=768)
    set_embedding_provider(provider)
    yield provider
    set_embedding_provider(None)


def test_chunking_empty_and_whitespace():
    assert chunk_text("") == []
    assert chunk_text("   \n\n   ") == []


def test_chunking_small_paragraphs_merge():
    text = "Paragraph 1 is short.\n\nParagraph 2 is short.\n\nParagraph 3 is short."
    chunks = chunk_text(text, max_chunk_chars=500)
    # Under 500 characters, all 3 short paragraphs merge into a single chunk
    assert len(chunks) == 1
    assert "Paragraph 1" in chunks[0]
    assert "Paragraph 3" in chunks[0]


def test_chunking_large_text_splits_cleanly():
    para1 = "A" * 400
    para2 = "B" * 400
    para3 = "C" * 400
    text = f"{para1}\n\n{para2}\n\n{para3}"
    chunks = chunk_text(text, max_chunk_chars=500)
    assert len(chunks) == 3
    assert chunks[0] == para1
    assert chunks[1] == para2
    assert chunks[2] == para3


def test_chunking_oversized_single_paragraph_splits_on_sentences():
    sentence1 = "This is sentence one with a full stop."
    sentence2 = "This is sentence two with a question mark?"
    sentence3 = "This is sentence three with an exclamation mark!"
    para = f"{sentence1} {sentence2} {sentence3}"
    chunks = chunk_text(para, max_chunk_chars=50)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 60


@pytest.mark.asyncio
async def test_mock_embedding_provider_deterministic():
    provider = MockEmbeddingProvider(dimensions=768)
    vec1 = await provider.embed_query("VersusLab AI Platform")
    vec2 = await provider.embed_query("VersusLab AI Platform")
    assert len(vec1) == 768
    assert vec1 == vec2

    docs = ["Doc one", "Doc two"]
    doc_vecs = await provider.embed_documents(docs)
    assert len(doc_vecs) == 2
    assert len(doc_vecs[0]) == 768


def test_format_rag_context():
    dummy_chunks = [
        DocumentChunk(
            id="c1",
            document_id="d1",
            chunk_index=0,
            text="VersusLab was created for LLM evaluation.",
            embedding=[0.0] * 768,
        ),
        DocumentChunk(
            id="c2",
            document_id="d1",
            chunk_index=1,
            text="Every model streams over one SSE connection.",
            embedding=[0.0] * 768,
        ),
    ]

    formatted = format_rag_context(dummy_chunks)
    assert "[Chunk 1]" in formatted
    assert "[Chunk 2]" in formatted
    assert "VersusLab was created for LLM evaluation." in formatted
    assert "Every model streams over one SSE connection." in formatted
    assert "---" in formatted


@pytest.mark.asyncio
async def test_upload_document_validation():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Reject invalid file extension
        resp = await client.post(
            "/api/documents",
            files={"file": ("test.pdf", b"Fake PDF content", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "Only .txt and .md files are supported" in resp.json()["detail"]

        # 2. Reject empty file
        resp = await client.post(
            "/api/documents",
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert resp.status_code == 400
        assert "Uploaded file is empty" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_document_and_idempotent_deduplication():
    content = b"# VersusLab Overview\n\nA platform for testing multiple LLMs at once."

    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    # First call: not existing in DB
    mock_session.scalar.return_value = None

    app.dependency_overrides[get_session] = lambda: mock_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/documents",
                files={"file": ("overview.md", content, "text/markdown")},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["filename"] == "overview.md"
            assert data["deduplicated"] is False
            assert data["chunk_count"] == 1
            assert "content_hash" in data

            # Second call: simulate existing document with identical content hash
            existing_doc = Document(
                id="existing-doc-123",
                filename="overview.md",
                content_hash=data["content_hash"],
                mime_type="text/markdown",
            )
            existing_doc.chunks = [DocumentChunk(id="c1", document_id="existing-doc-123", chunk_index=0, text="...", embedding=[])]
            mock_session.scalar.return_value = existing_doc

            resp2 = await client.post(
                "/api/documents",
                files={"file": ("overview.md", content, "text/markdown")},
            )
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["id"] == "existing-doc-123"
            assert data2["deduplicated"] is True
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_race_with_attached_document():
    dummy_chunks = [
        DocumentChunk(
            id="c1",
            document_id="doc-99",
            chunk_index=0,
            text="Secret key is XYZ-12345.",
            embedding=[0.0] * 768,
        )
    ]

    with (
        patch("app.api.race.hybrid_retrieve", new_callable=AsyncMock) as mock_retrieve,
        patch("app.api.race.create_race_record", new_callable=AsyncMock),
    ):
        mock_retrieve.return_value = dummy_chunks

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/races",
                json={
                    "prompt": "What is the secret key?",
                    "models": ["mock:mock-1"],
                    "document_id": "doc-99",
                },
            )
            assert resp.status_code == 200
            mock_retrieve.assert_called_once()


@pytest.mark.asyncio
async def test_get_document_detail():
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session

    try:
        doc = Document(
            id="doc-preview-1",
            filename="sample.txt",
            content_hash="abc",
            mime_type="text/plain",
        )
        doc.chunks = [
            DocumentChunk(id="c1", document_id="doc-preview-1", chunk_index=0, text="First chunk text", embedding=[]),
            DocumentChunk(id="c2", document_id="doc-preview-1", chunk_index=1, text="Second chunk text", embedding=[]),
        ]
        mock_session.scalar.return_value = doc

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/documents/doc-preview-1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == "doc-preview-1"
            assert data["chunk_count"] == 2
            assert len(data["chunks"]) == 2
            assert data["chunks"][0]["text"] == "First chunk text"
    finally:
        app.dependency_overrides.pop(get_session, None)
