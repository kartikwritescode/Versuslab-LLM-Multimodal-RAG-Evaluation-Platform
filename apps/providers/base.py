from collections.abc import AsyncIterator
from typing import Protocol

from app.providers.types import ModelDelta , ModelRequest

class ModelProvider(Protocol):
    def stream(self , request: ModelRequest) -> AsyncIterator[ModelDelta]: ...