# Metrics

> English first; 繁體中文版本在下方.
> Rules: record **measured** values only; leave `{待填}` otherwise. Always note the environment (machine, model, settings). Unless stated otherwise, measurements use the sample project `examples/sample-game-frontend/`. Never record numbers from company code here.

## 1. Development cost

| Item | Value | Date | Notes |
| --- | --- | --- | --- |
| Claude Code cloud session (initial build: design → code → tests → PR #1) | **≈ USD 7** | 2026-10-30 | One session |
| Claude Code (docs / learning structure) | {待填} | 2026-10-31 | |
| GitHub Codespaces usage | {待填} | 2026-11-01 | Core-hours |
| GPU instance for 32B benchmark | {待填} | | Instance type, USD/h × hours |
| **Total** | {待填} | | |

## 2. Indexing

| Date | Environment | Project | Files | Chunks | Full index (s) | Incremental, no changes (s) | Embedding model |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-30 | Cloud sandbox, **fake embeddings** | Sample | 20 | 67 | 0.39* | 0.01* | (fake) |
| 2026-11-01 | Codespaces (CPU) | Sample | 20 | 67 | {待填} | {待填} | nomic-embed-text |
| {待填} | Mac M2 32 GB | Sample | 20 | 67 | {待填} | {待填} | nomic-embed-text |
| {待填} | Mac M2 32 GB | Real project (count only, no names) | {待填} | {待填} | {待填} | {待填} | nomic-embed-text |

\* Pipeline overhead only. The fake embeddings make these numbers meaningless as performance data.

## 3. Query latency

Measure from the "送出" click until the answer appears (or with `time curl …/query`). Record the first query after model load separately.

| Date | Environment | Model | top_k | First query (s) | Avg of 10 queries (s) | p90 (s) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-01 | Codespaces (CPU) | qwen2.5-coder:3b | 8 | {待填} | {待填} | {待填} | |
| {待填} | Mac M2 32 GB | qwen2.5-coder:14b | 8 | {待填} | {待填} | {待填} | |

## 4. Evaluation results

Uses the 10 questions in [`evaluation/questions.md`](evaluation/questions.md).

| Date | Environment | Model | Correct (0–2 each, max 20) | Citations correct (/10) | Says "not found" for Q10 | Avg latency (s) |
| --- | --- | --- | --- | --- | --- | --- |
| {待填} | Codespaces | qwen2.5-coder:3b | {待填} | {待填} | {待填} | {待填} |
| {待填} | Mac M2 | qwen2.5-coder:14b | {待填} | {待填} | {待填} | {待填} |
| {待填} | GPU instance | qwen2.5-coder:32b | {待填} | {待填} | {待填} | {待填} |

## 5. Model comparison (3B / 14B / 32B)

| Model | Download size | Memory in use (`ollama ps`) | Runs on GPU? | Tokens/s (generation) | Avg query (s) | Eval score (/20) | Citation accuracy | Subjective quality notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen2.5-coder:3b | ≈ 1.9 GB | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| qwen2.5-coder:14b | ≈ 9 GB | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| qwen2.5-coder:32b | ≈ 20 GB | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |

Download sizes are approximate values from the Ollama library tags (Q4). Replace them with what `ollama list` shows on your machine.

## 6. Engineering quality

| Date | Item | Value |
| --- | --- | --- |
| 2026-10-30 | Backend unit tests | 50 passed (< 1 s, no network) |
| 2026-10-30 | Bugs found by end-to-end run that unit tests missed | 1 (`text-dense` vector name; see devlog) |

## How to measure

```bash
# Index time (prints duration at the end)
./scripts/index.sh --full
```

```bash
# Query latency
time curl -s localhost:8000/query -H 'Content-Type: application/json' -d '{"question":"玩家受傷後的無敵時間在哪裡設定？"}' > /dev/null
```

```bash
# Model memory / CPU vs GPU split
ollama ps
```

```bash
# Tokens per second (eval rate)
ollama run qwen2.5-coder:14b --verbose "Explain a fixed-timestep game loop in 3 sentences."
```

---

# 數據紀錄

> 規則：只記錄**實際量測**的數值，沒量過就保留 `{待填}`。務必註明環境（機器、模型、設定）。除非另外註明，量測一律使用範例專案 `examples/sample-game-frontend/`。不要在這裡記錄任何來自公司程式碼的數據。

## 1. 開發成本

| 項目 | 數值 | 日期 | 備註 |
| --- | --- | --- | --- |
| Claude Code 雲端工作階段（初版建置：設計 → 程式 → 測試 → PR #1） | **約 7 美元** | 2026-10-30 | 單一工作階段 |
| Claude Code（文件與學習紀錄結構） | {待填} | 2026-10-31 | |
| GitHub Codespaces 用量 | {待填} | 2026-11-01 | 核心小時數 |
| 32B 測試用的 GPU 機器 | {待填} | | 機型、每小時美元 × 時數 |
| **總計** | {待填} | | |

## 2. 索引

| 日期 | 環境 | 專案 | 檔案數 | 片段數 | 完整索引（秒） | 無變更增量索引（秒） | Embedding 模型 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-30 | 雲端 sandbox，**假 embedding** | 範例專案 | 20 | 67 | 0.39* | 0.01* | （假） |
| 2026-11-01 | Codespaces（CPU） | 範例專案 | 20 | 67 | {待填} | {待填} | nomic-embed-text |
| {待填} | Mac M2 32GB | 範例專案 | 20 | 67 | {待填} | {待填} | nomic-embed-text |
| {待填} | Mac M2 32GB | 實際專案（只記數量，不記名稱） | {待填} | {待填} | {待填} | {待填} | nomic-embed-text |

\* 只代表流程本身的開銷。因為使用假 embedding，這些數字不能當作效能數據。

## 3. 查詢時間

從按下「送出」到回答出現為止（或用 `time curl …/query`）。模型載入後的第一次查詢另外記錄。

| 日期 | 環境 | 模型 | top_k | 第一次查詢（秒） | 10 次平均（秒） | p90（秒） | 備註 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-01 | Codespaces（CPU） | qwen2.5-coder:3b | 8 | {待填} | {待填} | {待填} | |
| {待填} | Mac M2 32GB | qwen2.5-coder:14b | 8 | {待填} | {待填} | {待填} | |

## 4. 評估結果

使用 [`evaluation/questions.md`](evaluation/questions.md) 的 10 題。

| 日期 | 環境 | 模型 | 正確性（每題 0–2，滿分 20） | 引用正確（/10） | 第 10 題是否回答找不到 | 平均回應時間（秒） |
| --- | --- | --- | --- | --- | --- | --- |
| {待填} | Codespaces | qwen2.5-coder:3b | {待填} | {待填} | {待填} | {待填} |
| {待填} | Mac M2 | qwen2.5-coder:14b | {待填} | {待填} | {待填} | {待填} |
| {待填} | GPU 機器 | qwen2.5-coder:32b | {待填} | {待填} | {待填} | {待填} |

## 5. 模型比較（3B／14B／32B）

| 模型 | 下載大小 | 實際記憶體（`ollama ps`） | 是否在 GPU 上執行 | 生成速度（tokens/s） | 平均查詢（秒） | 評估分數（/20） | 引用正確率 | 主觀品質備註 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen2.5-coder:3b | 約 1.9GB | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| qwen2.5-coder:14b | 約 9GB | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| qwen2.5-coder:32b | 約 20GB | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |

下載大小是 Ollama 模型庫標籤（Q4）的大約值，請改成你機器上 `ollama list` 顯示的數字。

## 6. 工程品質

| 日期 | 項目 | 數值 |
| --- | --- | --- |
| 2026-10-30 | 後端單元測試 | 50 個通過（< 1 秒，不需網路） |
| 2026-10-30 | 端到端測試抓到、單元測試沒抓到的問題 | 1 個（`text-dense` 向量名稱，見 devlog） |

## 量測方式

```bash
# 索引時間（最後會顯示耗時）
./scripts/index.sh --full
```

```bash
# 查詢時間
time curl -s localhost:8000/query -H 'Content-Type: application/json' -d '{"question":"玩家受傷後的無敵時間在哪裡設定？"}' > /dev/null
```

```bash
# 模型記憶體／CPU 與 GPU 的分配
ollama ps
```

```bash
# 每秒 token 數（eval rate）
ollama run qwen2.5-coder:14b --verbose "Explain a fixed-timestep game loop in 3 sentences."
```
