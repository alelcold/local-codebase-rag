# 0015. Cross-encoder rerank, optional and lazily loaded

- **Status**: Accepted (ships **off**: `RERANK=false`, and the default image does not contain the dependencies; see [experiment plan](../evaluation/experiment-plan-retrieval.md) groups H and I)
- **Date**: 2026-11-02
- **Related**: ADR [0013](0013-hybrid-retrieval-and-split-retrieval.md) (hybrid / split retrieval, switch architecture), ADR [0014](0014-similarity-threshold.md) (threshold), ADR [0002](0002-ollama-outside-docker-on-mac.md) (no GPU in Docker on a Mac), measurements in [`docs/metrics.md`](../metrics.md) §4b and §6, code `backend/app/rerank.py`

> English first; 繁體中文版本在下方. Privacy: illustrate only with the sample project.

## Context

Embedding search is a **bi-encoder**: the question and each chunk are embedded separately, and similarity is a dot product of two vectors computed independently. It is fast enough to search everything, but coarse: it cannot see *how* a chunk relates to the question. A **cross-encoder** reads the question and one chunk together and outputs a relevance score. It is much more accurate per pair, but needs a full transformer pass per pair, so it can only re-order a short list. Retrieve-then-rerank is the standard way to combine them.

For this project the ranking problem is visible in 定位設定 questions: the code that defines a value is often retrieved, but below the docs that talk about it, and with `TOP_K=4` it falls out (ADR 0013). A reranker could move it into the excerpts the model reads.

Constraints:

- The backend runs **on CPU** everywhere: in Docker on a Mac there is no GPU (ADR 0002), and Codespaces / CI have none. Ollama keeps the GPU on the Mac.
- Questions are Chinese, code is English: the model must handle both.
- The default install, CI, and anyone not using rerank must not pay for it in image size, startup time or memory.

## Decision

1. **Switches** (ADR 0013 pattern, all in `.env`, off by default): `RERANK=false`, `RERANK_MODEL=BAAI/bge-reranker-base`, `RERANK_CANDIDATES=10`, `RERANK_TOP_N=3`, plus `RERANK_MAX_LENGTH=512` (tokens per pair, the main CPU cost knob). `/health` reports them under `retrieval` and the reranker state under `reranker` (`installed`, `loaded`); `evaluate.py` and `compare.py` show them.
2. **Flow.** Retrieve `RERANK_CANDIDATES` excerpts with the current settings, score each (question, excerpt) pair with the cross-encoder, keep the best `RERANK_TOP_N` for the LLM. The cross-encoder sees `file path + symbol` followed by the chunk text. With rerank on, `RERANK_TOP_N` replaces `TOP_K` as the default number of excerpts (`/health` reports it as `top_k`, so the UI starts there); a `top_k` in the request still wins, and candidates are never fewer than it.
3. **Order of the pipeline** (in `RagService.retrieve_detailed`):
   1. vector search (+ BM25 + identifier with `HYBRID_SEARCH`);
   2. `SCORE_THRESHOLD` on vector cosines (ADR 0014) — if nothing is left, stop: no rerank, no LLM;
   3. RRF fusion;
   4. **`SPLIT_RETRIEVAL` selects the candidates**: `RERANK_CANDIDATES` items with at most `DOC_TOP_K` docs;
   5. **rerank** those candidates, keep `RERANK_TOP_N`;
   6. with `SPLIT_RETRIEVAL`, re-group code first (each group in rerank order).

   **Split before rerank**, because split exists to stop docs from crowding out code *in what the model reads*. Docs crowd the candidate pool too (they are written in the question's language, so both the bi-encoder and the cross-encoder like them); if rerank ran first on an unsplit pool, a few doc sections could again take every slot, and splitting afterwards would only have the reranker's survivors to choose from. Splitting first guarantees the doc cap (at most `DOC_TOP_K` of the final excerpts, since at most that many candidates are docs) and lets the cross-encoder spend its passes choosing *which code*. Step 6 keeps split's "code first" contract.
4. **Model choice: `BAAI/bge-reranker-base`, not `bge-reranker-v2-m3`.** v2-m3 (568M parameters, multilingual) is the stronger model and was the first candidate, but measured on 4 x86 vCPUs (metrics §4b) it needs **12.0 s** for 10 pairs at 512 tokens and 2.8 GB RAM, which is too slow when it is added to every query before the first token. `bge-reranker-base` (278M, trained on Chinese and English) needs **3.7 s** and 1.9 GB. v2-m3 at 256 tokens (5.5 s) was rejected because chunks are up to 3000 characters: 256 tokens would cut most of a code chunk, including names further down. `mmarco-mMiniLMv2-L12-H384-v1` (1.0 s) is the fallback for slower machines; v2-m3 remains one `.env` line away for machines with spare CPU.
5. **Candidates 10, top N 3.** 10 pairs keeps rerank at a few seconds on CPU (cost is linear in candidates), while still reaching well past `TOP_K=4`, where the defining code tends to sit. 3 excerpts keep the prompt short for small models. In the experiment plan, H and I use `RERANK_TOP_N=4` so they send as many excerpts as the other groups.
6. **Lazy, optional, cached:**
   - Dependencies (`torch` CPU wheel, `sentence-transformers`, `transformers`) are installed only with the build argument **`INSTALL_RERANK=true`**. Measured: image **616 MB → 2.14 GB** (+1.5 GB). `torch` comes from the CPU wheel index; the default PyPI wheel for Linux x86_64 bundles CUDA and is several GB larger.
   - `services.assemble` creates a `CrossEncoderReranker` only when `RERANK=true`; it imports nothing heavy. The model is loaded on the **first query that needs it** (thread-safe, once). With `RERANK=false` nothing is imported or loaded: startup time and memory are unchanged (a unit test checks `sentence_transformers` is never imported).
   - The model is cached under `HF_HOME=/models/hf`, a named volume `reranker_models`, so it is downloaded once, not per container rebuild.
   - `RERANK=true` in an image without the dependencies: `/health` is `degraded` with `reranker.installed: false`, and queries fail with a message that says how to rebuild.
7. **Latency is reported.** The stream's `done` event carries `rerank_seconds` (scoring only) and `rerank_load_seconds` (only on the query that loaded the model); the UI shows them next to the timing line; `evaluate.py` records them per question and as "Rerank time, mean"; `compare.py` compares them.
8. **Tests** use a fake reranker (`FakeReranker` in `tests/conftest.py`): no download, no torch. CI's smoke test keeps `RERANK=false` and the default image.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| `BAAI/bge-reranker-v2-m3` as default | Best quality of those tried; multilingual | 12.0 s / 10 pairs and 2.8 GB RAM on 4 vCPU; 2.2 GB download | Too slow for every query on CPU; kept as an option |
| `bge-reranker-v2-m3` with `RERANK_MAX_LENGTH=256` | 5.5 s | Truncates code chunks to their first ~200 tokens | Loses exactly the declarations further down a chunk |
| `mmarco-mMiniLMv2-L12-H384-v1` | 1.0 s, 470 MB | Trained on translated MS MARCO (web passages), weakest on code | Fallback for slow machines |
| LLM as reranker (ask Ollama to score) | No new dependency | One LLM call per candidate or a long listwise prompt: minutes on CPU | Far slower than a cross-encoder |
| Rerank before split | The cross-encoder sees every type | Docs can retake every slot; split would only see the reranker's survivors | Split first, then rerank (see Decision 3) |
| Rerank the whole fused pool (30) | Higher recall ceiling | Linear cost: ~3× the time | 10 is a good cost/benefit start; tunable |
| Always install the dependencies | One image | +1.5 GB for everyone, including CI and users who never enable it | Build argument instead |
| ONNX / quantised cross-encoder (`optimum`, `fastembed`) | Faster on CPU, smaller | Another runtime and model export path to maintain; model choice limited | Revisit if rerank is turned on by default |
| Load the model at startup | First query not slower | Startup time and memory for a switch that might never be used per process; download blocks startup | Lazy load, load time reported separately |

## Consequences

- **Positive**: A precise relevance signal can be switched on and measured like the other switches, at zero cost when off. The split/rerank order keeps the "docs never crowd out code" guarantee. Latency is visible in every report.
- **Negative / trade-offs**:
  - About +4 s per query on a 4-vCPU machine with the default model (more with v2-m3), plus a one-off download (~1 GB) and model load (~8 s) on first use.
  - The rerank image is 2.14 GB instead of 616 MB, and needs a separate build (`INSTALL_RERANK=true docker compose build backend`).
  - About +1.9 GB RAM in the backend while the model is loaded (it stays loaded for the process lifetime). On a Mac this counts against Docker Desktop's memory limit, not the GPU's unified memory used by Ollama.
  - With rerank, `source.score` stays the retrieval score; the cross-encoder's score is `rerank_score` (a sigmoid output, not comparable with cosine).
  - `bge-reranker-base` is weaker than v2-m3; group H measures whether it is good enough.
- **Follow-ups**: Run groups H and I; record rerank time and correctness in `docs/metrics.md` §4a and Mac numbers in §4b. If rerank wins, consider an ONNX/quantised build before making it a default, and a reranker-score threshold as a second refusal signal.

---

# 0015. Cross-encoder Rerank：選用、延遲載入

- **狀態**：已接受（預設**關閉**：`RERANK=false`，預設映像檔也不含相關依賴；見[實驗計畫](../evaluation/experiment-plan-retrieval.md) H、I 組）
- **日期**：2026-11-02
- **相關**：ADR [0013](0013-hybrid-retrieval-and-split-retrieval.md)（混合檢索／分類取回、開關架構）、ADR [0014](0014-similarity-threshold.md)（門檻）、ADR [0002](0002-ollama-outside-docker-on-mac.md)（Mac 的 Docker 沒有 GPU）、量測見 [`docs/metrics.md`](../metrics.md) §4b 與 §6、程式碼 `backend/app/rerank.py`

## 背景

向量檢索是 **bi-encoder**：問題與每個片段分別轉成向量，相似度是兩個獨立算出的向量的內積。速度快到可以搜尋全部片段，但比較粗略：看不到片段「如何」回答問題。**Cross-encoder（交叉編碼器）** 把問題和一個片段一起讀進模型，輸出一個相關性分數。每一組都準確得多，但每組都要完整跑一次 transformer，所以只能用來重新排序一小段清單。「先檢索、再 rerank」是結合兩者的標準做法。

本專案的排序問題在「定位設定」題目上很明顯：定義數值的程式碼常常有被取回，但排在談論它的文件後面，`TOP_K=4` 時就被擠出去（ADR 0013）。Reranker 有機會把它排進模型會讀到的片段中。

限制：

- backend 在所有環境都**跑在 CPU 上**：Mac 的 Docker 沒有 GPU（ADR 0002），Codespaces／CI 也沒有。Mac 的 GPU 留給 Ollama。
- 問題是中文、程式碼是英文：模型必須兩種都懂。
- 預設安裝、CI、以及不用 rerank 的人，不能在映像檔大小、啟動時間或記憶體上為它付出代價。

## 決策

1. **開關**（沿用 ADR 0013 的模式，全在 `.env`，預設關閉）：`RERANK=false`、`RERANK_MODEL=BAAI/bge-reranker-base`、`RERANK_CANDIDATES=10`、`RERANK_TOP_N=3`，另加 `RERANK_MAX_LENGTH=512`（每組的 token 上限，是 CPU 成本的主要參數）。`/health` 在 `retrieval` 下回報這些設定，在 `reranker` 下回報狀態（`installed`、`loaded`）；`evaluate.py` 與 `compare.py` 也會顯示。
2. **流程。** 依目前設定取回 `RERANK_CANDIDATES` 段，交叉編碼器為每組（問題, 片段）打分，取最好的 `RERANK_TOP_N` 段送進 LLM。交叉編碼器看到的是「檔案路徑 + 符號名稱」加上片段內容。開啟 rerank 時，`RERANK_TOP_N` 取代 `TOP_K` 作為預設片段數（`/health` 以 `top_k` 回報，介面從這個數字開始）；請求中帶的 `top_k` 仍然優先，候選數也不會少於它。
3. **流程順序**（`RagService.retrieve_detailed`）：
   1. 向量檢索（`HYBRID_SEARCH` 時加上 BM25 + 識別字）；
   2. 對向量 cosine 套用 `SCORE_THRESHOLD`（ADR 0014）——什麼都不剩就停止：不 rerank、不呼叫 LLM；
   3. RRF 合併；
   4. **`SPLIT_RETRIEVAL` 選出候選**：`RERANK_CANDIDATES` 段，其中文件最多 `DOC_TOP_K` 段；
   5. **rerank** 這些候選，保留 `RERANK_TOP_N` 段；
   6. 開啟 `SPLIT_RETRIEVAL` 時，重新分組讓程式碼在前（各組內依 rerank 順序）。

   **先分類取回、再 rerank**，因為分類取回的目的是避免文件擠掉「模型讀到的」程式碼。文件也會擠滿候選池（它們用問題的語言寫成，bi-encoder 和 cross-encoder 都偏好它們）；如果先對沒分類的候選池 rerank，幾段文件可能又占滿所有名額，事後再分類也只能從 reranker 留下的片段中挑。先分類能保證文件上限（候選中最多 `DOC_TOP_K` 段文件，最終片段當然也不會超過），並讓交叉編碼器把運算花在「挑哪些程式碼」。第 6 步維持分類取回「程式碼在前」的約定。
4. **模型選擇：`BAAI/bge-reranker-base`，而不是 `bge-reranker-v2-m3`。** v2-m3（5.68 億參數、多語言）比較強，也是第一候選，但在 4 個 x86 vCPU 上實測（metrics §4b）10 組、512 token 要 **12.0 秒**、記憶體 2.8 GB；每次查詢在首字之前都要多等這麼久，太慢。`bge-reranker-base`（2.78 億參數，以中英文訓練）只要 **3.7 秒**、1.9 GB。v2-m3 搭配 256 token（5.5 秒）也不採用：片段最長 3000 字元，256 token 會切掉大部分程式碼，包括後段的名稱。`mmarco-mMiniLMv2-L12-H384-v1`（1.0 秒）是較慢機器的備案；CPU 有餘裕的機器只要改一行 `.env` 就能用 v2-m3。
5. **候選 10、取 3。** 10 組讓 CPU 上的 rerank 維持在幾秒內（成本與候選數成正比），同時能看到 `TOP_K=4` 之外、定義程式碼常落在的位置。3 段讓小模型的提示保持精簡。實驗計畫中 H、I 組使用 `RERANK_TOP_N=4`，讓送進模型的片段數與其他組相同。
6. **延遲載入、選用安裝、快取：**
   - 依賴（`torch` CPU 版、`sentence-transformers`、`transformers`）只在建置參數 **`INSTALL_RERANK=true`** 時安裝。實測映像檔 **616 MB → 2.14 GB**（+1.5 GB）。`torch` 從 CPU 專用的 wheel 索引安裝；PyPI 上 Linux x86_64 的預設 wheel 內含 CUDA，會再大好幾 GB。
   - `services.assemble` 只有在 `RERANK=true` 時才建立 `CrossEncoderReranker`，且不 import 任何重量級套件。模型在**第一次需要它的查詢**才載入（執行緒安全，只載入一次）。`RERANK=false` 時什麼都不 import、不載入：啟動時間與記憶體不變（有單元測試確認 `sentence_transformers` 從未被 import）。
   - 模型快取在 `HF_HOME=/models/hf`，也就是具名 volume `reranker_models`，只下載一次，重建容器不會重新下載。
   - 映像檔沒有依賴卻設定 `RERANK=true`：`/health` 為 `degraded`，`reranker.installed: false`；查詢會失敗，錯誤訊息說明如何重新建置。
7. **回報延遲。** 串流的 `done` 事件帶有 `rerank_seconds`（只算打分）與 `rerank_load_seconds`（只在載入模型的那次查詢）；介面在耗時列顯示；`evaluate.py` 逐題記錄並統計「rerank 耗時平均」；`compare.py` 會比較。
8. **測試**使用假的 reranker（`tests/conftest.py` 的 `FakeReranker`）：不下載模型、不需要 torch。CI 冒煙測試維持 `RERANK=false` 與預設映像檔。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 預設 `BAAI/bge-reranker-v2-m3` | 試過的模型中品質最好；多語言 | 4 vCPU 上 10 組 12.0 秒、記憶體 2.8 GB；下載 2.2 GB | 在 CPU 上每次查詢都這樣太慢；保留為選項 |
| `bge-reranker-v2-m3` + `RERANK_MAX_LENGTH=256` | 5.5 秒 | 程式碼片段只剩前約 200 個 token | 正好丟掉片段後段的宣告 |
| `mmarco-mMiniLMv2-L12-H384-v1` | 1.0 秒、470 MB | 以翻譯的 MS MARCO（網頁段落）訓練，對程式碼最弱 | 慢機器的備案 |
| 用 LLM 當 reranker（請 Ollama 打分） | 不需新依賴 | 每個候選一次 LLM 呼叫，或很長的 listwise 提示：CPU 上要數分鐘 | 比交叉編碼器慢太多 |
| 先 rerank 再分類取回 | 交叉編碼器看得到所有類型 | 文件可能重新占滿名額；分類只能從 reranker 留下的片段挑 | 先分類、再 rerank（見決策 3） |
| rerank 整個融合後的候選池（30） | 召回上限較高 | 成本線性增加：約 3 倍時間 | 10 是成本效益不錯的起點；可調整 |
| 一律安裝依賴 | 只有一種映像檔 | 所有人（包括 CI 與從不開啟的人）都多 1.5 GB | 改用建置參數 |
| ONNX／量化的交叉編碼器（`optimum`、`fastembed`） | CPU 上更快、更小 | 多一套 runtime 與模型轉換流程要維護；模型選擇受限 | 若要預設開啟 rerank 再評估 |
| 啟動時載入模型 | 第一次查詢不會比較慢 | 每個行程都要為可能用不到的開關付出啟動時間與記憶體；下載會卡住啟動 | 延遲載入，並另外回報載入時間 |

## 後果

- **正面**：精確的相關性訊號可以像其他開關一樣開啟與量測，關閉時零成本。分類取回與 rerank 的順序維持「文件不會擠掉程式碼」的保證。每份報告都看得到延遲。
- **負面／取捨**：
  - 在 4 vCPU 的機器上，預設模型讓每次查詢多約 4 秒（v2-m3 更多），第一次使用還要下載（約 1 GB）並載入模型（約 8 秒）。
  - rerank 映像檔是 2.14 GB 而不是 616 MB，需要另外建置（`INSTALL_RERANK=true docker compose build backend`）。
  - 模型載入後 backend 多佔約 1.9 GB 記憶體（行程存活期間都不釋放）。在 Mac 上這算在 Docker Desktop 的記憶體上限，不佔 Ollama 使用的 GPU 統一記憶體。
  - 開啟 rerank 時，`source.score` 仍是檢索分數；交叉編碼器的分數是 `rerank_score`（sigmoid 輸出，不能和 cosine 比較）。
  - `bge-reranker-base` 比 v2-m3 弱；H 組會量測它是否夠用。
- **後續工作**：跑 H、I 組，把 rerank 耗時與正確性記到 `docs/metrics.md` §4a，Mac 數據記到 §4b。若 rerank 有效，在預設開啟前先評估 ONNX／量化版本，以及以 rerank 分數作為第二個拒答訊號。
