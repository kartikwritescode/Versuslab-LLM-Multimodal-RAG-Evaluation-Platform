"""add context_hash, citations, and tsvector generated column

Revision ID: 003_context_hash_and_citations
Revises: 002_pgvector_and_documents
Create Date: 2026-09-22 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_context_hash_and_citations"
down_revision: str | None = "002_pgvector_and_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add full-text search generated column and GIN index to document_chunks
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED;"
    )
    op.execute("CREATE INDEX ix_document_chunks_tsv ON document_chunks USING GIN (tsv);")

    # 2. Add shared_context_hash to races table
    op.add_column(
        "races",
        sa.Column("shared_context_hash", sa.String(length=64), nullable=True),
    )

    # 3. Add context_hash, citations_valid, and invalid_citations to model_runs table
    op.add_column(
        "model_runs",
        sa.Column("context_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "model_runs",
        sa.Column("citations_valid", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "model_runs",
        sa.Column("invalid_citations", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("model_runs", "invalid_citations")
    op.drop_column("model_runs", "citations_valid")
    op.drop_column("model_runs", "context_hash")
    op.drop_column("races", "shared_context_hash")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_tsv;")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS tsv;")
