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
| {待填} | Codespaces | qwen2.5-coder:3b | 4 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | Codespaces | qwen2.5-coder:3b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | Mac M2 | qwen2.5-coder:14b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | GPU instance | qwen2.5-coder:32b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |

### 4a. Retrieval switches (ADR 0013)

Runs from [`evaluation/experiment-plan-retrieval.md`](evaluation/experiment-plan-retrieval.md): Codespaces, `qwen2.5-coder:3b`, `TOP_K=4`. "Main" = `questions.yaml` (10), "Ident." = `questions-identifiers.yaml` (5). "Q10 refused" = the trick question answered with "not found" (report: Trick question refused); for G and I also note whether it came from the threshold (LLM not called). "Rerank time" = mean `rerank_seconds` of the `done` event, model load excluded (ADR 0015); "—" = rerank off.

| Date | Group | Switches | Manual correctness, main (/20) | Defining file retrieved, main | Defining file retrieved, ident. | Code file retrieved, main | Docs among retrieved chunks, main | Answers with Simplified | Q10 refused | First token, mean (s) | Rerank time, mean (s) | Report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-03 | A. baseline | all off | {待填} | 0/3 (0%) | 1/3 (33%) | 1/9 (11%) | 95% | 1 / 0 | No (0/1) | 13.0 / 21.2 | — | [main](evaluation/results/2026-11-03-codespace-3b-k4-baseline.md) · [ident.](evaluation/results/2026-11-03-codespace-3b-k4-baseline-ident.md) |
| 2026-11-03 | B. + hybrid | `HYBRID_SEARCH` | {待填} | 0/3 (0%) | 3/3 (100%) | 3/9 (33%) | 88% | 0 / 0 | No (0/1) | 6.7 / 10.7 ¹ | — | [main](evaluation/results/2026-11-03-codespace-3b-k4-hybrid.md) · [ident.](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-ident.md) |
| 2026-11-03 | C. + split | `SPLIT_RETRIEVAL`, `DOC_TOP_K=1` | {待填} | 1/3 (33%) | 3/3 (100%) | 6/9 (67%) | 25% | 3 / 0 | No (0/1) | 15.9 / 17.8 | — | [main](evaluation/results/2026-11-03-codespace-3b-k4-split.md) · [ident.](evaluation/results/2026-11-03-codespace-3b-k4-split-ident.md) |
| 2026-11-03 | D. + hybrid + split | `HYBRID_SEARCH`, `SPLIT_RETRIEVAL`, `DOC_TOP_K=1` | {待填} | 0/3 (0%) | 3/3 (100%) | 6/9 (67%) | 25% | 4 / 2 | No (0/1) | 17.2 / 19.9 | — | [main](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split.md) · [ident.](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-ident.md) |
| 2026-11-03 | F. all on | + `CHUNK_METADATA`, `PROMPT_VARIANT=v2` | {待填} | 0/3 (0%) | 3/3 (100%) | 5/9 (56%) | 25% | 2 / 0 | No (0/1) | 19.6 / 23.8 | — | [main](evaluation/results/2026-11-03-codespace-3b-k4-all.md) · [ident.](evaluation/results/2026-11-03-codespace-3b-k4-all-ident.md) |
| 2026-11-03 | G. + threshold | **Not adopted after calibration**: no `SCORE_THRESHOLD` value suggested, group not run | — | — | — | — | — | — | — | — | — | [calibration](evaluation/results/2026-11-03-threshold-calibration.md) |
| 2026-11-03 | H. + rerank | `RERANK`, 10 → 4 | {待填} | 0/3 (0%) | 2/3 (67%) | 2/9 (22%) | 85% | 1 / 1 | No (0/1) | 21.2 / 27.4 | 2.9 / 4.4 | [main](evaluation/results/2026-11-03-codespace-3b-k4-rerank.md) · [ident.](evaluation/results/2026-11-03-codespace-3b-k4-rerank-ident.md) |
| 2026-11-03 | I. hybrid + split + rerank | `HYBRID_SEARCH`, `SPLIT_RETRIEVAL`, `DOC_TOP_K=1`, `RERANK`, 10 → 4 (redefined, see the experiment plan) | {待填} | 3/3 (100%) | 3/3 (100%) | 7/9 (78%) | 23% | 0 / 0 | No (0/1) | 26.8 / 26.3 | 4.8 / 6.4 | [main](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-rerank.md) · [ident.](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-rerank-ident.md) |
| 2026-11-03 | J. D + prompt v3 | `HYBRID_SEARCH`, `SPLIT_RETRIEVAL`, `DOC_TOP_K=1`, `PROMPT_VARIANT=v3` (ADR 0016) | {待填} | 0/3 (0%) | 3/3 (100%) | 6/9 (67%) | 25% | 0 / 0 ³ | Yes (1/1), but 8 of 9 real questions refused too (§4c) | 20.3 / 26.3 | — | [main](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-v3.md) · [ident.](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-v3-ident.md) |

"Answers with Simplified", "First token, mean (s)" and "Rerank time, mean (s)" are given as main / ident.; "Q10 refused" is from the main set. Manual correctness is not judged yet. Comparisons: `evaluation/results/2026-11-03-baseline-vs-{hybrid,split,all,rerank,hybrid-split-rerank}[-ident].md` `2026-11-03-split-vs-hybrid-split-rerank[-ident].md`, and for D: `2026-11-03-split-vs-hybrid-split[-ident].md` (C → D) and `2026-11-03-hybrid-split-vs-hybrid-split-rerank[-ident].md` (D → I, the effect of rerank alone). First-token time is measured from the request, so in H and I it includes the rerank time. Rerank time grows with excerpt length: in I most candidates are code chunks (longer than doc sections), hence 4.8–6.4 s vs 2.9 s in H. Prompt caching (footnote ¹) shows up once: in I's ident. set, question 15 retrieved the same excerpts as in H, and its first token minus rerank time was 0.2 s, so I's ident. first-token mean is too low. Even after subtracting rerank, H's main-set first-token mean (18.3 s) is higher than A's (13.0 s), with similar excerpts. Compare latency between groups with care.

¹ Not caused by hybrid search: retrieval took 0.07–0.21 s in every group. In B, 7 of the 10 main questions retrieved exactly the same excerpts as in A, and three of them (2, 4, 9) got their first token in about 0.2 s, which points to Ollama reusing a cached prompt. The questions whose excerpts changed (5, 8) were not faster than in A (11.7 → 13.9 s, 16.2 → 15.0 s). Run order and caching affect these means, so do not read B's latency as a gain. First-token time follows prompt length: C and F put longer code excerpts in the prompt (e.g. 146 lines for question 3 in C → 47 s).

### 4b. Reranker CPU cost (micro-benchmark, ADR 0015)

Cross-encoder only (no LLM, no retrieval): 10 (question, excerpt) pairs from the sample project, question 「玩家受傷後的無敵時間在哪裡設定？」, median of 5 runs after one warm-up, `sentence-transformers` 5.1.2, `torch` 2.9.1+cpu. **Environment: Claude Code cloud container, 4 vCPU x86_64, 15 GB, no GPU** (similar size to a Codespace, not a Codespace; Mac numbers {待填}). Real per-query rerank time on Codespaces goes into §4a.

| Date | Model | `RERANK_MAX_LENGTH` | 10 pairs, median (s) | Peak RSS (MB) | Download (GB) |
| --- | --- | --- | --- | --- | --- |
| 2026-11-02 | `BAAI/bge-reranker-v2-m3` (568M) | 512 | 11.97 | 2846 | 2.2 |
| 2026-11-02 | `BAAI/bge-reranker-v2-m3` | 256 | 5.54 | 2579 | 2.2 |
| 2026-11-02 | **`BAAI/bge-reranker-base` (278M, default)** | 512 | 3.73 | 1851 | 1.1 |
| 2026-11-02 | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (118M) | 512 | 1.03 | 1326 | 0.47 |
| {待填} | `BAAI/bge-reranker-base` | 512 | {待填} (Mac M2, in Docker) | {待填} | 1.1 |

First load of `bge-reranker-base` from the local cache inside the backend image: 7.8 s (same container).

### 4c. Refusing out-of-scope questions (ADR 0016)

Group J of the [experiment plan](evaluation/experiment-plan-retrieval.md) against its reference D (same retrieval, prompt v1). "Refusal rate" = trick questions answered "not found" without invented code (report: 拒答率); "False refusal rate" = answerable questions answered with a "not found" phrase and no keyword hit (report: 誤拒率). "Out-of-scope" = `questions-out-of-scope.yaml` (5 trick questions 21–25, 3 control questions 26–28). Main-set false refusals are over its 9 answerable questions.

| Date | Group | Prompt | Refusal rate, out-of-scope (/5) | False refusal rate, out-of-scope (/3) | Q10 refused, main | False refusal rate, main (/9) | False refusal rate, ident. (/5) | Answers with Simplified, main / out-of-scope | Manual correctness, main (/20) | Report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-03 | D. hybrid + split | v1 | 1/5 (20%) ⁴ | 0/3 (0%) | No (0/1) | 0/9 (0%) ² | 0/5 (0%) ² | 4 / 7 | {待填} | [main](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split.md) · [out-of-scope](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-oos.md) |
| 2026-11-03 | J. D + prompt v3 | v3 | 5/5 (100%) | **3/3 (100%)** | Yes (1/1) | **8/9 (89%)** | **2/5 (40%)** | 0 / 0 ³ | {待填} | [main](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-v3.md) · [ident.](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-v3-ident.md) · [out-of-scope](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-v3-oos.md) |

J retrieved exactly the same excerpts as D on all 23 questions, so every difference is the prompt. Of J's 23 answers, 19 are the fixed sentence 「在索引的專案中找不到相關內容。」 and nothing else (11 tokens); only main Q3 and ident. Q12, Q14, Q15 were answered. Refused real questions include main Q5, Q6 and ident. Q11, Q13, where every expected file was retrieved. **Prompt v3 is not adopted** (decision rule of the experiment plan: false refusal rate must stay 0). Comparisons: `evaluation/results/2026-11-03-hybrid-split-vs-hybrid-split-v3[-ident|-oos].md`.

³ Not a fix for Simplified characters: 19 of 23 J answers are the fixed sentence. The 4 real answers had none, too few to judge.

⁴ Keyword screen. By reading the answers, D refused 2 of 5: Q22 is a refusal written in Simplified Chinese, and the keyword list has 無法 only in its Traditional form (quoted in the 2026-11-03 devlog). Q23 (cloud sync “via `syncUi`”) and Q25 (gamepad mapped to the keyboard handler) are invented answers.

² Re-scored, not re-run: the false-refusal check applied to D's existing 2026-11-03 answers. The same re-scoring of every A–I report (main and ident.) also gives 0: none of the 14 answerable questions' answers contained a refusal phrase in any group, so the v1 / v2 baseline is 0 and any false refusal in J comes from prompt v3. Reports written before ADR 0016 have no `false_refusals` in their summary, so `compare.py` shows "—" for them.

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
| 2026-11-02 | Backend unit tests with threshold, rerank (fake cross-encoder) and calibration script | 157 passed (≈ 7 s, no network, no model download) |
| 2026-11-02 | Backend image size, default / `INSTALL_RERANK=true` (`docker images`, linux/amd64) | 616 MB / 2.14 GB (+1.5 GB: torch CPU, transformers, scipy, scikit-learn …; model not included) |
| 2026-11-03 | Backend unit tests with prompt v3, out-of-scope question set and refusal / false-refusal metrics | 170 passed (≈ 7 s, no network) |

## How to measure

On the Mac M2, one command measures §2, §3, §4, §4a and §5 and writes a summary whose tables have the same columns as this file (ADR 0016; README「在 Mac 實機測試（一鍵量測）」):

```bash
./scripts/benchmark-mac.sh
```

The single measurements below are what it runs.

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
| {待填} | Codespaces | qwen2.5-coder:3b | 4 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | Codespaces | qwen2.5-coder:3b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | Mac M2 | qwen2.5-coder:14b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |
| {待填} | GPU 機器 | qwen2.5-coder:32b | 8 | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} | {待填} |

### 4a. 檢索開關（ADR 0013）

依 [`evaluation/experiment-plan-retrieval.md`](evaluation/experiment-plan-retrieval.md) 執行：Codespaces、`qwen2.5-coder:3b`、`TOP_K=4`。「主要」= `questions.yaml`（10 題），「識別字」= `questions-identifiers.yaml`（5 題）。「Q10 拒答」= 陷阱題回答「找不到」（報告的「陷阱題正確拒答」）；G、I 組另外註明是否由門檻直接拒答（未呼叫 LLM）。「rerank 耗時」= `done` 事件 `rerank_seconds` 的平均，不含模型載入（ADR 0015）；「—」= 未開啟 rerank。

| 日期 | 組別 | 開關 | 人工判定正確性，主要（/20） | 定義檔命中，主要 | 定義檔命中，識別字 | 程式碼檔命中，主要 | 取回片段中文件比例，主要 | 混入簡體字的回答 | Q10 拒答 | 首字延遲平均（秒） | rerank 耗時平均（秒） | 報告 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-03 | A. 基準線 | 全部關閉 | {待填} | 0/3 (0%) | 1/3 (33%) | 1/9 (11%) | 95% | 1 / 0 | 否（0/1） | 13.0 / 21.2 | — | [主要](evaluation/results/2026-11-03-codespace-3b-k4-baseline.md) · [識別字](evaluation/results/2026-11-03-codespace-3b-k4-baseline-ident.md) |
| 2026-11-03 | B. + 混合檢索 | `HYBRID_SEARCH` | {待填} | 0/3 (0%) | 3/3 (100%) | 3/9 (33%) | 88% | 0 / 0 | 否（0/1） | 6.7 / 10.7 ¹ | — | [主要](evaluation/results/2026-11-03-codespace-3b-k4-hybrid.md) · [識別字](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-ident.md) |
| 2026-11-03 | C. + 分類取回 | `SPLIT_RETRIEVAL`、`DOC_TOP_K=1` | {待填} | 1/3 (33%) | 3/3 (100%) | 6/9 (67%) | 25% | 3 / 0 | 否（0/1） | 15.9 / 17.8 | — | [主要](evaluation/results/2026-11-03-codespace-3b-k4-split.md) · [識別字](evaluation/results/2026-11-03-codespace-3b-k4-split-ident.md) |
| 2026-11-03 | D. + 混合 + 分類 | `HYBRID_SEARCH`、`SPLIT_RETRIEVAL`、`DOC_TOP_K=1` | {待填} | 0/3 (0%) | 3/3 (100%) | 6/9 (67%) | 25% | 4 / 2 | 否（0/1） | 17.2 / 19.9 | — | [主要](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split.md) · [識別字](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-ident.md) |
| 2026-11-03 | F. 全部開啟 | + `CHUNK_METADATA`、`PROMPT_VARIANT=v2` | {待填} | 0/3 (0%) | 3/3 (100%) | 5/9 (56%) | 25% | 2 / 0 | 否（0/1） | 19.6 / 23.8 | — | [主要](evaluation/results/2026-11-03-codespace-3b-k4-all.md) · [識別字](evaluation/results/2026-11-03-codespace-3b-k4-all-ident.md) |
| 2026-11-03 | G. + 門檻 | **校準後不採用**：`calibrate_threshold.py` 沒有建議值，未執行 | — | — | — | — | — | — | — | — | — | [校準輸出](evaluation/results/2026-11-03-threshold-calibration.md) |
| 2026-11-03 | H. + Rerank | `RERANK`，10 → 4 | {待填} | 0/3 (0%) | 2/3 (67%) | 2/9 (22%) | 85% | 1 / 1 | 否（0/1） | 21.2 / 27.4 | 2.9 / 4.4 | [主要](evaluation/results/2026-11-03-codespace-3b-k4-rerank.md) · [識別字](evaluation/results/2026-11-03-codespace-3b-k4-rerank-ident.md) |
| 2026-11-03 | I. 混合 + 分類 + Rerank | `HYBRID_SEARCH`、`SPLIT_RETRIEVAL`、`DOC_TOP_K=1`、`RERANK`，10 → 4（重新定義，見實驗計畫） | {待填} | 3/3 (100%) | 3/3 (100%) | 7/9 (78%) | 23% | 0 / 0 | 否（0/1） | 26.8 / 26.3 | 4.8 / 6.4 | [主要](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-rerank.md) · [識別字](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-rerank-ident.md) |
| 2026-11-03 | J. D + 提示 v3 | `HYBRID_SEARCH`、`SPLIT_RETRIEVAL`、`DOC_TOP_K=1`、`PROMPT_VARIANT=v3`（ADR 0016） | {待填} | 0/3 (0%) | 3/3 (100%) | 6/9 (67%) | 25% | 0 / 0 ³ | 是（1/1），但 9 題真實問題有 8 題也被拒答（§4c） | 20.3 / 26.3 | — | [主要](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-v3.md) · [識別字](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-v3-ident.md) |

「混入簡體字的回答」、「首字延遲平均」與「rerank 耗時平均」的格式為 主要 / 識別字；「Q10 拒答」來自主要題組。人工判定正確性尚未評分。比較報告：`evaluation/results/2026-11-03-baseline-vs-{hybrid,split,all,rerank,hybrid-split-rerank}[-ident].md` 、`2026-11-03-split-vs-hybrid-split-rerank[-ident].md`，以及 D 組的 `2026-11-03-split-vs-hybrid-split[-ident].md`（C → D）與 `2026-11-03-hybrid-split-vs-hybrid-split-rerank[-ident].md`（D → I，只有 rerank 的差別）。首字延遲從送出請求開始計算，所以 H、I 組包含 rerank 耗時。rerank 耗時隨片段長度增加：I 組的候選多半是程式碼片段（比文件段落長），所以是 4.8–6.4 秒，H 組是 2.9 秒。提示快取（註 ¹）出現了一次：I 組識別字題組第 15 題取回的片段與 H 組相同，首字延遲扣掉 rerank 只有 0.2 秒，所以 I 組識別字題組的首字平均偏低。H 組主要題組扣掉 rerank 後的首字平均（18.3 秒）仍高於 A 組（13.0 秒），而兩組取回的片段相近。各組之間的延遲比較要小心解讀。

¹ 不是混合檢索造成的：每一組的檢索都只花 0.07–0.21 秒。B 組主要題組 10 題中有 7 題取回的片段與 A 組完全相同，其中第 2、4、9 題的首字只要約 0.2 秒，看起來是 Ollama 重用了快取的提示。片段有改變的題目（5、8）沒有比 A 快（11.7 → 13.9 秒、16.2 → 15.0 秒）。執行順序與快取都會影響這些平均值，不要把 B 的延遲看成改善。首字延遲取決於提示長度：C、F 會把較長的程式碼片段放進提示（例如 C 組第 3 題 146 行 → 47 秒）。

### 4b. Reranker 的 CPU 成本（微基準測試，ADR 0015）

只量交叉編碼器（不含 LLM 與檢索）：範例專案的 10 組（問題, 片段），問題為「玩家受傷後的無敵時間在哪裡設定？」，暖機一次後跑 5 次取中位數，`sentence-transformers` 5.1.2、`torch` 2.9.1+cpu。**環境：Claude Code 雲端容器，4 vCPU x86_64、15 GB、無 GPU**（規格接近 Codespace，但不是 Codespace；Mac 數據 {待填}）。Codespaces 上每次查詢實際的 rerank 耗時記在 §4a。

| 日期 | 模型 | `RERANK_MAX_LENGTH` | 10 組中位數（秒） | 記憶體峰值（MB） | 下載大小（GB） |
| --- | --- | --- | --- | --- | --- |
| 2026-11-02 | `BAAI/bge-reranker-v2-m3`（568M） | 512 | 11.97 | 2846 | 2.2 |
| 2026-11-02 | `BAAI/bge-reranker-v2-m3` | 256 | 5.54 | 2579 | 2.2 |
| 2026-11-02 | **`BAAI/bge-reranker-base`（278M，預設）** | 512 | 3.73 | 1851 | 1.1 |
| 2026-11-02 | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`（118M） | 512 | 1.03 | 1326 | 0.47 |
| {待填} | `BAAI/bge-reranker-base` | 512 | {待填}（Mac M2，Docker 內） | {待填} | 1.1 |

在 backend 映像檔內從本機快取第一次載入 `bge-reranker-base`：7.8 秒（同一個容器環境）。

### 4c. 拒答範圍外的問題（ADR 0016）

[實驗計畫](evaluation/experiment-plan-retrieval.md)的 J 組，以 D 組（同樣的檢索、提示 v1）為參考。「拒答率」= 陷阱題回答「找不到」而且沒有編造程式碼（報告的「拒答率」）；「誤拒率」= 可回答的題目，回答含有「找不到」類的字句而且沒有命中任何關鍵字（報告的「誤拒率」）。「範圍外」= `questions-out-of-scope.yaml`（陷阱題 21–25 共 5 題、對照題 26–28 共 3 題）。主要題組的誤拒率以其中 9 題可回答的題目計算。

| 日期 | 組別 | 提示 | 拒答率，範圍外（/5） | 誤拒率，範圍外（/3） | Q10 拒答，主要 | 誤拒率，主要（/9） | 誤拒率，識別字（/5） | 混入簡體字的回答，主要 / 範圍外 | 人工判定正確性，主要（/20） | 報告 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-03 | D. 混合 + 分類 | v1 | 1/5 (20%) ⁴ | 0/3 (0%) | 否（0/1） | 0/9 (0%) ² | 0/5 (0%) ² | 4 / 7 | {待填} | [主要](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split.md) · [範圍外](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-oos.md) |
| 2026-11-03 | J. D + 提示 v3 | v3 | 5/5 (100%) | **3/3 (100%)** | 是（1/1） | **8/9 (89%)** | **2/5 (40%)** | 0 / 0 ³ | {待填} | [主要](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-v3.md) · [識別字](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-v3-ident.md) · [範圍外](evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-v3-oos.md) |

J 組在全部 23 題取回的片段都與 D 組完全相同，所以所有差異都來自提示。J 組 23 個回答中，有 19 個只有固定句「在索引的專案中找不到相關內容。」（11 個 token）；只有主要題組第 3 題、識別字題組第 12、14、15 題有回答。被拒答的真實問題包括主要題組第 5、6 題與識別字題組第 11、13 題，這幾題的預期檔案全部都有取回。**不採用提示 v3**（實驗計畫的決策規則：誤拒率必須維持 0）。比較報告：`evaluation/results/2026-11-03-hybrid-split-vs-hybrid-split-v3[-ident|-oos].md`。

³ 這不代表簡體字問題解決了：J 組 23 個回答有 19 個是固定句。另外 4 個真正的回答沒有簡體字，但數量太少，無法下結論。

⁴ 這是關鍵字篩選的結果。實際讀過回答，D 組 5 題拒答了 2 題：第 22 題是用簡體字寫的拒答，關鍵字清單的「無法」只有繁體寫法（原文引用在 2026-11-03 的 devlog）。第 23 題（「透過 `syncUi`」同步到雲端）與第 25 題（把手把對應到鍵盤處理函式）都是編造的回答。

² 重新計分，不是重新執行：用誤拒判定檢查 D 組 2026-11-03 既有的回答。對 A～I 組所有報告（主要與識別字題組）做同樣的重新計分，結果也都是 0：14 題可回答的題目在任何一組的回答都沒有出現拒答字句，所以 v1／v2 的基準是 0，J 組若有誤拒，就是提示 v3 造成的。ADR 0016 之前產生的報告摘要中沒有 `false_refusals`，`compare.py` 會顯示「—」。

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
| 2026-11-02 | 含門檻、rerank（假的交叉編碼器）與校準腳本的後端單元測試 | 157 個通過（約 7 秒，不需網路、不下載模型） |
| 2026-11-02 | backend 映像檔大小，預設／`INSTALL_RERANK=true`（`docker images`，linux/amd64） | 616 MB／2.14 GB（+1.5 GB：torch CPU 版、transformers、scipy、scikit-learn 等；不含模型） |
| 2026-11-03 | 含提示 v3、範圍外題組與拒答率／誤拒率的後端單元測試 | 170 個通過（約 7 秒，不需網路） |

## 量測方式

在 Mac M2 上，一個指令就能量完 §2、§3、§4、§4a、§5，並輸出欄位與本檔案相同的摘要（ADR 0016；README「在 Mac 實機測試（一鍵量測）」）：

```bash
./scripts/benchmark-mac.sh
```

下面是它實際執行的個別量測。

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
