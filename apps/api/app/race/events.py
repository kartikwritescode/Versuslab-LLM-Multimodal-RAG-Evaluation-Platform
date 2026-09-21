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
    "race.completed",
]


class RaceEvent(BaseModel):
    type: EventType
    race_id: str
    sequence: int = 0
    timestamp_ns: int = Field(default_factory=time.time_ns)
    model_id: str | None = None
    text: str | None = None
    finish_reason: str | None = None
    usage: Usage | None = None
    error: str | None = None