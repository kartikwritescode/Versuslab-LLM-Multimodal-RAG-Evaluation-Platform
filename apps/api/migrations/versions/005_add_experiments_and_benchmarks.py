"""add benchmark datasets, benchmark cases, experiments, and experiment_runs

Revision ID: 005_experiments_and_benchmarks
Revises: 004_evaluations_and_costs
Create Date: 2026-09-22 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_experiments_and_benchmarks"
down_revision: str | None = "004_evaluations_and_costs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create benchmark_datasets table (immutable, versioned)
    op.create_table(
        "benchmark_datasets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_benchmark_datasets_name", "benchmark_datasets", ["name"])

    # 2. Create benchmark_cases table
    op.create_table(
        "benchmark_cases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(length=36),
            sa.ForeignKey("benchmark_datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=True),
        sa.Column("gold_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="general"),
    )
    op.create_index("ix_benchmark_cases_dataset_id", "benchmark_cases", ["dataset_id"])
    op.create_index("ix_benchmark_cases_category", "benchmark_cases", ["category"])

    # 3. Create experiments table
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "dataset_id",
            sa.String(length=36),
            sa.ForeignKey("benchmark_datasets.id"),
            nullable=False,
        ),
        sa.Column("models", sa.JSON(), nullable=False),
        sa.Column("git_commit", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("include_llm_judge", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_experiments_dataset_id", "experiments", ["dataset_id"])

    # 4. Create experiment_runs table (join table back to races)
    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "experiment_id",
            sa.String(length=36),
            sa.ForeignKey("experiments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "benchmark_case_id",
            sa.String(length=36),
            sa.ForeignKey("benchmark_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "race_id",
            sa.String(length=32),
            sa.ForeignKey("races.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_experiment_runs_experiment_id", "experiment_runs", ["experiment_id"])
    op.create_index("ix_experiment_runs_benchmark_case_id", "experiment_runs", ["benchmark_case_id"])
    op.create_index("ix_experiment_runs_race_id", "experiment_runs", ["race_id"])


def downgrade() -> None:
    op.drop_table("experiment_runs")
    op.drop_table("experiments")
    op.drop_table("benchmark_cases")
    op.drop_table("benchmark_datasets")
