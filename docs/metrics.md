# Metrics

> English first; 繁體中文版本在下方.
> Rules: record **measured** values only; leave `{待填}` otherwise. Always note the environment (machine, model, settings). Unless stated otherwise, measurements use the sample project `examples/sample-game-frontend/`. Never record numbers from company code here.

## 1. Development cost

| Item | Value | Date | Notes |
| --- | --- | --- | --- |
| Claude Code cloud session (initial build: design → code → tests → PR #1) | **≈ USD 7** | 2026-10-30 | One session |
| Claude Code (docs / learning structure) | {待填} | 2026-10-31 | |
| GitHub Codespaces usage | {待填} | 2026-11-01 | Core-hours |
| Claude Code (timeouts, CI, docs PR) | {待填} | 2026-11-02 | |
| GitHub Actions minutes | {待填} | | Public repo on GitHub-hosted runners: check the billing page |
| GPU instance for 32B benchmark | {待填} | | Instance type, USD/h × hours |
| **Total** | {待填} | | |

## 2. Indexing

| Date | Environment | Project | Files | Chunks | Full index (s) | Incremental, no changes (s) | Embedding model |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-30 | Cloud sandbox, **fake embeddings** | Sample | 20 | 67 | 0.39* | 0.01* | (fake) |
| 2026-11-01 | Codespaces (CPU) | Sample | 20 | 67 | {待填} | {待填} | nomic-embed-text |
| 2026-11-02 | GitHub Actions runner (CPU, CI smoke test, Ollama 0.40.13) | Sample | 20 | 67 | 21.54 | — | nomic-embed-text |
| {待填} | Mac M2 32 GB | Sample | 20 | 67 | {待填} | {待填} | nomic-embed-text |
| {待填} | Mac M2 32 GB | Real project (count only, no names) | {待填} | {待填} | {待填} | {待填} | nomic-embed-text |

\* Pipeline overhead only. The fake embeddings make these numbers meaningless as performance data.

## 3. Query latency

**Source**: from now on, latency comes from `scripts/evaluate.py` (10 different questions through `/query/stream`, after a warm-up query; see [evaluation/README.md](evaluation/README.md) and ADR 0012). Link the report in Notes. Single queries measured by hand in the UI are marked as such.

Measure from the "送出" click until the answer appears (or with `time curl …/query`). Record the first query after model load separately. Do not repeat the same question to get an average: Ollama's prompt cache makes repeats much faster (see the 0.8 s row below).

**Time to first token** (since the streaming UI, ADR 0010): from the "送出" click until the first answer token appears. The UI shows it as 「首字延遲」 under the answer; the backend reports `first_token_seconds` in the stream's `done` event. Use the average of the same 10 queries.

| Date | Environment | Model | top_k | First query (s) | Avg of 10 queries (s) | p90 (s) | Time to first token, avg (s) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-01 | Codespaces (CPU) | qwen2.5-coder:3b | 8 | {待填} | {待填} | {待填} | — | **Estimated ≈ 1.5–2 min per query** (not measured over 10 queries). The UI returned 504 before the timeout fix; see ADR 0009 |
| 2026-11-02 | Codespaces (CPU), `curl` through nginx inside the codespace | qwen2.5-coder:3b | {待填} | 54.7 | — | — | — | One query, non-streaming `/query`. The same query from the browser through the port forwarder failed with 504 after about 100 s (test log #9; ADR 0010) |
| 2026-11-02 | Codespaces (CPU), browser through the forwarding URL, streaming | qwen2.5-coder:3b | 4 | 43.8 | — | — | 30.4 (first query) | Single query by hand: 「玩家受傷後的無敵時間在哪裡設定？」, first after model load, 129 tokens. All 4 retrieved chunks were docs; the answer named the wrong file and mixed in Simplified characters (devlog 2026-11-02) |
| 2026-11-02 | Same | qwen2.5-coder:3b | 4 | — | — | — | 0.8 (prompt cache) | Same question asked again: 14.3 s total, 134 tokens. Ollama reused the cached prompt, so this is **not** normal latency. Generation speed both times ≈ 10 tokens/s |
| {待填} | Codespaces (CPU), `scripts/evaluate.py` | qwen2.5-coder:3b | 4 | — | {待填} | {待填} | {待填} | 10 questions; check that nothing is cut off at about 100 s |
| 2026-11-02 | GitHub Actions runner (CPU) | qwen2.5-coder:0.5b | 4 | 8 | — | — | — | CI smoke test (PR #3), one query, `LLM_NUM_CTX=4096`. Pipeline check only: the answer text had no `[n]` citation (sources were correct) |
| 2026-11-02 | GitHub Actions runner (CPU) | qwen2.5-coder:0.5b | 4 | 5 | — | — | 0.09 (backend) | CI smoke test (PR #4): non-streaming query 5 s; streaming query (model already loaded) 1.0 s total, 44 tokens, `first_token_seconds` 0.086 from the `done` event |
| {待填} | Mac M2 32 GB | qwen2.5-coder:14b | 8 | {待填} | {待填} | {待填} | {待填} | |

## 4. Evaluation results

**Source**: `scripts/evaluate.py` on the 10 questions in [`evaluation/questions.yaml`](evaluation/questions.yaml) (same as [`questions.md`](evaluation/questions.md)), then `--apply-manual` after a person fills in the correctness column. Copy the numbers from the report's summary and link the report. Automatic columns are proxies; only "Manual correctness" measures correct answers (ADR 0012). Compare runs with `scripts/compare.py`.

| Date | Environment | Model | top_k | Manual correctness (/20) | Code file retrieved | Defining file retrieved | Keyword hit rate | Answers with Simplified | Q10 refused | First token, mean (s) | Total, mean (s) | Report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| {待填} | Codespaces | qwen2.5-coder:3b | 4 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | Codespaces | qwen2.5-coder:3b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | Mac M2 | qwen2.5-coder:14b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | GPU instance | qwen2.5-coder:32b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |

### 4a. Retrieval switches (ADR 0013)

Runs from [`evaluation/experiment-plan-retrieval.md`](evaluation/experiment-plan-retrieval.md): Codespaces, `qwen2.5-coder:3b`, `TOP_K=4`. "Main" = `questions.yaml` (10), "Ident." = `questions-identifiers.yaml` (5).

| Date | Group | Switches | Manual correctness, main (/20) | Defining file retrieved, main | Defining file retrieved, ident. | Code file retrieved, main | Docs among retrieved chunks, main | Answers with Simplified | First token, mean (s) | Report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| {待填} | A. baseline | all off | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | B. + hybrid | `HYBRID_SEARCH` | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | C. + split | `SPLIT_RETRIEVAL`, `DOC_TOP_K=1` | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | F. all on | + `CHUNK_METADATA`, `PROMPT_VARIANT=v2` | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |

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
| 2026-11-02 | Backend unit tests | 56 passed (≈ 1.4 s, no network), including 504 timeout handling |
| 2026-11-01 | Problems found on Codespaces that unit tests missed | {待填} (see [devlog](devlog/2026-11-01-codespace-setup.md)) |
| 2026-11-02 | Backend unit tests after streaming (`/query/stream`) | 70 passed (≈ 2 s, no network) |
| 2026-11-02 | Backend unit tests including the evaluation scripts | 93 passed (≈ 5 s, no network; the backend is mocked by a local SSE server) |
| 2026-11-02 | CI duration, first run (no caches): unit tests / compose config / image builds (backend, frontend) / smoke test | 40 s / 5 s / 76 s, 45 s / 2 min 41 s (PR #3) |

## How to measure

```bash
# Index time (prints duration at the end)
./scripts/index.sh --full
```

```bash
# Query latency
time curl -sS localhost:8000/query -H 'Content-Type: application/json' -d '{"question":"玩家受傷後的無敵時間在哪裡設定？"}' > /dev/null
```

```bash
# Streaming: time to first token and total (the done event has the backend's own numbers)
curl -sS -N localhost:8080/api/query/stream -H 'Content-Type: application/json' -d '{"question":"玩家受傷後的無敵時間在哪裡設定？"}' | grep -A1 '^event: done'
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
| Claude Code（逾時、CI、文件 PR） | {待填} | 2026-11-02 | |
| GitHub Actions 分鐘數 | {待填} | | 公開 repo 使用 GitHub 提供的 runner：請查看帳單頁面 |
| 32B 測試用的 GPU 機器 | {待填} | | 機型、每小時美元 × 時數 |
| **總計** | {待填} | | |

## 2. 索引

| 日期 | 環境 | 專案 | 檔案數 | 片段數 | 完整索引（秒） | 無變更增量索引（秒） | Embedding 模型 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-30 | 雲端 sandbox，**假 embedding** | 範例專案 | 20 | 67 | 0.39* | 0.01* | （假） |
| 2026-11-01 | Codespaces（CPU） | 範例專案 | 20 | 67 | {待填} | {待填} | nomic-embed-text |
| 2026-11-02 | GitHub Actions runner（CPU，CI 冒煙測試，Ollama 0.40.13） | 範例專案 | 20 | 67 | 21.54 | — | nomic-embed-text |
| {待填} | Mac M2 32GB | 範例專案 | 20 | 67 | {待填} | {待填} | nomic-embed-text |
| {待填} | Mac M2 32GB | 實際專案（只記數量，不記名稱） | {待填} | {待填} | {待填} | {待填} | nomic-embed-text |

\* 只代表流程本身的開銷。因為使用假 embedding，這些數字不能當作效能數據。

## 3. 查詢時間

**數據來源**：之後的查詢時間改由 `scripts/evaluate.py` 產生（10 個不同的問題，經 `/query/stream`，先送一題暖機問題；見 [evaluation/README.md](evaluation/README.md) 與 ADR 0012），並在備註附上報告連結。在介面上手動量的單次查詢會另外註明。

從按下「送出」到回答出現為止（或用 `time curl …/query`）。模型載入後的第一次查詢另外記錄。不要用重複問同一題的方式取平均：Ollama 的提示詞快取會讓重複的問題快很多（見下方 0.8 秒那一列）。

**首字延遲**（介面改為串流後，ADR 0010）：從按下「送出」到回答的第一個字出現為止。介面會在回答下方顯示「首字延遲」；後端則在串流的 `done` 事件中回報 `first_token_seconds`。取同樣 10 次查詢的平均。

| 日期 | 環境 | 模型 | top_k | 第一次查詢（秒） | 10 次平均（秒） | p90（秒） | 首字延遲平均（秒） | 備註 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-01 | Codespaces（CPU） | qwen2.5-coder:3b | 8 | {待填} | {待填} | {待填} | — | **推算每次約 1.5～2 分鐘**（不是 10 次查詢的實測平均）。修正逾時前介面回傳 504，見 ADR 0009 |
| 2026-11-02 | Codespaces（CPU），在 codespace 內用 `curl` 經 nginx | qwen2.5-coder:3b | {待填} | 54.7 | — | — | — | 單次查詢，非串流的 `/query`。同樣的查詢從瀏覽器經連接埠轉發，約 100 秒後回傳 504（測試紀錄 #9；ADR 0010） |
| 2026-11-02 | Codespaces（CPU），瀏覽器經轉發網址，串流 | qwen2.5-coder:3b | 4 | 43.8 | — | — | 30.4（第一次查詢） | 手動單次查詢：「玩家受傷後的無敵時間在哪裡設定？」，模型載入後的第一次，129 個 token。取回的 4 段全是文件；回答說錯檔案，並混入簡體字（devlog 2026-11-02） |
| 2026-11-02 | 同上 | qwen2.5-coder:3b | 4 | — | — | — | 0.8（提示詞快取） | 同一題再問一次：總耗時 14.3 秒，134 個 token。Ollama 重用了快取的提示詞，所以**不是**一般的延遲。兩次的生成速度都約每秒 10 個 token |
| {待填} | Codespaces（CPU），`scripts/evaluate.py` | qwen2.5-coder:3b | 4 | — | {待填} | {待填} | {待填} | 10 題；確認不會在約 100 秒時被中斷 |
| 2026-11-02 | GitHub Actions runner（CPU） | qwen2.5-coder:0.5b | 4 | 8 | — | — | — | CI 冒煙測試（PR #3），單次查詢，`LLM_NUM_CTX=4096`。只用來驗證流程：回答文字沒有 `[n]` 引用（來源正確） |
| 2026-11-02 | GitHub Actions runner（CPU） | qwen2.5-coder:0.5b | 4 | 5 | — | — | 0.09（後端） | CI 冒煙測試（PR #4）：非串流查詢 5 秒；串流查詢（模型已載入）總共 1.0 秒、44 個 token，`done` 事件的 `first_token_seconds` 為 0.086 |
| {待填} | Mac M2 32GB | qwen2.5-coder:14b | 8 | {待填} | {待填} | {待填} | {待填} | |

## 4. 評估結果

**數據來源**：用 `scripts/evaluate.py` 跑 [`evaluation/questions.yaml`](evaluation/questions.yaml) 的 10 題（與 [`questions.md`](evaluation/questions.md) 相同），由人填好正確性欄位後執行 `--apply-manual`。從報告的摘要抄數字，並附上報告連結。自動計算的欄位只是代理指標，只有「人工判定正確性」代表回答正確（ADR 0012）。不同次執行用 `scripts/compare.py` 比較。

| 日期 | 環境 | 模型 | top_k | 人工判定正確性（/20） | 程式碼檔命中 | 定義檔命中 | 關鍵字命中率 | 混入簡體字的回答 | 第 10 題拒答 | 首字延遲平均（秒） | 總耗時平均（秒） | 報告 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| {待填} | Codespaces | qwen2.5-coder:3b | 4 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | Codespaces | qwen2.5-coder:3b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | Mac M2 | qwen2.5-coder:14b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | GPU 機器 | qwen2.5-coder:32b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |

### 4a. 檢索開關（ADR 0013）

依 [`evaluation/experiment-plan-retrieval.md`](evaluation/experiment-plan-retrieval.md) 執行：Codespaces、`qwen2.5-coder:3b`、`TOP_K=4`。「主要」= `questions.yaml`（10 題），「識別字」= `questions-identifiers.yaml`（5 題）。

| 日期 | 組別 | 開關 | 人工判定正確性，主要（/20） | 定義檔命中，主要 | 定義檔命中，識別字 | 程式碼檔命中，主要 | 取回片段中文件比例，主要 | 混入簡體字的回答 | 首字延遲平均（秒） | 報告 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| {待填} | A. 基準線 | 全部關閉 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | B. + 混合檢索 | `HYBRID_SEARCH` | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | C. + 分類取回 | `SPLIT_RETRIEVAL`、`DOC_TOP_K=1` | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | F. 全部開啟 | + `CHUNK_METADATA`、`PROMPT_VARIANT=v2` | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |

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
| 2026-11-02 | 後端單元測試 | 56 個通過（約 1.4 秒，不需網路），包含 504 逾時處理 |
| 2026-11-01 | Codespaces 上發現、單元測試沒抓到的問題 | {待填}（見 [devlog](devlog/2026-11-01-codespace-setup.md)） |
| 2026-11-02 | 加入串流（`/query/stream`）後的後端單元測試 | 70 個通過（約 2 秒，不需網路） |
| 2026-11-02 | 含評估腳本的後端單元測試 | 93 個通過（約 5 秒，不需網路；後端以本機的 SSE 假伺服器取代） |
| 2026-11-02 | CI 耗時，第一次執行（沒有快取）：單元測試／compose 檢查／映像檔 build（backend、frontend）／冒煙測試 | 40 秒／5 秒／76 秒、45 秒／2 分 41 秒（PR #3） |

## 量測方式

```bash
# 索引時間（最後會顯示耗時）
./scripts/index.sh --full
```

```bash
# 查詢時間
time curl -sS localhost:8000/query -H 'Content-Type: application/json' -d '{"question":"玩家受傷後的無敵時間在哪裡設定？"}' > /dev/null
```

```bash
# 串流：首字延遲與總時間（done 事件裡是後端自己量的數字）
curl -sS -N localhost:8080/api/query/stream -H 'Content-Type: application/json' -d '{"question":"玩家受傷後的無敵時間在哪裡設定？"}' | grep -A1 '^event: done'
```

```bash
# 模型記憶體／CPU 與 GPU 的分配
ollama ps
```

```bash
# 每秒 token 數（eval rate）
ollama run qwen2.5-coder:14b --verbose "Explain a fixed-timestep game loop in 3 sentences."
```
