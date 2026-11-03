"""Cross-encoder reranking (RERANK=true). Design: docs/decisions/0015-rerank.md

A bi-encoder (the embedding model) encodes question and chunk separately and
compares vectors; a cross-encoder reads the question and the chunk *together*
and outputs one relevance score. It is far more accurate per pair, but needs a
forward pass per (question, chunk) pair, so it only re-orders a short candidate
list.

The model is heavy (``torch`` + ``sentence-transformers`` add about a gigabyte
to the image, the default model is about 2 GB), so:

- nothing here imports ``torch`` or ``sentence_transformers`` at module import;
- :class:`CrossEncoderReranker` loads the model on the first :meth:`score` call,
  not at startup, and the services only create it when ``RERANK=true``;
- the dependencies are installed only when the image is built with
  ``INSTALL_RERANK=true`` (see ``backend/Dockerfile``); with them missing and
  ``RERANK=true``, queries fail with :class:`RerankUnavailableError`, which says
  how to rebuild, and ``/health`` reports it.

The model files are cached under ``HF_HOME`` (a named volume in
docker-compose.yml), so they are downloaded once, not on every container start.
"""

from __future__ import annotations

import importlib.util
import threading
import time
from collections.abc import Sequence
from typing import Protocol


class Reranker(Protocol):
    """Anything that scores (question, passage) pairs; higher = more relevant."""

    def score(self, question: str, passages: Sequence[str]) -> list[float]: ...


class RerankUnavailableError(RuntimeError):
    """RERANK=true, but the image was built without the rerank dependencies."""


def rerank_installed() -> bool:
    """True when ``sentence_transformers`` can be imported (checked without importing it)."""
    return importlib.util.find_spec("sentence_transformers") is not None


class CrossEncoderReranker:
    """``sentence_transformers.CrossEncoder``, loaded lazily and only once (thread safe)."""

    def __init__(self, model_name: str, max_length: int = 512):
        self.model_name = model_name
        self.max_length = max_length
        self._model = None
        self._lock = threading.Lock()
        # Seconds the model load took, set by the call that loaded it; the caller
        # reports it once so the first query's rerank time is not misread.
        self.load_seconds: float | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self):
        with self._lock:
            if self._model is None:
                if not rerank_installed():
                    raise RerankUnavailableError(
                        "RERANK=true，但 backend 映像檔沒有安裝 rerank 依賴（sentence-transformers / torch）。"
                        "請以 INSTALL_RERANK=true docker compose build backend 重新建置，或把 RERANK 設為 false。"
                    )
                started = time.monotonic()
                from sentence_transformers import CrossEncoder  # heavy: imports torch

                self._model = CrossEncoder(self.model_name, max_length=self.max_length)
                self.load_seconds = round(time.monotonic() - started, 3)
            return self._model

    def score(self, question: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        model = self._load()
        scores = model.predict([(question, p) for p in passages], show_progress_bar=False)
        return [float(s) for s in scores]

    def take_load_seconds(self) -> float | None:
        """Model load time if the model was loaded since the last call, else None."""
        value, self.load_seconds = self.load_seconds, None
        return value


def rerank_order(scores: Sequence[float]) -> list[int]:
    """Indices sorted by score, highest first; ties keep the incoming (retrieval) order."""
    return sorted(range(len(scores)), key=lambda i: (-scores[i], i))
