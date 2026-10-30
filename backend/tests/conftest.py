"""Shared fixtures. No network: Ollama is replaced by fakes (embeddings, LLM and
an httpx MockTransport), Qdrant by qdrant-client's in-process ``:memory:`` mode."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

import httpx
import pytest
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata
from llama_index.core.llms.callbacks import llm_completion_callback
from qdrant_client import QdrantClient

from app.config import Settings
from app.services import Services, assemble

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "project"
EMBED_DIM = 64


class FakeEmbedding(BaseEmbedding):
    """Deterministic bag-of-words hashing embedding: texts sharing words are close."""

    calls: int = 0

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * EMBED_DIM
        for token in re.findall(r"[a-zA-Z]{3,}", text.lower()):
            bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % EMBED_DIM
            vec[bucket] += 1.0
        if not any(vec):
            vec[0] = 1.0
        return vec

    def _get_text_embedding(self, text: str) -> list[float]:
        self.calls += 1
        return self._vector(text)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._vector(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._vector(query)


class FailingEmbedding(FakeEmbedding):
    fail_on: str = ""

    def _get_text_embedding(self, text: str) -> list[float]:
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("ollama unavailable")
        return super()._get_text_embedding(text)


class FakeLLM(CustomLLM):
    """Records prompts; answers with a canned string."""

    answer: str = "The player jumps in [1]."
    prompts: list[str] = []

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(model_name="fake-llm")

    @llm_completion_callback()
    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        self.prompts.append(prompt)
        return CompletionResponse(text=self.answer)

    @llm_completion_callback()
    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
        yield self.complete(prompt)


def ollama_transport(models: list[str] | None = None, down: bool = False) -> httpx.MockTransport:
    models = ["qwen2.5-coder:14b", "nomic-embed-text:latest"] if models is None else models

    def handler(request: httpx.Request) -> httpx.Response:
        if down:
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in models]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def codebase(tmp_path: Path) -> Path:
    dest = tmp_path / "project"
    shutil.copytree(FIXTURE_PROJECT, dest)
    return dest


@pytest.fixture
def settings(codebase: Path) -> Settings:
    return Settings(
        codebase_path=str(codebase),
        qdrant_url="http://qdrant.test:6333",
        ollama_base_url="http://ollama.test:11434",
        chunk_max_chars=1500,
        top_k=4,
    )


def make_services(
    settings: Settings,
    embed: BaseEmbedding | None = None,
    llm: FakeLLM | None = None,
    transport: httpx.MockTransport | None = None,
) -> Services:
    return assemble(
        settings,
        QdrantClient(location=":memory:"),
        embed or FakeEmbedding(),
        llm or FakeLLM(prompts=[]),
        httpx.Client(base_url=settings.ollama_base_url, transport=transport or ollama_transport()),
    )


@pytest.fixture
def services(settings: Settings) -> Services:
    return make_services(settings)
