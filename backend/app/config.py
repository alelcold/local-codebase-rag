"""Runtime settings, read from environment variables (see .env.example)."""

from __future__ import annotations

import re
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# nomic-embed-text was trained with task prefixes; retrieval quality drops
# noticeably without them. Other models get no prefix unless configured.
NOMIC_QUERY_PREFIX = "search_query: "
NOMIC_DOC_PREFIX = "search_document: "

PROMPT_VARIANTS = {"v1", "v2", "v3"}
# Files treated as documentation (everything else indexed is code). Same set as
# scripts/evaluate.py, so "code vs. docs" means the same thing in both places.
DOC_EXTENSIONS = {".md", ".mdx", ".markdown", ".txt", ".rst"}


def is_doc_path(path: str) -> bool:
    dot = path.rfind(".")
    return dot != -1 and path[dot:].lower() in DOC_EXTENSIONS


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # --- Ollama (runs natively on macOS, outside Docker) ---
    ollama_base_url: str = "http://host.docker.internal:11434"
    llm_model: str = "qwen2.5-coder:14b"
    llm_temperature: float = 0.1
    llm_num_ctx: int = 16384
    # Seconds per request to Ollama. CPU-only machines (e.g. Codespaces) need
    # 1.5-2 minutes per answer even with a 3B model; see ADR 0009.
    llm_request_timeout: float = 300.0
    ollama_keep_alive: str = "30m"

    embed_model: str = "nomic-embed-text"
    embed_batch_size: int = 16
    embed_request_timeout: float = 300.0
    # Unset/empty means "pick a sensible default for EMBED_MODEL".
    embed_query_prefix: str | None = None
    embed_doc_prefix: str | None = None

    # --- Qdrant ---
    qdrant_url: str = "http://qdrant:6333"
    # Empty means derive from EMBED_MODEL, so switching embedding models never
    # mixes vectors of different dimensions in one collection.
    qdrant_collection: str = ""

    # --- Indexing ---
    codebase_path: str = "/codebase"
    index_extensions: str = ".ts,.tsx,.js,.jsx,.mjs,.cjs,.md"
    exclude_dirs: str = (
        "node_modules,.git,dist,build,out,coverage,.next,.nuxt,.turbo,.cache,.vite,vendor"
    )
    exclude_patterns: str = "*.min.js,*.bundle.js,*.map,*.d.ts,package-lock.json"
    max_file_bytes: int = 500_000
    chunk_max_chars: int = 3000

    # Add file path, kind, symbol, class and the names a chunk defines/exports to
    # the text sent to the embedding model (ADR 0013). Changes what is embedded,
    # so the indexer rebuilds the whole collection when this is toggled.
    chunk_metadata: bool = False

    # --- Query ---
    # Total excerpts given to the LLM.
    top_k: int = 8
    # Prompt wording: "v1" (original), "v2" (always Traditional Chinese, code
    # locations first, documentation only as support; ADR 0013) or "v3" (v1 +
    # say "not found" when no excerpt mentions the topic + always Traditional
    # Chinese; ADR 0016).
    prompt_variant: str = "v1"
    # Hybrid retrieval: vector search + BM25 keyword search + exact identifier
    # definitions, merged with Reciprocal Rank Fusion. Query time only; no
    # re-index needed. ADR 0013.
    hybrid_search: bool = False
    rrf_k: int = 60
    # Candidates each retriever returns before fusion / per-type selection.
    retrieval_candidates: int = 30
    # Split retrieval: at most DOC_TOP_K documentation excerpts; the rest of
    # TOP_K goes to code. A type with too few hits leaves its slots to the other.
    split_retrieval: bool = False
    doc_top_k: int = 1
    # Similarity threshold (ADR 0014): vector hits whose cosine similarity is
    # below this are dropped before fusion. Empty = no filtering. No universal
    # default: calibrate per embedding model with scripts/calibrate_threshold.py.
    # Hits from the identifier channel (and keyword hits containing an exact
    # identifier from the question) are exempt. When nothing is left, the LLM is
    # not called and a fixed "not found" answer is returned.
    score_threshold: float | None = None
    # Rerank (ADR 0015): retrieve RERANK_CANDIDATES excerpts with the settings
    # above, re-score them with a cross-encoder and send the best RERANK_TOP_N
    # to the LLM. The model is loaded on first use only (needs the image built
    # with INSTALL_RERANK=true); RERANK=false never imports it.
    rerank: bool = False
    rerank_model: str = "BAAI/bge-reranker-base"
    rerank_candidates: int = 10
    rerank_top_n: int = 3
    # Tokens per (question, excerpt) pair given to the cross-encoder. CPU cost
    # grows with it; 512 covers a typical 3000-character chunk's important part.
    rerank_max_length: int = 512
    # /query/stream sends a heartbeat event when nothing else has been sent for
    # this many seconds (embedding and prompt processing can take a minute on
    # CPU), so proxies that drop idle connections keep seeing data. ADR 0010.
    stream_heartbeat_seconds: float = 10.0

    # --- API ---
    cors_origins: str = "*"

    @field_validator("embed_query_prefix", "embed_doc_prefix", mode="before")
    @classmethod
    def _empty_prefix_is_auto(cls, value: str | None) -> str | None:
        # docker compose passes unset variables through as "".
        return value or None

    @field_validator("score_threshold", mode="before")
    @classmethod
    def _empty_threshold_is_off(cls, value: object) -> object:
        # SCORE_THRESHOLD= (empty, also what docker compose passes when unset) = no filtering.
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("score_threshold")
    @classmethod
    def _check_threshold(cls, value: float | None) -> float | None:
        if value is not None and not -1.0 <= value <= 1.0:
            raise ValueError(f"SCORE_THRESHOLD is a cosine similarity (-1..1), got {value}")
        return value

    @field_validator("rerank_candidates", "rerank_top_n", "rerank_max_length")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("RERANK_CANDIDATES, RERANK_TOP_N and RERANK_MAX_LENGTH must be >= 1")
        return value

    @field_validator("prompt_variant", mode="before")
    @classmethod
    def _check_prompt_variant(cls, value: str | None) -> str:
        value = (value or "v1").strip().lower()
        if value not in PROMPT_VARIANTS:
            raise ValueError(f"PROMPT_VARIANT must be one of {sorted(PROMPT_VARIANTS)}, got {value!r}")
        return value

    @property
    def collection_name(self) -> str:
        if self.qdrant_collection:
            return self.qdrant_collection
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", self.embed_model).strip("_").lower()
        return f"codebase_{slug}"

    @property
    def _is_nomic(self) -> bool:
        return self.embed_model.split(":")[0].endswith("nomic-embed-text")

    @property
    def query_prefix(self) -> str:
        if self.embed_query_prefix is not None:
            return self.embed_query_prefix
        return NOMIC_QUERY_PREFIX if self._is_nomic else ""

    @property
    def doc_prefix(self) -> str:
        if self.embed_doc_prefix is not None:
            return self.embed_doc_prefix
        return NOMIC_DOC_PREFIX if self._is_nomic else ""

    @property
    def extensions(self) -> set[str]:
        return {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in _split_csv(self.index_extensions)}

    @property
    def excluded_dirs(self) -> set[str]:
        return set(_split_csv(self.exclude_dirs))

    @property
    def excluded_patterns(self) -> list[str]:
        return _split_csv(self.exclude_patterns)

    def retrieval_summary(self) -> dict:
        """Retrieval-related settings, reported by /health so evaluation runs record them."""
        return {
            "hybrid_search": self.hybrid_search,
            "split_retrieval": self.split_retrieval,
            "doc_top_k": self.doc_top_k if self.split_retrieval else None,
            "chunk_metadata": self.chunk_metadata,
            "prompt_variant": self.prompt_variant,
            "rrf_k": self.rrf_k if self.hybrid_search else None,
            "retrieval_candidates": self.retrieval_candidates,
            # ADR 0014 / 0015
            "score_threshold": self.score_threshold,
            "rerank": self.rerank,
            "rerank_model": self.rerank_model if self.rerank else None,
            "rerank_candidates": self.rerank_candidates if self.rerank else None,
            "rerank_top_n": self.rerank_top_n if self.rerank else None,
        }

    @property
    def default_top_k(self) -> int:
        """Excerpts sent to the LLM when the request does not say: RERANK_TOP_N
        with rerank on, else TOP_K. /health reports this as ``top_k`` so the UI
        starts from the number that is actually used."""
        return self.rerank_top_n if self.rerank else self.top_k

    @property
    def cors_origin_list(self) -> list[str]:
        return _split_csv(self.cors_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
