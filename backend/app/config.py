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


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # --- Ollama (runs natively on macOS, outside Docker) ---
    ollama_base_url: str = "http://host.docker.internal:11434"
    llm_model: str = "qwen2.5-coder:14b"
    llm_temperature: float = 0.1
    llm_num_ctx: int = 16384
    llm_request_timeout: float = 600.0
    ollama_keep_alive: str = "30m"

    embed_model: str = "nomic-embed-text"
    embed_batch_size: int = 16
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

    # --- Query ---
    top_k: int = 8

    # --- API ---
    cors_origins: str = "*"

    @field_validator("embed_query_prefix", "embed_doc_prefix", mode="before")
    @classmethod
    def _empty_prefix_is_auto(cls, value: str | None) -> str | None:
        # docker compose passes unset variables through as "".
        return value or None

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

    @property
    def cors_origin_list(self) -> list[str]:
        return _split_csv(self.cors_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
