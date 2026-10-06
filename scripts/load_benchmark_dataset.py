"""Script to load an immutable, versioned benchmark dataset into PostgreSQL.

Usage:
    python scripts/load_benchmark_dataset.py [--file path/to/dataset.json]
"""
import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

# Add apps/api to path so imports work seamlessly from repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from sqlalchemy import func, select

from app.db.base import get_session_factory
from app.db.models import BenchmarkCase, BenchmarkDataset


def read_dataset_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Dataset file not found at: {file_path}")
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


async def load_dataset(file_path: Path) -> BenchmarkDataset:
    data = read_dataset_json(file_path)

    name = data.get("name", "Unnamed Benchmark")
    description = data.get("description", "")
    cases_data = data.get("cases", [])

    if not cases_data:
        raise ValueError("Dataset must contain at least one case")

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Rule of Immutability: Determine the next version number if dataset name already exists
        stmt = select(func.coalesce(func.max(BenchmarkDataset.version), 0)).where(
            BenchmarkDataset.name == name
        )
        result = await session.execute(stmt)
        latest_version = result.scalar_one()
        new_version = latest_version + 1

        dataset = BenchmarkDataset(
            id=uuid.uuid4().hex,
            name=name,
            version=new_version,
            description=description,
        )
        session.add(dataset)
        await session.flush()

        for c in cases_data:
            case = BenchmarkCase(
                id=uuid.uuid4().hex,
                dataset_id=dataset.id,
                question=c["question"],
                expected_answer=c.get("expected_answer"),
                gold_chunk_ids=c.get("gold_chunk_ids"),
                category=c.get("category", "general"),
            )
            session.add(case)

        await session.commit()
        await session.refresh(dataset)

        print("==================================================")
        print(" VersusLab Benchmark Dataset Loaded Successfully")
        print("==================================================")
        print(f" Name        : {dataset.name}")
        print(f" Version     : {dataset.version}")
        print(f" Dataset ID  : {dataset.id}")
        print(f" Total Cases : {len(cases_data)}")
        print("==================================================")
        return dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a benchmark dataset into VersusLab")
    parser.add_argument(
        "file_pos",
        nargs="?",
        default=None,
        help="Optional positional path to JSON dataset fixture",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to JSON dataset fixture",
    )
    args = parser.parse_args()
    target_file = args.file_pos or args.file or str(REPO_ROOT / "evals" / "datasets" / "seed_benchmark.json")

    asyncio.run(load_dataset(Path(target_file)))


if __name__ == "__main__":
    main()
