# CLAUDE.md

> English first. 繁體中文版本在下方。

## Project overview

`local-codebase-rag` is an on-premises RAG system that lets a team ask natural-language questions about a game front-end codebase (about 50–300 files). Answers cite file paths and line ranges. No code or query leaves the machine.

### Architecture

| Component | Where it runs | Code |
| --- | --- | --- |
| Ollama (LLM `qwen2.5-coder:14b`, embeddings `nomic-embed-text`) | **Natively on the host** (macOS, for Metal GPU). Never in Docker on a Mac. | — |
| Qdrant vector DB | Docker, named volume `qdrant_data` | `docker-compose.yml` |
| Backend: FastAPI + LlamaIndex (`/health`, `/index`, `/index/status`, `/query`) | Docker | `backend/app/` |
| Indexer (tree-sitter / Markdown-heading chunking, incremental by content hash) | Docker, `python -m app.indexer` | `backend/app/indexer.py`, `chunker.py` |
| Frontend: React + Vite, served by nginx, proxies `/api` | Docker | `frontend/` |

Containers reach Ollama at `http://host.docker.internal:11434`. On Linux (Codespaces, EC2), this relies on `extra_hosts: host.docker.internal:host-gateway` and Ollama listening on `0.0.0.0`. See `docs/decisions/0006-multi-environment-deployment.md`.

### Common commands

```bash
cd backend && pytest                 # unit tests (Ollama and Qdrant are faked; no network)
docker compose config -q             # validate compose
./scripts/setup.sh --index           # check Ollama, pull models, start stack, index
./scripts/index.sh [--full]          # (re)index the mounted project
cd frontend && npm run build         # type-check + build the UI
```

## Rules

### 1. Record every significant technical decision or fix

A change is "significant" when it picks between real alternatives, changes architecture or deployment, or fixes a bug that took investigation. When that happens:

a) **PR description**: add a section titled `## 技術決策說明 / Technical decisions` that explains
   - why it was done this way,
   - which alternatives were considered,
   - the trade-offs accepted.

b) **ADR**: add `docs/decisions/NNNN-short-title.md` using `docs/decisions/TEMPLATE.md` (Context, Decision, Alternatives, Consequences). Use the next free number. Never rewrite an accepted ADR. To change a decision, write a new ADR and mark the old one `Superseded by NNNN`.

c) **Devlog**: when a problem is worth remembering, add it to today's `docs/devlog/YYYY-MM-DD.md` in the form **Problem → Cause → Fix**, with the exact error message. Create the file from `docs/devlog/TEMPLATE.md` if it does not exist.

Also add new measurements to `docs/metrics.md` when you have them. Never invent numbers: leave `{待填}` when a value has not been measured.

### 2. Bilingual documents

Every document under `docs/` and this file is written in English first, followed by a Traditional Chinese version below it.

### 3. Privacy

- Documents, examples, screenshots, test fixtures and PR descriptions must **not** contain any company-internal code, file names, paths, project names or architecture details.
- All demonstrations use the sample project in `examples/sample-game-frontend/` (or the test fixtures in `backend/tests/fixtures/`).
- Before committing docs or screenshots, check that file paths, symbols and answers shown come from the sample project only.

---

# CLAUDE.md（繁體中文）

## 專案簡介

`local-codebase-rag` 是地端執行的 RAG 系統，讓團隊用自然語言查詢遊戲前端專案的程式碼（約 50–300 個檔案）。回答會附上引用的檔案路徑與行號，程式碼與問題都不會離開本機。

### 架構

| 元件 | 執行位置 | 程式碼 |
| --- | --- | --- |
| Ollama（LLM `qwen2.5-coder:14b`、embedding `nomic-embed-text`） | **直接在主機上執行**（macOS，為了使用 Metal GPU）。在 Mac 上絕不放進 Docker | — |
| Qdrant 向量資料庫 | Docker，具名 volume `qdrant_data` | `docker-compose.yml` |
| 後端：FastAPI + LlamaIndex（`/health`、`/index`、`/index/status`、`/query`） | Docker | `backend/app/` |
| 索引器（tree-sitter / Markdown 標題切塊，依內容雜湊增量索引） | Docker，`python -m app.indexer` | `backend/app/indexer.py`、`chunker.py` |
| 前端：React + Vite，由 nginx 提供並代理 `/api` | Docker | `frontend/` |

容器透過 `http://host.docker.internal:11434` 呼叫 Ollama。在 Linux（Codespaces、EC2）上，這需要 `extra_hosts: host.docker.internal:host-gateway`，而且 Ollama 要監聽 `0.0.0.0`。詳見 `docs/decisions/0006-multi-environment-deployment.md`。

### 常用指令

```bash
cd backend && pytest                 # 單元測試（Ollama 與 Qdrant 皆以假物件取代，不需網路）
docker compose config -q             # 驗證 compose 設定
./scripts/setup.sh --index           # 檢查 Ollama、拉模型、啟動服務、建立索引
./scripts/index.sh [--full]          # 重新索引掛載的專案
cd frontend && npm run build         # 型別檢查並 build 前端
```

## 規則

### 1. 每個重要技術決策或修正都要記錄

「重要」的意思是：在幾個可行方案之間做選擇、改變架構或部署方式，或是修正需要花時間追查的問題。遇到時：

a) **PR 描述**：加上 `## 技術決策說明 / Technical decisions` 段落，說明
   - 為什麼這樣做；
   - 考慮過哪些替代方案；
   - 接受了哪些取捨。

b) **ADR**：依 `docs/decisions/TEMPLATE.md`（背景、決策、替代方案、後果）新增 `docs/decisions/NNNN-short-title.md`，編號接續下去。已接受的 ADR 不要改寫；決策改變時新增一份 ADR，並把舊的標記為 `Superseded by NNNN`。

c) **Devlog**：遇到值得記錄的問題時，在當天的 `docs/devlog/YYYY-MM-DD.md` 以「**問題 → 原因 → 解法**」記錄，並附上完整錯誤訊息。檔案不存在時，從 `docs/devlog/TEMPLATE.md` 建立。

有新的量測數據時，一併更新 `docs/metrics.md`。不要編造數字，還沒量測的值保留 `{待填}`。

### 2. 雙語文件

`docs/` 底下的所有文件與本檔案，都先寫英文，下方再附繁體中文版本。

### 3. 隱私

- 文件、範例、截圖、測試資料與 PR 描述，**不得**包含任何公司內部的程式碼、檔名、路徑、專案名稱或架構細節。
- 所有示範一律使用 `examples/sample-game-frontend/` 範例專案（或 `backend/tests/fixtures/` 的測試資料）。
- 提交文件或截圖前，確認畫面中出現的檔案路徑、符號名稱與回答都只來自範例專案。
