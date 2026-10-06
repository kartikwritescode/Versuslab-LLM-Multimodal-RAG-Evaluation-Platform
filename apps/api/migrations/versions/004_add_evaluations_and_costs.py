"""add evaluations table and cost columns to model_runs

Revision ID: 004_evaluations_and_costs
Revises: 003_context_hash_and_citations
Create Date: 2026-09-22 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_evaluations_and_costs"
down_revision: str | None = "003_context_hash_and_citations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add optional attached document_id to races
    op.add_column(
        "races",
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
    )

    # 2. Add cost tracking columns to model_runs table (stored as exact Numeric(10, 6))
    op.add_column(
        "model_runs",
        sa.Column("input_cost", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.add_column(
        "model_runs",
        sa.Column("output_cost", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.add_column(
        "model_runs",
        sa.Column("total_cost", sa.Numeric(precision=10, scale=6), nullable=True),
    )

    # 2. Create evaluations table
    op.create_table(
        "evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_run_id", sa.String(length=36), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("judge_model", sa.String(length=128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluations_model_run_id",
        "evaluations",
        ["model_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_evaluations_model_run_id", table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_column("model_runs", "total_cost")
    op.drop_column("model_runs", "output_cost")
    op.drop_column("model_runs", "input_cost")
    op.drop_column("races", "document_id")
