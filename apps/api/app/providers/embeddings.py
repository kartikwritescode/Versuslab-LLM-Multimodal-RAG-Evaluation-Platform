import hashlib
import math
from typing import Protocol

import httpx

from app.core.config import settings


class EmbeddingProvider(Protocol):
    """Protocol defining the asynchronous embedding provider contract."""

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generates embedding vectors for a list of document chunk texts."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Generates an embedding vector for a single search query text."""
        ...


class OllamaEmbeddingProvider:
    """Ollama embedding provider calling POST /api/embed."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_embedding_model
        self.timeout_s = timeout_s

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Batches texts and calls Ollama /api/embed."""
        if not texts:
            return []

        url = f"{self.base_url}/api/embed"
        payload = {"model": self.model, "input": texts}

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list):
            raise TypeError(f"Unexpected Ollama embedding response shape: {data}")

        return embeddings

    async def embed_query(self, text: str) -> list[float]:
        """Generates embedding for a single query text."""
        vectors = await self.embed_documents([text])
        if not vectors:
            raise ValueError("Ollama returned empty embeddings for query")
        return vectors[0]


class MockEmbeddingProvider:
    """Deterministic embedding provider for testing without live network or GPU models."""

    def __init__(self, dimensions: int = 768) -> None:
        self.dimensions = dimensions

    def _hash_text(self, text: str) -> list[float]:
        """Produces a deterministic, unit-normalized float vector from text hash."""
        # Use sha256 to seed deterministic pseudo-values
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = []
        for i in range(self.dimensions):
            byte_val = h[i % len(h)]
            # Spread into [-1.0, 1.0]
            val = ((byte_val / 255.0) * 2.0) - 1.0 + (i * 0.001)
            vec.append(val)

        # Normalize to unit length for cosine similarity
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_text(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._hash_text(text)


_embedding_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Returns the configured embedding provider singleton."""
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = OllamaEmbeddingProvider()
    return _embedding_provider


def set_embedding_provider(provider: EmbeddingProvider | None) -> None:
    """Allows overriding the embedding provider for testing."""
    global _embedding_provider
    _embedding_provider = provider
