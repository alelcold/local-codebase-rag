# Resume entries (draft)

> English first; 繁體中文版本在下方.
> Format per bullet: **what I did + how + result**. Numbers marked `{待填}` must come from [`../metrics.md`](../metrics.md). Do not guess them.
> Privacy: describe the company codebase only in generic terms ("a game front-end codebase of ~N files"). Never name internal projects, files or systems.
> Sources: PR #1–#11 and [`../metrics.md`](../metrics.md). Every number below is from the sample project; Codespaces numbers are CPU-only with `qwen2.5-coder:3b` and automatic metrics (manual correctness not judged yet). Mac M2 numbers come from `scripts/benchmark-mac.sh` (ADR 0016) once it has run.

## English version

**On-prem Codebase RAG Assistant**: personal / team tooling project · Python, FastAPI, LlamaIndex, Qdrant, Ollama, React, Docker, GitHub Actions · [GitHub](https://github.com/alelcold/local-codebase-rag)

- Built an **on-premises RAG system** that answers natural-language questions about a game front-end codebase with **file-and-line citations**, using Ollama (`qwen2.5-coder:14b` + `nomic-embed-text`), Qdrant, FastAPI + LlamaIndex and a React UI. Code never leaves the machine, and per-query API cost is zero.
- Designed **syntax-aware chunking** with tree-sitter (one chunk per function or class, oversized classes split per method, Markdown split by heading), so every citation maps to exact source lines. Reached {待填}/20 on a 10-question evaluation set with {待填}/10 correct citations.
- Implemented **incremental indexing** keyed on per-file content hashes stored in the vector DB, with an automatic full rebuild when chunking or embedding settings change. A full index of the 20-file sample project (67 chunks) takes 21.5 s on a CPU-only CI runner; re-indexing it unchanged on a Mac M2 takes {待填} s with zero re-embedding.
- Diagnosed a **Docker-on-macOS GPU limitation** (no Metal passthrough) and kept the LLM native on the host, with containers reaching it via `host.docker.internal`. On a Mac M2 32 GB: {待填} tokens/s generation, {待填} s average answer time, {待填} s time to first token.
- Replaced blocking answers with **Server-Sent Events streaming** (sources first, then tokens, with heartbeats). Behind the Codespaces port forwarder, which cut non-streaming queries off with a 504 after about 100 s, a streamed query completed (43.8 s total, first token at 30.4 s on CPU).
- Built an **automated evaluation and experiment pipeline** (`evaluate.py`, `compare.py`, `calibrate_threshold.py`; 10 + 5 questions measuring latency, cited-file and defining-file hits, Simplified-character drift and trick-question refusals) and used it to decide retrieval changes from 7 experiment groups (two question sets each) instead of intuition:
  - **split code/doc retrieval** cut documentation in the retrieved context from 95% to 25% and raised code-file retrieval from 1/9 to 6/9 questions;
  - **hybrid search** (vector + BM25 + identifier definitions, merged with RRF) raised defining-file retrieval on identifier questions from 1/3 to 3/3 at 0.07–0.21 s retrieval time;
  - **rejected a similarity threshold** after calibration: a generic 0.70 cut-off would have dropped 93% (25/27) of the relevant excerpts;
  - kept **cross-encoder rerank optional**: alone it did not retrieve any defining file (0/3), scoring Markdown 0.8–0.99 and code mostly below 0.1, and it added 2.9–4.8 s per query on CPU.
- Made one Compose setup run on **Mac, GitHub Codespaces and Linux GPU instances**, and turned the Codespaces setup into a **dev container** that starts the whole stack on open, plus a 12-step `doctor.sh` that prints the fix for each failure. Documented the trade-offs in 16 ADRs.
- Set up **GitHub Actions CI**: 157 unit tests in about 7 s with Ollama and Qdrant faked, compose validation, image builds, and an end-to-end smoke test with a 0.5B model on the runner (first run: 40 s / 5 s / 76 s + 45 s / 2 min 41 s).
- Shipped the first full version (backend, UI, Docker, setup script, 50 unit tests) in **one AI-agent session for ≈ USD 7** of compute. Added an end-to-end check that caught a cross-process vector-store bug the unit tests missed.
- Benchmarked 3B / 14B / 32B models on speed and answer quality: {待填} tokens/s vs. {待填} tokens/s; quality {待填} vs. {待填}/20. The results informed the default model choice.

### Short version (one line)

- Built an on-prem codebase Q&A assistant (Ollama, Qdrant, FastAPI/LlamaIndex, React, Docker) with syntax-aware chunking, hybrid retrieval, streaming answers and file:line citations, and chose retrieval settings from automated evaluation runs (e.g. split retrieval: docs in context 95% → 25%). It scored {待填}/20 at {待填} s average latency on a Mac M2.

## 中文版本

**地端 Codebase RAG 問答系統**｜個人／團隊工具專案｜Python、FastAPI、LlamaIndex、Qdrant、Ollama、React、Docker、GitHub Actions｜[GitHub](https://github.com/alelcold/local-codebase-rag)

> 來源：PR #1～#11 與 [`../metrics.md`](../metrics.md)。以下數字都來自範例專案；Codespaces 的數字是只有 CPU、`qwen2.5-coder:3b`、自動指標（尚未人工評分）。Mac M2 的數字在 `scripts/benchmark-mac.sh`（ADR 0016）執行後填入。

- 建置**地端 RAG 系統**，讓團隊用自然語言查詢遊戲前端程式碼，回答附**檔案與行號引用**。使用 Ollama（`qwen2.5-coder:14b`＋`nomic-embed-text`）、Qdrant、FastAPI＋LlamaIndex 與 React 介面；程式碼不離開本機，每次查詢的 API 成本為零。
- 設計**依語法結構的切塊策略**：用 tree-sitter 讓每個函式或 class 各成一塊，過大的 class 依 method 再切，Markdown 依標題切，讓每個引用都對應到精確的原始碼行數。10 題評估得分 {待填}/20，引用正確 {待填}/10。
- 實作**增量索引**：以存在向量資料庫中的各檔案內容雜湊值判斷變更，切塊或 embedding 設定改變時自動全量重建。20 個檔案（67 個片段）的範例專案在只有 CPU 的 CI runner 上完整索引需 21.5 秒；在 Mac M2 上沒有變更時重新索引需 {待填} 秒，無需重新向量化。
- 找出 **macOS 上 Docker 無法使用 GPU** 的限制（Metal 不會開放給容器），因此讓 LLM 在主機上原生執行，容器透過 `host.docker.internal` 呼叫。在 Mac M2 32GB 上：生成速度 {待填} tokens/s、平均回答時間 {待填} 秒、首字延遲 {待填} 秒。
- 把等待整段回答改為 **Server-Sent Events 串流**（先送引用、再逐 token 送出，並送 heartbeat）。Codespaces 的連接埠轉發會在約 100 秒時讓非串流查詢回傳 504；改用串流後查詢可以完成（CPU 上總計 43.8 秒、首字延遲 30.4 秒）。
- 建立**自動化評估與實驗流程**（`evaluate.py`、`compare.py`、`calibrate_threshold.py`；10＋5 題，量測延遲、引用檔與定義檔命中、簡體字、陷阱題拒答），用 7 組實驗（各跑兩個題組）的數據、而不是直覺來決定檢索方式：
  - **程式碼／文件分類取回**：取回內容中的文件比例從 95% 降到 25%，取回程式碼檔的題目從 1/9 增加到 6/9；
  - **混合檢索**（向量＋BM25＋識別字定義，以 RRF 合併）：識別字題目取回定義檔從 1/3 提升到 3/3，檢索時間只有 0.07–0.21 秒；
  - 校準後**不採用相似度門檻**：常見的 0.70 會丟掉 93%（25/27）應取回的片段；
  - **Cross-encoder rerank 維持選用**：單獨使用時定義檔命中仍是 0/3（Markdown 得分 0.8–0.99，程式碼多半低於 0.1），而且在 CPU 上每次查詢多 2.9–4.8 秒。
- 讓同一套 Compose 設定能在 **Mac、GitHub Codespaces 與 Linux GPU 機器**上執行，並把 Codespaces 的設定做成開啟即自動啟動的 **dev container**，加上 12 個步驟、每項失敗都印出修正指令的 `doctor.sh`。取捨記錄在 16 份 ADR。
- 建置 **GitHub Actions CI**：157 個單元測試約 7 秒（Ollama、Qdrant 皆以假物件取代）、compose 檢查、映像檔 build，以及在 runner 上用 0.5B 模型跑的端到端冒煙測試（第一次執行：40 秒／5 秒／76 秒＋45 秒／2 分 41 秒）。
- 以 **AI agent 單一工作階段、約 7 美元**的運算成本完成第一版（後端、介面、Docker、安裝腳本、50 個單元測試），並加入端到端驗證，抓到單元測試沒發現的跨行程向量資料庫問題。
- 實測比較 3B／14B／32B 模型的速度與回答品質：{待填} vs {待填} tokens/s，品質 {待填} vs {待填}/20，並據此決定預設模型。

### 精簡版（一行）

- 建置地端程式碼問答系統（Ollama、Qdrant、FastAPI／LlamaIndex、React、Docker），具備語法感知切塊、混合檢索、串流回答與「檔案:行號」引用，並以自動評估的數據決定檢索設定（例如分類取回讓取回內容中的文件比例從 95% 降到 25%）。在 Mac M2 上評估得分 {待填}/20、平均回應時間 {待填} 秒。

---

## Notes for tailoring / 調整建議

- **AI / ML roles**: lead with the evaluation pipeline and the retrieval decisions (split, hybrid, rejected threshold, optional rerank), then model benchmarking. **AI／ML 職缺**：先寫評估流程與檢索決策（分類取回、混合檢索、不採用門檻、選用 rerank），再寫模型實測。
- **Backend / platform roles**: lead with streaming, incremental indexing, multi-environment Docker, CI and the dev container. **後端／平台職缺**：先寫串流、增量索引、多環境 Docker、CI 與 dev container。
- **Front-end / game roles**: emphasize the team problem it solves, the streaming UI and the citation UI. **前端／遊戲職缺**：強調它解決了團隊的什麼問題，以及串流與引用介面。
- Interview follow-ups for each bullet: [`../learning/knowledge-checklist.md`](../learning/knowledge-checklist.md). 每一條可能被追問的內容，見知識檢核清單。
