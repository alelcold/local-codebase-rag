"""Qdrant access: LlamaIndex's QdrantVectorStore for writes/search, plus the raw
client for the bookkeeping incremental indexing needs (per-file hashes, deletes)."""

from __future__ import annotations

from collections.abc import Sequence

from llama_index.core.schema import BaseNode, NodeWithScore
from llama_index.core.vector_stores.types import VectorStoreQuery
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

SCROLL_PAGE = 1000


class CodeVectorStore:
    def __init__(self, client: QdrantClient, collection: str):
        self.client = client
        self.collection = collection
        self._vector_store = self._make_vector_store()

    def _make_vector_store(self) -> QdrantVectorStore:
        self._built_with_collection = self.exists()
        return QdrantVectorStore(
            client=self.client,
            collection_name=self.collection,
            # Speeds up the per-file deletes done by incremental indexing.
            payload_indexes=[{"field_name": "file_path", "field_schema": qm.PayloadSchemaType.KEYWORD}],
        )

    def _store(self) -> QdrantVectorStore:
        # QdrantVectorStore inspects the collection (vector layout, existence)
        # only when constructed. The collection may be created, dropped or
        # recreated by another process, e.g. the CLI indexer while the API is
        # running, so rebuild the wrapper whenever that state has changed.
        if self.exists() != self._built_with_collection:
            self._vector_store = self._make_vector_store()
        return self._vector_store

    def exists(self) -> bool:
        return self.client.collection_exists(self.collection)

    def count(self) -> int:
        if not self.exists():
            return 0
        return self.client.count(self.collection, exact=True).count

    def file_hashes(self) -> dict[str, str]:
        """Map of file_path -> content hash for every file currently indexed."""
        if not self.exists():
            return {}
        hashes: dict[str, str] = {}
        offset = None
        while True:
            points, offset = self.client.scroll(
                self.collection,
                limit=SCROLL_PAGE,
                offset=offset,
                with_payload=["file_path", "file_hash"],
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                if "file_path" in payload:
                    hashes[payload["file_path"]] = payload.get("file_hash", "")
            if offset is None:
                return hashes

    def delete_file(self, file_path: str) -> None:
        if not self.exists():
            return
        self.client.delete(
            self.collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key="file_path", match=qm.MatchValue(value=file_path))]
                )
            ),
            wait=True,
        )

    def add(self, nodes: Sequence[BaseNode]) -> None:
        if nodes:
            self._store().add(list(nodes))

    def query(self, embedding: list[float], top_k: int) -> list[NodeWithScore]:
        if not self.exists():
            return []
        result = self._store().query(
            VectorStoreQuery(query_embedding=embedding, similarity_top_k=top_k)
        )
        nodes = result.nodes or []
        scores = result.similarities or [0.0] * len(nodes)
        return [NodeWithScore(node=n, score=s) for n, s in zip(nodes, scores)]

    def reset(self) -> None:
        """Drop the whole collection (used by full re-index)."""
        if self.exists():
            self.client.delete_collection(self.collection)
        # QdrantVectorStore caches "collection initialized"; start fresh.
        self._vector_store = self._make_vector_store()
