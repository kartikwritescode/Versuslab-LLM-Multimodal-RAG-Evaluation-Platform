# CRITICAL CONTRACT: Keep in exact sync with apps/web/lib/types.ts
import time
from typing import Literal

from pydantic import BaseModel, Field

from app.providers.types import Usage

EventType = Literal[
    "race.started",
    "model.started",
    "model.delta",
    "model.completed",
    "model.error",
    "model.timeout",
    "model.cancelled",
    "race.completed",
    "race.cancelled",
]


class RaceEvent(BaseModel):
    type: EventType
    race_id: str
    # Sequence is stamped centrally in run_race to guarantee strictly increasing monotonic ordering
    sequence: int = 0
    # Nanosecond timestamp evaluates dynamically at event creation for exact timeline analysis
    timestamp_ns: int = Field(default_factory=time.time_ns)
    model_id: str | None = None
    text: str | None = None
    finish_reason: str | None = None
    usage: Usage | None = None
    error: str | None = None