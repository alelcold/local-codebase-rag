"""Incremental indexer: scan the codebase, chunk changed files, embed, store.

Run inside the backend container:
    python -m app.indexer          # only new / changed / deleted files
    python -m app.indexer --full   # drop the collection and rebuild everything

Change detection compares each file's hash with the ``file_hash`` stored in
Qdrant, so the vector store itself is the source of truth: wiping the Qdrant
volume simply causes a full re-index on the next run.

Every point also stores ``index_config`` (see :func:`index_config`): the
settings that decide what gets chunked and embedded. When the stored value
differs from the current settings (or is missing, i.e. the index was built by an
older version), the run turns into a full rebuild automatically, so vectors
built with different settings are never mixed in one collection (ADR 0013).
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import logging
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

from .chunker import CHUNKER_VERSION, Chunk, chunk_file, declared_names
from .config import Settings, is_doc_path
from .store import CodeVectorStore

log = logging.getLogger(__name__)

# Payload keys kept out of the text LlamaIndex would otherwise build for
# embeddings / prompts; we compose those texts ourselves.
_METADATA_KEYS = [
    "file_path",
    "file_hash",
    "start_line",
    "end_line",
    "symbol",
    "kind",
    "language",
    "defines",
    "exports",
    "index_config",
]

# Bump when the embedding text format changes.
EMBED_FORMAT_VERSION = "2"


@dataclass
class IndexReport:
    scanned: int = 0
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    chunks_written: int = 0
    full: bool = False
    # Why a full rebuild happened although --full was not given (settings changed).
    rebuild_reason: str | None = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def scan_files(root: Path, settings: Settings) -> tuple[dict[str, Path], list[str]]:
    """Return ({relative posix path: absolute path}, skipped relative paths)."""
    files: dict[str, Path] = {}
    skipped: list[str] = []
    excluded_dirs = settings.excluded_dirs
    patterns = settings.excluded_patterns
    extensions = settings.extensions

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in excluded_dirs)
        for name in sorted(filenames):
            abs_path = Path(dirpath) / name
            rel = abs_path.relative_to(root).as_posix()
            if abs_path.suffix.lower() not in extensions:
                continue
            if any(fnmatch.fnmatch(name, p) for p in patterns):
                continue
            try:
                if abs_path.stat().st_size > settings.max_file_bytes:
                    skipped.append(rel)
                    continue
            except OSError:
                skipped.append(rel)
                continue
            files[rel] = abs_path
    return files, skipped


def content_hash(data: bytes, settings: Settings) -> str:
    """Hash of file content *and* chunking config, so config changes re-chunk."""
    h = hashlib.sha256()
    h.update(f"{CHUNKER_VERSION}:{settings.chunk_max_chars}:{settings.embed_model}\n".encode())
    h.update(data)
    return h.hexdigest()


def index_config(settings: Settings) -> str:
    """Everything that changes what is chunked or embedded, as one readable string.

    Stored on every point; a mismatch makes the next indexing run a full rebuild.
    Query-time settings (hybrid search, split retrieval, prompt) are not part of
    it: toggling those needs no re-index.
    """
    return (
        f"chunker={CHUNKER_VERSION};embed_format={EMBED_FORMAT_VERSION};"
        f"chunk_max_chars={settings.chunk_max_chars};embed_model={settings.embed_model};"
        f"doc_prefix={settings.doc_prefix!r};chunk_metadata={'on' if settings.chunk_metadata else 'off'}"
    )


def chunk_names(chunk: Chunk) -> tuple[list[str], list[str]]:
    return declared_names(chunk.text, chunk.language)


def embed_text(chunk: Chunk, settings: Settings) -> str:
    """Text sent to the embedding model: location header + code.

    With CHUNK_METADATA on, the header also says whether this is code or
    documentation, the enclosing class of a method, and every name the chunk
    defines / exports, so a question naming a constant lands on the chunk that
    declares it even when the code itself is a bare list of assignments.
    """
    header = f"File: {chunk.file_path}\n"
    if settings.chunk_metadata:
        header += f"Type: {'documentation' if is_doc_path(chunk.file_path) else 'code'} ({chunk.language})\n"
        if chunk.symbol:
            header += f"{'Section' if chunk.kind == 'section' else 'Symbol'}: {chunk.symbol} ({chunk.kind})\n"
            if chunk.kind == "method" and "." in chunk.symbol:
                header += f"Class: {chunk.symbol.split('.', 1)[0]}\n"
        defines, exports = chunk_names(chunk)
        if defines:
            header += f"Defines: {', '.join(defines)}\n"
        if exports:
            header += f"Exports: {', '.join(exports)}\n"
    elif chunk.symbol:
        header += f"Symbol: {chunk.symbol} ({chunk.kind})\n"
    return f"{settings.doc_prefix}{header}\n{chunk.text}"


def chunk_to_node(chunk: Chunk, file_hash: str, embedding: list[float], config: str = "") -> TextNode:
    node_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"{chunk.file_path}:{chunk.start_line}:{chunk.end_line}:{file_hash}")
    )
    defines, exports = chunk_names(chunk)
    node = TextNode(
        id_=node_id,
        text=chunk.text,
        embedding=embedding,
        metadata={
            "file_path": chunk.file_path,
            "file_hash": file_hash,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "symbol": chunk.symbol or "",
            "kind": chunk.kind,
            "language": chunk.language,
            # Comma-separated (Qdrant payloads stay flat); used by keyword search.
            "defines": ",".join(defines),
            "exports": ",".join(exports),
            "index_config": config,
        },
        excluded_embed_metadata_keys=_METADATA_KEYS,
        excluded_llm_metadata_keys=_METADATA_KEYS,
    )
    node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=chunk.file_path)
    return node


class CodebaseIndexer:
    def __init__(self, settings: Settings, store: CodeVectorStore, embed_model: BaseEmbedding):
        self.settings = settings
        self.store = store
        self.embed_model = embed_model

    def run(self, full: bool = False, progress: Callable[[str], None] | None = None) -> IndexReport:
        started = time.monotonic()
        report = IndexReport(full=full)
        notify = progress or (lambda _msg: None)
        root = Path(self.settings.codebase_path)
        if not root.is_dir():
            raise FileNotFoundError(f"Codebase path not found or not a directory: {root}")

        current = index_config(self.settings)
        if not full:
            stored = self.store.index_configs()
            if stored and stored != {current}:
                full = report.full = True
                old = ", ".join(sorted(c or "(none: built by an older version)" for c in stored))
                report.rebuild_reason = f"index settings changed: {old} -> {current}"
                notify(f"Index settings changed, rebuilding everything.\n  was: {old}\n  now: {current}")
        if full:
            notify("Full re-index: dropping existing collection")
            self.store.reset()

        files, report.skipped = scan_files(root, self.settings)
        report.scanned = len(files)
        indexed = self.store.file_hashes()

        for rel in sorted(set(indexed) - set(files)):
            self.store.delete_file(rel)
            report.deleted.append(rel)
            notify(f"deleted  {rel}")

        for i, (rel, abs_path) in enumerate(sorted(files.items()), start=1):
            try:
                data = abs_path.read_bytes()
                digest = content_hash(data, self.settings)
                if indexed.get(rel) == digest:
                    report.unchanged += 1
                    continue
                text = data.decode("utf-8", errors="replace")
                written = self._index_file(rel, text, digest)
                report.chunks_written += written
                if written == 0 and rel not in indexed:
                    report.unchanged += 1  # empty file; nothing to store
                    continue
                (report.updated if rel in indexed else report.added).append(rel)
                notify(f"[{i}/{len(files)}] indexed {rel} ({written} chunks)")
            except Exception as exc:  # keep going; report per-file failures
                log.exception("Failed to index %s", rel)
                report.errors[rel] = f"{type(exc).__name__}: {exc}"
                notify(f"[{i}/{len(files)}] ERROR {rel}: {exc}")

        report.duration_seconds = round(time.monotonic() - started, 2)
        return report

    def _index_file(self, rel: str, text: str, digest: str) -> int:
        chunks = chunk_file(rel, text, self.settings.chunk_max_chars)
        # Embed before deleting old points: if Ollama fails, the old version
        # stays searchable and the file is retried next run.
        embeddings: list[list[float]] = []
        batch = self.settings.embed_batch_size
        texts = [embed_text(c, self.settings) for c in chunks]
        for start in range(0, len(texts), batch):
            embeddings.extend(self.embed_model.get_text_embedding_batch(texts[start : start + batch]))
        config = index_config(self.settings)
        nodes = [chunk_to_node(c, digest, e, config) for c, e in zip(chunks, embeddings)]
        self.store.delete_file(rel)
        self.store.add(nodes)
        return len(nodes)


def main(argv: list[str] | None = None) -> int:
    from .services import build_services

    parser = argparse.ArgumentParser(description="Index the codebase into Qdrant.")
    parser.add_argument("--full", action="store_true", help="drop the collection and rebuild everything")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    services = build_services()
    s = services.settings
    print(f"Codebase:   {s.codebase_path}")
    print(f"Collection: {s.collection_name}  (embed model: {s.embed_model})")
    print(f"Settings:   {index_config(s)}")
    report = services.indexer.run(full=args.full, progress=print)
    print(
        f"\nDone in {report.duration_seconds}s — scanned {report.scanned}, "
        f"added {len(report.added)}, updated {len(report.updated)}, deleted {len(report.deleted)}, "
        f"unchanged {report.unchanged}, skipped {len(report.skipped)}, errors {len(report.errors)}, "
        f"chunks written {report.chunks_written}"
    )
    if report.rebuild_reason:
        print(f"Full rebuild because {report.rebuild_reason}")
    for path, err in report.errors.items():
        print(f"  ERROR {path}: {err}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
