# 0003. Use Qdrant as the vector database

- **Status**: Accepted
- **Date**: 2026-10-30
- **Related**: [0004](0004-chunking-by-file-type.md), `backend/app/store.py`

> English first; 繁體中文版本在下方.

## Context

We need to store a few thousand chunk vectors at most (300 files × ~10 chunks) with metadata (`file_path`, `start_line`, `end_line`, `symbol`, `file_hash`). The store must support:

- similarity search with the metadata returned, for citations;
- **deleting all chunks of one file** and **listing indexed files with their hash**, for incremental indexing;
- persistence across restarts, running in Docker;
- easy testing without a server.

Scale is small, so raw performance is not the deciding factor. Operational simplicity and features are.

## Decision

Use **Qdrant** (`qdrant/qdrant:v1.20.0`) in Docker with a named volume. Access it through LlamaIndex's `QdrantVectorStore` for writes and search, and through the raw `qdrant-client` for bookkeeping (`scroll` for file hashes, delete-by-filter on `file_path`, with a keyword payload index). Unit tests use `QdrantClient(location=":memory:")`.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Chroma | Very easy, popular in tutorials | Fewer filtering and operational features; persistence behavior changed across versions | Qdrant's filter-delete and payload index fit incremental indexing better |
| pgvector (Postgres) | SQL; one DB for everything | Needs a Postgres container and schema/migrations; heavier for this use | Overkill when there is no other relational data |
| FAISS (library) | Fast, no server | No metadata store or filtering; we would manage persistence and deletes ourselves | Too much custom code |
| Milvus | Built for very large scale | Several components (etcd, MinIO); heavy for thousands of vectors | Over-engineered |
| LanceDB (embedded) | No server; files on disk | Embedded in the backend process; harder to inspect separately | Wanted a separate service with a dashboard and HTTP API |

## Consequences

- **Positive**: One small container. Payload filters make per-file delete and update simple. The in-memory mode gives fast unit tests. The built-in web dashboard (`localhost:6333/dashboard`) helps with debugging.
- **Negative / trade-offs**:
  - Mixing LlamaIndex's wrapper with the raw client exposed a wrapper quirk: vector layout is detected only at construction time. That caused the `text-dense` bug (devlog 2026-10-30). It is mitigated in `CodeVectorStore._store()`.
  - The in-memory mode ignores payload indexes and is not a perfect stand-in for the server. One end-to-end run with a real Qdrant is still needed.
- **Follow-ups**: Pin and upgrade the Qdrant image and `qdrant-client` together. Their minor versions should match.

---

# 0003. 向量資料庫選用 Qdrant

- **狀態**：已接受
- **日期**：2026-10-30

## 背景

需要儲存的向量最多只有幾千個（300 個檔案 × 約 10 個片段），並附帶 metadata（`file_path`、`start_line`、`end_line`、`symbol`、`file_hash`）。資料庫需要支援：

- 相似度搜尋，並回傳 metadata 供引用使用；
- **刪除某個檔案的所有片段**，以及**列出已索引的檔案和雜湊值**，供增量索引使用；
- 重啟後資料仍在，可以在 Docker 中執行；
- 不需要伺服器也能方便地測試。

資料量很小，所以效能不是決定因素，維運的簡單程度與功能才是。

## 決策

使用 **Qdrant**（`qdrant/qdrant:v1.20.0`），以 Docker 執行並搭配具名 volume。寫入與搜尋透過 LlamaIndex 的 `QdrantVectorStore`；索引的簿記工作則直接用 `qdrant-client`（用 `scroll` 取得檔案雜湊值、依 `file_path` 篩選刪除，並為它建立 keyword payload index）。單元測試使用 `QdrantClient(location=":memory:")`。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| Chroma | 非常容易上手，教學常見 | 篩選與維運功能較少；持久化行為在不同版本間有變動 | Qdrant 的篩選刪除與 payload index 更適合增量索引 |
| pgvector（Postgres） | 用 SQL；一個資料庫處理所有資料 | 需要 Postgres 容器與 schema／migration；用在這裡太重 | 沒有其他關聯式資料，殺雞用牛刀 |
| FAISS（函式庫） | 快，不需要伺服器 | 沒有 metadata 儲存與篩選；持久化與刪除都要自己處理 | 要寫太多自訂程式碼 |
| Milvus | 為超大規模設計 | 包含多個元件（etcd、MinIO）；幾千筆向量用它太重 | 過度設計 |
| LanceDB（內嵌） | 不需要伺服器，資料存成檔案 | 內嵌在後端行程裡，較難單獨檢查 | 希望是獨立服務，有 dashboard 和 HTTP API |

## 後果

- **正面**：只多一個小容器。payload 篩選讓「依檔案刪除和更新」變得簡單。記憶體模式讓單元測試很快。內建的網頁 dashboard（`localhost:6333/dashboard`）方便除錯。
- **負面／取捨**：
  - 同時使用 LlamaIndex 的 wrapper 和原生 client，暴露了 wrapper 的一個特性：它只在建構時偵測向量格式。這造成了 `text-dense` 的問題（見 devlog 2026-10-30），已在 `CodeVectorStore._store()` 處理。
  - 記憶體模式會忽略 payload index，無法完全代表真正的伺服器，所以仍需要一次真實 Qdrant 的端到端測試。
- **後續工作**：Qdrant 映像和 `qdrant-client` 要一起固定版本、一起升級，兩者的 minor 版本應一致。
