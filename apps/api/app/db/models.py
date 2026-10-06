import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base


class Race(Base):
    __tablename__ = "races"

    # Hex uuid matching coordinator's race_id (e.g. uuid.uuid4().hex)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # sha256 hash of the canonical RAG context shared identically across all contenders
    shared_context_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationship to contender runs with selectin loading for easy single-query serialization
    model_runs: Mapped[list["ModelRun"]] = relationship(
        "ModelRun",
        back_populates="race",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ModelRun.id",
    )


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
    )
    race_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("races.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Context hash stamped from race.shared_context_hash to verify fairness
    context_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Heuristic verification of inline [Sn] citations
    citations_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    invalid_citations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Cost tracking (in dollars, stored as exact Numeric(10, 6))
    input_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    output_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)

    # Performance metrics
    tokens_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_per_output_token: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_tokens_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Cost efficiency metrics
    cost_per_1k_tokens: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    cost_per_second: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)

    # Response length statistics
    response_word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_sentence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Quality metrics
    aggregate_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    qualifier_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Memory/Context utilization
    context_utilization_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_max_context: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Streaming stability metrics
    streaming_chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_chunk_size: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Cost vs Quality tradeoff (quality points per dollar)
    cost_quality_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    race: Mapped["Race"] = relationship("Race", back_populates="model_runs")
    evaluations: Mapped[list["Evaluation"]] = relationship(
        "Evaluation",
        back_populates="model_run",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Evaluation.created_at",
    )


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
    )
    model_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("model_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    judge_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    model_run: Mapped["ModelRun"] = relationship("ModelRun", back_populates="evaluations")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # sha256 content hash for idempotent re-upload detection
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False, default="text/plain")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DocumentChunk.chunk_index",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dimensions),
        nullable=False,
    )
    # Full-text search tsvector generated stored column
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(text, ''))", persisted=True),
        nullable=True,
    )

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")


class BenchmarkDataset(Base):
    """Immutable, versioned collection of benchmark evaluation cases."""

    __tablename__ = "benchmark_datasets"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    cases: Mapped[list["BenchmarkCase"]] = relationship(
        "BenchmarkCase",
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BenchmarkCase.id",
    )
    experiments: Mapped[list["Experiment"]] = relationship(
        "Experiment",
        back_populates="dataset",
        lazy="selectin",
    )


class BenchmarkCase(Base):
    """An individual test question/prompt within an immutable benchmark dataset."""

    __tablename__ = "benchmark_cases"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("benchmark_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    gold_chunk_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general", index=True)

    dataset: Mapped["BenchmarkDataset"] = relationship("BenchmarkDataset", back_populates="cases")
    experiment_runs: Mapped[list["ExperimentRun"]] = relationship(
        "ExperimentRun",
        back_populates="benchmark_case",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Experiment(Base):
    """A configured multi-model evaluation run across a benchmark dataset."""

    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("benchmark_datasets.id"),
        nullable=False,
        index=True,
    )
    models: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    include_llm_judge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    dataset: Mapped["BenchmarkDataset"] = relationship("BenchmarkDataset", back_populates="experiments")
    experiment_runs: Mapped[list["ExperimentRun"]] = relationship(
        "ExperimentRun",
        back_populates="experiment",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ExperimentRun.created_at",
    )


class ExperimentRun(Base):
    """Join record linking an experiment case execution back to a real race and its model runs."""

    __tablename__ = "experiment_runs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
    )
    experiment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    benchmark_case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("benchmark_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    race_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("races.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="experiment_runs")
    benchmark_case: Mapped["BenchmarkCase"] = relationship("BenchmarkCase", back_populates="experiment_runs")
    race: Mapped["Race"] = relationship("Race")

