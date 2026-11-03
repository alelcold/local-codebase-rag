# Article series plan

> English first; 繁體中文版本在下方.
> Privacy: every example, screenshot and number in the articles comes from the sample project (`examples/sample-game-frontend/`) or from this repo. Never show company code, file names or architecture.
> Metric references (M§n) point to sections of [`../metrics.md`](../metrics.md).

## Article 1 — Why I built an on-prem codebase RAG

- **Target readers**: Front-end and game developers, and tech leads who want "ask the codebase" without sending code to the cloud.
- **Key sections**:
  1. The problem: onboarding questions ("where is X configured?") and the limits of grep.
  2. Why not just use a cloud AI assistant: privacy, unpredictable cost, the team needs a shared tool (ADR 0001).
  3. What RAG is, in one diagram: index time vs. query time.
  4. Architecture: Ollama on the host, plus Qdrant / FastAPI + LlamaIndex / React in Docker.
  5. What "good" looks like: answers with clickable `file:line` citations.
  6. Limits: a 14B local model vs. frontier models, single-machine throughput.
- **Screenshots**: architecture diagram (README mermaid); UI answering Q1 from the evaluation set with a citation expanded.
- **Data**: model download size (M§5); average query time on Mac M2 (M§3); evaluation score for 14B (M§4).

## Article 2 — Building the whole system with a Claude Code cloud session for about USD 7

- **Target readers**: Engineers curious about AI coding agents; people who want a realistic cost and quality report, not hype.
- **Key sections**:
  1. The prompt: requirements, constraints and acceptance criteria (tests pass, `docker compose config` valid, README complete, PR).
  2. What the agent produced: backend, chunker, tests, Dockerfiles, UI, scripts and docs.
  3. How it verified itself: unit tests with fakes, and an end-to-end run with real Qdrant plus a fake Ollama server.
  4. The bug only the end-to-end run caught (`text-dense` vector name), and why that is a lesson about testing, not about AI.
  5. Where a human still mattered: the architecture constraints, reviewing the PR, running on real hardware.
  6. Cost breakdown and what I would prompt differently next time.
- **Screenshots**: PR #1 file list; the test run output (50 passed); the devlog problem section.
- **Data**: development cost ≈ USD 7 (M§1); 50 unit tests (M§6); bugs caught only by end-to-end (M§6); lines of code {待填}.

## Article 3 — Docker on a Mac can't use the GPU? Lessons from deploying a local LLM

- **Target readers**: Developers running LLMs locally on Apple Silicon, and DevOps people supporting mixed Mac/Linux teams.
- **Key sections**:
  1. The trap: "just add Ollama to docker-compose".
  2. Why: Docker Desktop runs a Linux VM, and Metal is not exposed to it (ADR 0002).
  3. Measured impact: CPU-in-Docker vs. native Metal speed.
  4. Connecting containers to the host: `host.docker.internal` on Mac vs. `host-gateway` plus `OLLAMA_HOST=0.0.0.0` on Linux (ADR 0006, devlog 2026-11-01).
  5. Security notes: never expose 11434 publicly; private Codespaces ports; security groups.
  6. One compose file for Mac, Codespaces and an EC2 GPU instance.
- **Screenshots**: `ollama ps` showing GPU usage; `/health` before and after the Linux fix; Codespaces Ports panel with 11434 private.
- **Data**: tokens/s with CPU vs. Metal (M§5, still to be measured); first-query load time (M§3).

## Article 4 — 3B vs. 14B vs. 32B local models: real-world measurements

- **Target readers**: Anyone choosing a local model size for their hardware.
- **Key sections**:
  1. Test setup: same sample project, same 10 questions, same `top_k` and `num_ctx`.
  2. Memory math: weights + KV cache, and why 32B is borderline on 32 GB (ADR 0005).
  3. Speed: tokens/s, first-query load, average query time.
  4. Quality: correctness, citation accuracy, and the hallucination trap (Q10).
  5. Where each size fails, with concrete examples from the sample project.
  6. Recommendation by hardware tier, and the cost of a GPU instance for 32B.
- **Screenshots**: the same question answered by 3B / 14B / 32B side by side; Activity Monitor memory pressure with 32B.
- **Data**: the full model comparison table (M§5); evaluation results per model (M§4); GPU instance cost (M§1).

## Article 5 — How to evaluate RAG answer quality

- **Target readers**: Engineers who built a RAG prototype and want to know if it is actually good.
- **Key sections**:
  1. Why "it looks right" fails.
  2. Build a question set: expected facts, expected citations, a trick question (`docs/evaluation/questions.md`).
  3. Score retrieval and generation separately; citation correctness as a cheap, strong signal.
  4. Track latency together with quality.
  5. Use the set as a regression test when changing chunking, `top_k` or models.
  6. Next steps: LLM-as-judge, automated runs in CI, recall@k from logged retrievals.
- **Screenshots**: a filled score sheet; one correct answer and one hallucinated answer for comparison.
- **Data**: score per model (M§4); the effect of changing `top_k` or `CHUNK_MAX_CHARS` on the score, if tested ({待填}).

## Article 6 — Improving RAG retrieval with data

- **Target readers**: Engineers whose RAG prototype "sort of works" and who want to improve retrieval step by step without guessing.
- **Thesis**: change one thing at a time and let the evaluation set decide. Each step fixes one named failure and has its own metric.
- **Key sections** (each step: the failure it targets → the change → the metric → the result):
  1. **Baseline** (vector only, `TOP_K=4`): the failure — 定位設定 questions retrieve docs, not the defining code; the trick question sometimes gets an invented answer. Metrics: Defining file retrieved, Docs among retrieved chunks, Trick question refused, Manual correctness, time to first token (M§4a group A).
  2. **Hybrid retrieval** (BM25 + identifier + RRF, ADR 0013): for questions that name an identifier. Metrics: Defining file retrieved on the identifier set, Code file retrieved; `matched_by` to show which channel found it (group B).
  3. **Split retrieval** (docs ≤ 1, ADR 0013): docs crowding out code. Metrics: Docs among retrieved chunks ↓, Code / Defining file retrieved ↑, correctness on doc-heavy questions unchanged (groups C, D).
  4. **Similarity threshold** (ADR 0014): the trick question. Calibration table from `calibrate_threshold.py` (expected excerpts dropped vs. others blocked per candidate; why not 0.70); then Q10 refused, Refused by SCORE_THRESHOLD, Expected-file recall unchanged, time saved by not calling the LLM (group G).
  5. **Rerank** (ADR 0015): ordering within the candidates. Metrics: Defining file retrieved / cited ↑, Manual correctness ↑, **rerank time vs. first-token time**; model choice table (v2-m3 vs. base vs. MiniLM, metrics §4b); image size cost (+1.5 GB, §6) (groups H, I).
  6. What did not help, what was kept off by default, and why (the "decision rule" of the experiment plan).
- **Figures**: one chart of Defining file retrieved and Manual correctness across groups A → I; the calibration score distribution (expected vs. other); a latency stack (retrieval / rerank / first token).
- **Data**: all from `docs/metrics.md` §4a, §4b, §6 ({待填} until the experiment plan has been run).

## Publishing checklist (each article)

- [ ] All code and screenshots come from the sample project or this repo.
- [ ] Every number is copied from `metrics.md`, with its environment stated.
- [ ] The ADRs and devlogs it is based on are linked.
- [ ] Cross-posted links are added back here.

---

# 系列文章規劃

> 隱私：文章中所有的範例、截圖與數字，都來自範例專案（`examples/sample-game-frontend/`）或本 repo。不得出現公司的程式碼、檔名或架構。
> 數據代號（M§n）指的是 [`../metrics.md`](../metrics.md) 的章節。

## 第 1 篇 — 為什麼做地端 codebase RAG

- **目標讀者**：前端與遊戲開發者，以及想要「直接問程式碼」又不想把程式碼送上雲端的技術主管。
- **重點段落**：
  1. 問題：新人常見的問題（「X 在哪裡設定？」），以及 grep 的極限。
  2. 為什麼不直接用雲端 AI 助手：隱私、成本難以預估、團隊需要共用的工具（ADR 0001）。
  3. 一張圖說明 RAG：索引階段與查詢階段。
  4. 架構：主機上的 Ollama，加上 Docker 裡的 Qdrant／FastAPI + LlamaIndex／React。
  5. 「好的回答」長什麼樣子：附上可點擊的 `檔案:行號` 引用。
  6. 限制：14B 地端模型與頂尖模型的差距，以及單機的吞吐量。
- **截圖**：架構圖（README 的 mermaid）；介面回答評估題第 1 題並展開引用。
- **數據**：模型下載大小（M§5）；Mac M2 的平均查詢時間（M§3）；14B 的評估分數（M§4）。

## 第 2 篇 — 用 Claude Code 雲端工作階段約 7 美元建出整套系統

- **目標讀者**：對 AI coding agent 有興趣的工程師；想看實際成本與品質報告、而不是炒作的人。
- **重點段落**：
  1. 提示詞：需求、限制與驗收條件（測試通過、`docker compose config` 驗證無誤、README 完整、開 PR）。
  2. Agent 產出了什麼：後端、切塊器、測試、Dockerfile、介面、腳本與文件。
  3. 它怎麼驗證自己：用假物件的單元測試，以及用真實 Qdrant 加假 Ollama server 的端到端測試。
  4. 只有端到端測試抓到的問題（`text-dense` 向量名稱），以及為什麼這是測試的教訓，而不是 AI 的問題。
  5. 仍然需要人的地方：架構限制、審查 PR、在真實硬體上執行。
  6. 成本拆解，以及下次會怎麼改寫提示詞。
- **截圖**：PR #1 的檔案清單；測試結果（50 passed）；devlog 的問題段落。
- **數據**：開發成本約 7 美元（M§1）；50 個單元測試（M§6）；只有端到端抓到的問題數（M§6）；程式碼行數 {待填}。

## 第 3 篇 — Mac Docker 用不到 GPU？地端 LLM 部署踩坑紀錄

- **目標讀者**：在 Apple Silicon 上跑地端 LLM 的開發者，以及支援 Mac／Linux 混合團隊的 DevOps。
- **重點段落**：
  1. 陷阱：「把 Ollama 加進 docker-compose 就好」。
  2. 原因：Docker Desktop 跑的是 Linux VM，Metal 不會開放給它（ADR 0002）。
  3. 實測影響：Docker 內 CPU 與原生 Metal 的速度差異。
  4. 容器連到主機：Mac 的 `host.docker.internal`，對比 Linux 的 `host-gateway` 加 `OLLAMA_HOST=0.0.0.0`（ADR 0006、devlog 2026-11-01）。
  5. 資安提醒：不要公開 11434；Codespaces 的 port 維持 private；設定 security group。
  6. 一個 compose 檔同時支援 Mac、Codespaces 與 EC2 GPU 機器。
- **截圖**：`ollama ps` 顯示 GPU 使用情況；Linux 修正前後的 `/health`；Codespaces Ports 面板中 11434 為 private。
- **數據**：CPU 與 Metal 的 tokens/s（M§5，尚待量測）；第一次查詢的載入時間（M§3）。

## 第 4 篇 — 3B vs 14B vs 32B 地端模型實測

- **目標讀者**：要依自己的硬體挑選地端模型大小的人。
- **重點段落**：
  1. 測試設定：同一個範例專案、同樣 10 題、同樣的 `top_k` 與 `num_ctx`。
  2. 記憶體計算：權重 + KV cache，以及為什麼 32B 在 32GB 上很勉強（ADR 0005）。
  3. 速度：tokens/s、第一次載入、平均查詢時間。
  4. 品質：正確性、引用正確率、幻覺陷阱題（第 10 題）。
  5. 各尺寸在哪裡失敗，並用範例專案的具體例子說明。
  6. 依硬體等級給建議，以及租 GPU 機器跑 32B 的成本。
- **截圖**：3B／14B／32B 回答同一題的並排比較；跑 32B 時活動監視器的記憶體壓力。
- **數據**：完整的模型比較表（M§5）；各模型評估結果（M§4）；GPU 機器費用（M§1）。

## 第 5 篇 — 如何評估 RAG 回答品質

- **目標讀者**：已經做出 RAG 原型、想知道它到底好不好的工程師。
- **重點段落**：
  1. 為什麼「看起來是對的」不夠。
  2. 建立題組：預期事實、預期引用、一題陷阱題（`docs/evaluation/questions.md`）。
  3. 把檢索與生成分開評分；引用是否正確是便宜又有效的訊號。
  4. 品質和回應時間一起追蹤。
  5. 調整切塊、`top_k` 或模型時，把題組當成回歸測試。
  6. 下一步：LLM-as-judge、在 CI 中自動執行、從檢索紀錄計算 recall@k。
- **截圖**：填好的計分表；一則正確回答與一則幻覺回答的對比。
- **數據**：各模型分數（M§4）；調整 `top_k` 或 `CHUNK_MAX_CHARS` 對分數的影響（如有測試，{待填}）。

## 第 6 篇 — 用數據改善 RAG 檢索

- **目標讀者**：RAG 原型「大致能用」、想一步一步改善檢索而不是靠猜的工程師。
- **主軸**：一次只改一件事，讓評估題組來決定。每一步解決一個具體的失敗，並有自己的指標。
- **重點段落**（每一步：要解決的失敗 → 改動 → 指標 → 結果）：
  1. **基準線**（只有向量檢索、`TOP_K=4`）：失敗——「定位設定」題取回的是文件而不是定義的程式碼；陷阱題有時會得到編造的回答。指標：定義檔命中、取回片段中文件比例、陷阱題正確拒答、人工判定正確性、首字延遲（M§4a A 組）。
  2. **混合檢索**（BM25 + 識別字 + RRF，ADR 0013）：處理寫出識別字的問題。指標：識別字題組的定義檔命中、程式碼檔命中；用 `matched_by` 說明是哪個通道找到的（B 組）。
  3. **分類取回**（文件 ≤ 1，ADR 0013）：文件擠掉程式碼。指標：取回片段中文件比例 ↓、程式碼檔／定義檔命中 ↑、重點在文件的題目正確性不變（C、D 組）。
  4. **相似度門檻**（ADR 0014）：處理陷阱題。`calibrate_threshold.py` 的校準表（每個候選值丟掉的正確片段 vs. 擋掉的其他片段；為什麼不用 0.70）；接著是 Q10 拒答、因門檻直接拒答、預期檔案命中率不變、不呼叫 LLM 省下的時間（G 組）。
  5. **Rerank**（ADR 0015）：候選內的排序。指標：定義檔命中／引用 ↑、人工判定正確性 ↑、**rerank 耗時與首字延遲的比較**；模型選擇表（v2-m3 vs. base vs. MiniLM，metrics §4b）；映像檔大小成本（+1.5 GB，§6）（H、I 組）。
  6. 哪些沒有幫助、哪些維持預設關閉，以及原因（實驗計畫的「決策規則」）。
- **圖表**：A → I 各組的定義檔命中與人工判定正確性折線圖；校準的分數分布（預期 vs. 其他）；延遲堆疊圖（檢索／rerank／首字）。
- **數據**：全部取自 `docs/metrics.md` §4a、§4b、§6（實驗計畫跑完前為 {待填}）。

## 發布前檢查（每篇）

- [ ] 所有程式碼與截圖都來自範例專案或本 repo。
- [ ] 所有數字都從 `metrics.md` 複製，並註明環境。
- [ ] 附上依據的 ADR 與 devlog 連結。
- [ ] 轉貼到其他平台的連結補回這裡。
