# Resume entries (draft)

> English first; 繁體中文版本在下方.
> Format per bullet: **what I did + how + result**. Numbers marked `{待填}` must come from [`../metrics.md`](../metrics.md). Do not guess them.
> Privacy: describe the company codebase only in generic terms ("a game front-end codebase of ~N files"). Never name internal projects, files or systems.

## English version

**On-prem Codebase RAG Assistant**: personal / team tooling project · Python, FastAPI, LlamaIndex, Qdrant, Ollama, React, Docker · [GitHub](https://github.com/alelcold/local-codebase-rag)

- Built an **on-premises RAG system** that answers natural-language questions about a game front-end codebase with **file-and-line citations**, using Ollama (`qwen2.5-coder:14b` + `nomic-embed-text`), Qdrant, FastAPI + LlamaIndex and a React UI. Code never leaves the machine, and per-query API cost is zero.
- Designed **syntax-aware chunking** with tree-sitter (one chunk per function or class, oversized classes split per method, Markdown split by heading), so every citation maps to exact source lines. Reached {待填}/20 on a 10-question evaluation set with {待填}/10 correct citations.
- Implemented **incremental indexing** keyed on per-file content hashes stored in the vector DB. Re-indexing an unchanged {待填}-file project takes {待填} s with zero re-embedding, versus {待填} s for a full rebuild.
- Diagnosed a **Docker-on-macOS GPU limitation** (no Metal passthrough) and kept the LLM native on the host, with containers reaching it via `host.docker.internal`. Average answer time is {待填} s on a Mac M2 32 GB.
- Made one Compose setup run on **Mac, GitHub Codespaces and Linux GPU instances**: `host-gateway` mapping, bind-address and security rules, and model sizing from 3B to 32B by available memory. Documented in 6 ADRs.
- Shipped the first full version (backend, UI, Docker, setup script, 50 unit tests) in **one AI-agent session for ≈ USD 7** of compute. Added an end-to-end check that caught a cross-process vector-store bug the unit tests missed.
- Benchmarked 3B / 14B / 32B models on speed and answer quality: {待填} tokens/s vs. {待填} tokens/s; quality {待填} vs. {待填}/20. The results informed the default model choice.

### Short version (one line)

- Built an on-prem codebase Q&A assistant (Ollama, Qdrant, FastAPI/LlamaIndex, React, Docker) with syntax-aware chunking, incremental indexing and file:line citations. It scored {待填}/20 on an evaluation set at {待填} s average latency on a Mac M2.

## 中文版本

**地端 Codebase RAG 問答系統**｜個人／團隊工具專案｜Python、FastAPI、LlamaIndex、Qdrant、Ollama、React、Docker｜[GitHub](https://github.com/alelcold/local-codebase-rag)

- 建置**地端 RAG 系統**，讓團隊用自然語言查詢遊戲前端程式碼，回答附**檔案與行號引用**。使用 Ollama（`qwen2.5-coder:14b`＋`nomic-embed-text`）、Qdrant、FastAPI＋LlamaIndex 與 React 介面；程式碼不離開本機，每次查詢的 API 成本為零。
- 設計**依語法結構的切塊策略**：用 tree-sitter 讓每個函式或 class 各成一塊，過大的 class 依 method 再切，Markdown 依標題切，讓每個引用都對應到精確的原始碼行數。10 題評估得分 {待填}/20，引用正確 {待填}/10。
- 實作**增量索引**：以存在向量資料庫中的各檔案內容雜湊值判斷變更。{待填} 個檔案的專案在沒有變更時重新索引只需 {待填} 秒、無需重新向量化，完整重建則需 {待填} 秒。
- 找出 **macOS 上 Docker 無法使用 GPU** 的限制（Metal 不會開放給容器），因此讓 LLM 在主機上原生執行，容器透過 `host.docker.internal` 呼叫。在 Mac M2 32GB 上平均回答時間 {待填} 秒。
- 讓同一套 Compose 設定能在 **Mac、GitHub Codespaces 與 Linux GPU 機器**上執行：處理 `host-gateway` 對應、監聽位址與資安規則，並依記憶體選擇 3B 到 32B 的模型。共撰寫 6 份 ADR。
- 以 **AI agent 單一工作階段、約 7 美元**的運算成本完成第一版（後端、介面、Docker、安裝腳本、50 個單元測試），並加入端到端驗證，抓到單元測試沒發現的跨行程向量資料庫問題。
- 實測比較 3B／14B／32B 模型的速度與回答品質：{待填} vs {待填} tokens/s，品質 {待填} vs {待填}/20，並據此決定預設模型。

### 精簡版（一行）

- 建置地端程式碼問答系統（Ollama、Qdrant、FastAPI／LlamaIndex、React、Docker），具備語法感知切塊、增量索引與「檔案:行號」引用。評估得分 {待填}/20，在 Mac M2 上平均回應時間 {待填} 秒。

---

## Notes for tailoring / 調整建議

- **AI / ML roles**: lead with chunking, evaluation and model benchmarking. **AI／ML 職缺**：先寫切塊、評估與模型實測。
- **Backend / platform roles**: lead with incremental indexing, multi-environment Docker and the end-to-end bug. **後端／平台職缺**：先寫增量索引、多環境 Docker 與端到端測試抓到的問題。
- **Front-end / game roles**: emphasize the team problem it solves and the citation UI. **前端／遊戲職缺**：強調它解決了團隊的什麼問題，以及引用介面。
- Interview follow-ups for each bullet: [`../learning/knowledge-checklist.md`](../learning/knowledge-checklist.md). 每一條可能被追問的內容，見知識檢核清單。
