"""Embedding backends (D4): BGE-M3 served by Ollama is the default local
path (multilingual incl. Persian, no torch in our process). The fake backend
is a deterministic hash-projection used in dev/CI so retrieval logic is
testable with no models installed — it is NOT semantically meaningful.
"""
from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

from neurai.config import get_config

DIM_FAKE = 64


class EmbeddingBackend(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def name(self) -> str: ...


class OllamaEmbeddings:
    def __init__(self) -> None:
        from neurai.harness.backends import OllamaBackend

        self._backend = OllamaBackend()
        self._model = get_config().embed_model

    @property
    def name(self) -> str:
        return f"ollama:{self._model}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._backend.embed(texts, model=self._model)


class FakeEmbeddings:
    name = "fake:hash64"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = np.zeros(DIM_FAKE, dtype=np.float32)
            # bag-of-words hashing so shared tokens → nonzero similarity
            for token in text.split():
                h = int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "little")
                vec[h % DIM_FAKE] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            out.append(vec.tolist())
        return out


_backend: EmbeddingBackend | None = None


def get_embeddings() -> EmbeddingBackend:
    global _backend
    if _backend is None:
        cfg = get_config()
        _backend = FakeEmbeddings() if cfg.asr_engine == "fake" else OllamaEmbeddings()
    return _backend


def set_embeddings(b: EmbeddingBackend | None) -> None:
    global _backend
    _backend = b
