import hashlib
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.rate_limit import create_rate_limiter
from app.db.base import get_session
from app.db.models import Document, DocumentChunk
from app.providers.embeddings import get_embedding_provider
from app.retrieval.chunking import chunk_text

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".txt", ".md"}
ALLOWED_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "application/octet-stream",
}

document_rate_limiter = create_rate_limiter(settings.document_rate_limit_per_minute)


@router.post("", dependencies=[Depends(document_rate_limiter)])
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Uploads and ingests a text/markdown document.

    Computes SHA-256 content hash for idempotent re-upload detection.
    Chunks text by paragraph and embeds using the configured embedding provider.
    Enforces file size limit, MIME-type validation, and rate limits.
    """
    filename = file.filename or "document.txt"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Only .txt and .md files are supported.",
        )

    # Basic MIME-type validation
    if file.content_type and file.content_type.lower() not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported MIME type '{file.content_type}'. Only plain text and markdown are allowed.",
        )

    content_bytes = await file.read()
    if not content_bytes.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    # Request size limit enforcement
    if len(content_bytes) > settings.max_upload_size_bytes:
        max_mb = settings.max_upload_size_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {max_mb}MB.",
        )

    # Reject binary files disguised as text (presence of null bytes)
    if b"\x00" in content_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Binary file detected. Only valid UTF-8 text documents are supported.",
        )

    # Compute SHA-256 for idempotency check
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    # Check if document already exists
    existing_stmt = (
        select(Document)
        .options(selectinload(Document.chunks))
        .where(Document.content_hash == content_hash)
    )
    existing_doc = await session.scalar(existing_stmt)
    if existing_doc is not None:
        return {
            "id": existing_doc.id,
            "filename": existing_doc.filename,
            "content_hash": existing_doc.content_hash,
            "mime_type": existing_doc.mime_type,
            "chunk_count": len(existing_doc.chunks),
            "created_at": existing_doc.created_at.isoformat() if existing_doc.created_at else None,
            "deduplicated": True,
        }

    # Decode and chunk
    text = content_bytes.decode("utf-8", errors="replace")
    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not extract text chunks from file.")

    # Batch embed all chunks
    provider = get_embedding_provider()
    embeddings = await provider.embed_documents(chunks)

    doc_id = uuid.uuid4().hex
    doc = Document(
        id=doc_id,
        filename=filename,
        content_hash=content_hash,
        mime_type=file.content_type or "text/plain",
        created_at=datetime.now(timezone.utc),
    )
    session.add(doc)

    for idx, (chunk_str, emb) in enumerate(zip(chunks, embeddings, strict=True)):
        chunk_rec = DocumentChunk(
            id=uuid.uuid4().hex,
            document_id=doc_id,
            chunk_index=idx,
            text=chunk_str,
            embedding=emb,
        )
        session.add(chunk_rec)

    await session.commit()

    return {
        "id": doc.id,
        "filename": doc.filename,
        "content_hash": doc.content_hash,
        "mime_type": doc.mime_type,
        "chunk_count": len(chunks),
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "deduplicated": False,
    }


@router.get("")
async def list_documents(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict[str, Any]]:
    """Returns a list of all ingested documents ordered newest first."""
    stmt = (
        select(Document)
        .options(selectinload(Document.chunks))
        .order_by(desc(Document.created_at))
    )
    result = await session.scalars(stmt)
    docs = result.all()

    return [
        {
            "id": d.id,
            "filename": d.filename,
            "content_hash": d.content_hash,
            "mime_type": d.mime_type,
            "chunk_count": len(d.chunks),
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Returns a specific document with its ordered chunk snippets for UI inspection."""
    stmt = (
        select(Document)
        .options(selectinload(Document.chunks))
        .where(Document.id == document_id)
    )
    doc = await session.scalar(stmt)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "content_hash": doc.content_hash,
        "mime_type": doc.mime_type,
        "chunk_count": len(doc.chunks),
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "chunks": [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "text": c.text,
            }
            for c in sorted(doc.chunks, key=lambda x: x.chunk_index)
        ],
    }
