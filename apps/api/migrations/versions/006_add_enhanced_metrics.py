"""add enhanced performance and quality metrics

Revision ID: 006_enhanced_metrics
Revises: 005_experiments_and_benchmarks
Create Date: 2026-09-23 10:39:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_enhanced_metrics"
down_revision: str | None = "005_experiments_and_benchmarks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add enhanced metrics columns to model_runs table."""
    # Performance metrics
    op.add_column("model_runs", sa.Column("tokens_per_second", sa.Float(), nullable=True))
    op.add_column("model_runs", sa.Column("time_per_output_token", sa.Float(), nullable=True))
    op.add_column("model_runs", sa.Column("input_tokens_per_second", sa.Float(), nullable=True))

    # Cost efficiency metrics
    op.add_column("model_runs", sa.Column("cost_per_1k_tokens", sa.Numeric(10, 6), nullable=True))
    op.add_column("model_runs", sa.Column("cost_per_second", sa.Numeric(10, 6), nullable=True))

    # Response length statistics
    op.add_column("model_runs", sa.Column("response_word_count", sa.Integer(), nullable=True))
    op.add_column("model_runs", sa.Column("response_char_count", sa.Integer(), nullable=True))
    op.add_column("model_runs", sa.Column("response_sentence_count", sa.Integer(), nullable=True))

    # Quality metrics
    op.add_column("model_runs", sa.Column("aggregate_quality_score", sa.Float(), nullable=True))
    op.add_column("model_runs", sa.Column("confidence_score", sa.Float(), nullable=True))
    op.add_column("model_runs", sa.Column("qualifier_count", sa.Integer(), nullable=True))

    # Memory/Context utilization
    op.add_column("model_runs", sa.Column("context_utilization_percent", sa.Float(), nullable=True))
    op.add_column("model_runs", sa.Column("model_max_context", sa.Integer(), nullable=True))

    # Streaming stability metrics
    op.add_column("model_runs", sa.Column("streaming_chunk_count", sa.Integer(), nullable=True))
    op.add_column("model_runs", sa.Column("avg_chunk_size", sa.Float(), nullable=True))

    # Cost vs Quality tradeoff
    op.add_column("model_runs", sa.Column("cost_quality_ratio", sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove enhanced metrics columns from model_runs table."""
    op.drop_column("model_runs", "cost_quality_ratio")
    op.drop_column("model_runs", "avg_chunk_size")
    op.drop_column("model_runs", "streaming_chunk_count")
    op.drop_column("model_runs", "model_max_context")
    op.drop_column("model_runs", "context_utilization_percent")
    op.drop_column("model_runs", "qualifier_count")
    op.drop_column("model_runs", "confidence_score")
    op.drop_column("model_runs", "aggregate_quality_score")
    op.drop_column("model_runs", "response_sentence_count")
    op.drop_column("model_runs", "response_char_count")
    op.drop_column("model_runs", "response_word_count")
    op.drop_column("model_runs", "cost_per_second")
    op.drop_column("model_runs", "cost_per_1k_tokens")
    op.drop_column("model_runs", "input_tokens_per_second")
    op.drop_column("model_runs", "time_per_output_token")
    op.drop_column("model_runs", "tokens_per_second")
