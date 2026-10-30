"""Wiring: build the Ollama / Qdrant clients and the services that use them.

Everything external is created here, so tests can build ``Services`` with
fakes (mock embeddings / LLM, in-memory Qdrant, mocked HTTP transport).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms import LLM
from qdrant_client import QdrantClient

from .config import Settings, get_settings
from .indexer import CodebaseIndexer
from .rag import RagService
from .store import CodeVectorStore


@dataclass
class Services:
    settings: Settings
    store: CodeVectorStore
    embed_model: BaseEmbedding
    llm: LLM
    indexer: CodebaseIndexer
    rag: RagService
    ollama_http: httpx.Client


def assemble(
    settings: Settings,
    qdrant: QdrantClient,
    embed_model: BaseEmbedding,
    llm: LLM,
    ollama_http: httpx.Client,
) -> Services:
    store = CodeVectorStore(qdrant, settings.collection_name)
    return Services(
        settings=settings,
        store=store,
        embed_model=embed_model,
        llm=llm,
        indexer=CodebaseIndexer(settings, store, embed_model),
        rag=RagService(settings, store, embed_model, llm),
        ollama_http=ollama_http,
    )


def build_services(settings: Settings | None = None) -> Services:
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama

    settings = settings or get_settings()
    embed_model = OllamaEmbedding(
        model_name=settings.embed_model,
        base_url=settings.ollama_base_url,
        embed_batch_size=settings.embed_batch_size,
        keep_alive=settings.ollama_keep_alive,
    )
    llm = Ollama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=settings.llm_temperature,
        context_window=settings.llm_num_ctx,  # sent to Ollama as num_ctx
        request_timeout=settings.llm_request_timeout,
        keep_alive=settings.ollama_keep_alive,
    )
    return assemble(
        settings,
        QdrantClient(url=settings.qdrant_url, timeout=30),
        embed_model,
        llm,
        httpx.Client(base_url=settings.ollama_base_url, timeout=5.0),
    )


def _model_present(wanted: str, available: set[str]) -> bool:
    if wanted in available:
        return True
    # Ollama reports "nomic-embed-text:latest" for a model pulled as "nomic-embed-text".
    return ":" not in wanted and f"{wanted}:latest" in available


def check_ollama(services: Services) -> dict:
    s = services.settings
    required = [s.llm_model, s.embed_model]
    try:
        resp = services.ollama_http.get("/api/tags")
        resp.raise_for_status()
        available = {m.get("name", "") for m in resp.json().get("models", [])}
    except Exception as exc:
        return {"ok": False, "url": s.ollama_base_url, "error": f"{type(exc).__name__}: {exc}"}
    missing = [m for m in required if not _model_present(m, available)]
    return {
        "ok": not missing,
        "url": s.ollama_base_url,
        "llm_model": s.llm_model,
        "embed_model": s.embed_model,
        "missing_models": missing,
    }


def check_qdrant(services: Services) -> dict:
    s = services.settings
    try:
        exists = services.store.exists()
        points = services.store.count() if exists else 0
    except Exception as exc:
        return {"ok": False, "url": s.qdrant_url, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "url": s.qdrant_url, "collection": s.collection_name, "indexed": exists, "points": points}
