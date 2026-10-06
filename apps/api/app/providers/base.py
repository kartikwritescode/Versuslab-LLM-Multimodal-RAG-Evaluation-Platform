from collections.abc import AsyncIterator
from typing import Protocol

from app.providers.types import ModelDelta, ModelRequest


class ModelProvider(Protocol):
    # Plain def is used because calling an async generator returns an AsyncIterator without awaiting
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelDelta]: ...
