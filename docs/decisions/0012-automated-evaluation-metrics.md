# 0012. Automated evaluation: which metrics, and what they cannot tell

- **Status**: Accepted
- **Date**: 2026-11-02
- **Related**: [0007](0007-multi-environment-testing-strategy.md), [0010](0010-streaming-responses.md), [devlog 2026-11-02](../devlog/2026-11-02.md), `docs/evaluation/questions.yaml`, `scripts/evaluate.py`, `scripts/compare.py`

> English first; 繁體中文版本在下方. Privacy: illustrated only with the sample project.

## Context

`docs/evaluation/questions.md` has 10 questions with expected answers and citations, but running them meant typing each question into the UI, copying times by hand and scoring from memory. That does not scale to comparing models (3B / 14B / 32B), `TOP_K` values and environments, and it hides patterns.

The first Codespaces runs (CPU, `qwen2.5-coder:3b`, `TOP_K=4`) showed what manual testing misses:

- For 「玩家受傷後的無敵時間在哪裡設定？」 all 4 retrieved chunks were documentation (`README.md`, `docs/gameplay.md`, `docs/architecture.md`). The file that defines `INVINCIBLE_MS` (`src/config/gameConfig.ts`) was not retrieved, so the answer claimed the value was "defined in `docs/gameplay.md`".
- The answer mixed in Simplified Chinese (「具体来说」「代码」「无敵时间」).
- Asking the same question twice gave a 0.8 s time to first token instead of 30.4 s, because Ollama reused the cached prompt. A naive "average of 10 runs of the same question" would be misleading.

## Decision

1. **`docs/evaluation/questions.yaml`** is the machine-readable question set (same 10 questions as `questions.md`). Each question has a `type` (定位設定 / 解釋邏輯 / 跨檔案流程 / 陷阱題), `keywords` (each item a list of acceptable alternatives), `expected_files`, and for 定位設定 questions `definition_files`: the **code** file that defines the setting. A unit test checks that every expected file exists in the sample project and that identifier keywords really occur in the expected files.

2. **`scripts/evaluate.py`** asks every question through **`/query/stream`** (the same path the UI uses, default via nginx) and records, per question:

   | Metric | How | What it is for |
   | --- | --- | --- |
   | Time to first token, total time, tokens | Measured in the client from the request; tokens from the `done` event | Perceived speed, and generation speed separately from prompt processing |
   | Expected-file recall | Expected files among the **retrieved** sources ÷ expected files | Retrieval quality |
   | Code hit / doc hit | The same, split by extension (`.md` = doc) | Shows docs crowding out code (the Codespaces case) |
   | Definition hit (定位設定) | Is a `definition_files` entry retrieved? | "Where is X configured" must find the defining code, not only docs that mention it |
   | Answer cites an expected file | `[n]` in the answer mapped to sources | Whether the model uses the right excerpt |
   | Doc share of retrieved chunks | Share of retrieved chunks that are `.md` | Retrieval bias, independent of the expected list |
   | Keyword hit rate | Case-insensitive substring match; any alternative counts | Rough check that key facts appear |
   | Simplified characters | A list of 200 Simplified-only characters, checked to produce zero hits on this repo's Traditional docs | Language drift of small models |
   | Refusal (陷阱題) | A refusal phrase and no forbidden keyword (`WebSocket`…) | Hallucination resistance |

3. **A person still judges correctness.** The Markdown report has an empty 「人工判定正確性」 (0–2) column for every question; `--apply-manual` copies the filled-in scores into the JSON. The automatic numbers are never reported as "accuracy".

4. **Warm-up query by default**: one unscored question first loads the model, so question 1 is not penalized by model load (`--no-warmup` to measure a cold start). Questions differ from one another, so Ollama's prompt cache does not help between them.

5. **Results** go to `docs/evaluation/results/<date>-<label>.json` (full data, schema 1) and `.md` (report). **`scripts/compare.py`** prints a Markdown table of two runs (Δ = B − A, ▲/▼ where "better" is clear) for model or `TOP_K` comparisons. `docs/metrics.md` takes its numbers from these reports.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Keep manual scoring only | Human judgment on everything | Slow, inconsistent, no retrieval metrics, hard to compare runs | Does not scale; missed the docs-only retrieval |
| LLM-as-judge (a model grades answers) | Scales; closer to "correctness" than keywords | Needs a stronger model than the one under test, which on-prem means a second large model; judges are biased and need their own validation | Later, if manual scoring becomes the bottleneck; then validate it against the manual scores collected now |
| Embedding similarity to a reference answer | Tolerates paraphrase | Similar wording ≠ correct (a wrong number scores high); one more model call; hard to explain | Unclear meaning |
| RAGAS-style framework | Standard metrics (faithfulness, context recall) | Heavy dependency; most metrics need an LLM judge anyway; overkill for 10 questions | Too much for the current size |
| `/query` (non-streaming) | Simpler client | Cannot measure time to first token; not the path the UI uses | Streaming measures what users experience |
| Chunk/line-level hits instead of file-level | More precise | Line ranges change with `CHUNK_MAX_CHARS` and edits; brittle expectations | File level is stable; the report lists the exact ranges for a human |
| OpenCC for Simplified detection | Complete conversion tables | Extra dependency; characters valid in both scripts cause false positives | A conservative list with zero false positives on our docs is enough for a flag |

## Consequences

- **Positive**: One command produces comparable numbers for any environment. Retrieval and generation are scored separately, so "the model is bad" and "the model never saw the right code" can be told apart. Simplified drift and docs-only retrieval are visible per question.
- **Limitations (read before quoting a number)**:
  - **A keyword hit is not a correct answer.** An answer can contain `INVINCIBLE_MS` and `1500` and still say it is defined in the wrong file (exactly the Codespaces answer). It can also be correct in other words and miss a keyword. Keywords are a screening signal; correctness comes from the manual column.
  - **File recall measures what was retrieved, not what was used.** The model may ignore a retrieved file or cite the wrong one; "answer cites an expected file" only checks `[n]` markers, which small models often omit.
  - **The expected lists are ours.** A different chunk may also answer the question; a miss is a prompt to look, not proof of failure.
  - **Refusal detection is a phrase match.** 「沒有」 appears in many sentences; a 陷阱題 "refused" result still needs reading.
  - **The Simplified list is conservative**: it flags clear drift but does not catch every Simplified character.
  - **10 questions are a small sample**, all on one sample project. Differences of one question are noise. Timing depends on the machine and on what else runs; record the environment with every result.
  - Prompt caching: re-asking the **same** question right after itself measures cache hits (0.8 s vs 30.4 s on Codespaces), not normal latency. The script never repeats a question within a run.
- **Privacy**: results contain answers and cited paths. Only runs on the sample project may be committed; for any other project use `--out-dir` outside the repo.
- **Follow-ups**: Run the set on Codespaces with `TOP_K` 4 and 8 and on the Mac with 14B, fill in the manual column, and decide on `TOP_K` for `.env.codespaces`. Consider retrieval changes (e.g. favoring code for 定位設定 questions, hybrid keyword search for identifiers) only after the numbers show the problem consistently. Consider an LLM judge once enough manual scores exist to validate it.

---

# 0012. 自動化評估：採用哪些指標，以及它們無法告訴你什麼

- **狀態**：已接受
- **日期**：2026-11-02
- **相關**：[0007](0007-multi-environment-testing-strategy.md)、[0010](0010-streaming-responses.md)、[devlog 2026-11-02](../devlog/2026-11-02.md)、`docs/evaluation/questions.yaml`、`scripts/evaluate.py`、`scripts/compare.py`

## 背景

`docs/evaluation/questions.md` 有 10 題，附預期答案與引用，但執行時要把每題手動輸入介面、手抄時間、憑印象評分。要比較不同模型（3B／14B／32B）、`TOP_K` 與環境時，這樣做不但跟不上，也看不出規律。

在 Codespaces（CPU、`qwen2.5-coder:3b`、`TOP_K=4`）的前幾次測試，就暴露了手動測試容易漏掉的問題：

- 問「玩家受傷後的無敵時間在哪裡設定？」時，取回的 4 段全是文件（`README.md`、`docs/gameplay.md`、`docs/architecture.md`）。真正定義 `INVINCIBLE_MS` 的 `src/config/gameConfig.ts` 沒有被取回，所以回答說這個值「在 `docs/gameplay.md` 中定義」。
- 回答混入了簡體字（「具体来说」「代码」「无敵时间」）。
- 同一題連問兩次，首字延遲從 30.4 秒變成 0.8 秒，因為 Ollama 重用了快取的提示詞。如果只是「同一題問 10 次取平均」，數字會誤導。

## 決策

1. **`docs/evaluation/questions.yaml`** 是機器可讀的題組（與 `questions.md` 相同的 10 題）。每題有 `type`（定位設定／解釋邏輯／跨檔案流程／陷阱題）、`keywords`（每一項是可接受的替代寫法清單）、`expected_files`；定位設定題另有 `definition_files`，也就是實際定義該設定的**程式碼**檔。單元測試會檢查每個預期檔案都存在於範例專案，而且識別字類的關鍵字確實出現在預期檔案中。

2. **`scripts/evaluate.py`** 透過 **`/query/stream`**（和介面相同的路徑，預設經過 nginx）依序詢問每一題，並記錄每題的：

   | 指標 | 計算方式 | 用途 |
   | --- | --- | --- |
   | 首字延遲、總耗時、token 數 | 在用戶端從送出請求開始量測；token 數取自 `done` 事件 | 使用者感受到的速度，並把生成速度和提示詞處理分開 |
   | 預期檔案命中率 | 被**取回**的來源中有幾個預期檔案 ÷ 預期檔案數 | 檢索品質 |
   | 程式碼檔命中／文件檔命中 | 同上，依副檔名分開（`.md` 算文件） | 看出文件把程式碼擠掉的情況（Codespaces 的例子） |
   | 定義檔命中（定位設定） | 是否取回 `definition_files` 中的檔案 | 問「X 在哪裡設定」時，必須找到定義它的程式碼，而不只是提到它的文件 |
   | 回答引用預期檔案 | 把回答中的 `[n]` 對應到來源 | 模型有沒有用到正確的片段 |
   | 取回片段中文件的比例 | 取回片段中 `.md` 的比例 | 不依賴預期清單的檢索偏差 |
   | 關鍵字命中率 | 不分大小寫的子字串比對；任一替代寫法都算 | 粗略確認關鍵事實有出現 |
   | 簡體字 | 200 個只存在於簡體的字；已確認在本 repo 的繁體文件上零誤判 | 小模型的語言漂移 |
   | 拒答（陷阱題） | 出現拒答用語，且沒有禁用關鍵字（`WebSocket`…） | 抗幻覺能力 |

3. **正確性仍由人判定**：Markdown 報告每題都有空白的「人工判定正確性」（0–2）欄位；`--apply-manual` 會把填好的分數寫回 JSON。自動計算的數字絕不當作「正確率」報告。

4. **預設先送一題暖機問題**：先用一題不計分的問題載入模型，第 1 題就不會因為載入模型而吃虧（要量冷啟動時用 `--no-warmup`）。題目彼此不同，所以 Ollama 的提示詞快取在題目之間幫不上忙。

5. **結果**寫到 `docs/evaluation/results/<日期>-<label>.json`（完整資料，schema 1）與 `.md`（報告）。**`scripts/compare.py`** 會把兩次結果輸出成 Markdown 差異表（Δ = B − A，方向明確時以 ▲／▼ 標示較好或較差），用來比較模型或 `TOP_K`。`docs/metrics.md` 的數字改為取自這些報告。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 維持人工評分 | 每一題都有人判斷 | 慢、不一致、沒有檢索指標、難以比較不同次執行 | 無法擴充；漏掉了「只取回文件」的問題 |
| LLM 評審（由模型評分） | 可擴充；比關鍵字更接近「正確性」 | 需要比受測模型更強的模型，地端就得再跑一個大模型；評審本身有偏差，也需要驗證 | 等人工評分成為瓶頸再考慮，屆時用現在累積的人工分數驗證它 |
| 與參考答案比較 embedding 相似度 | 能容忍換句話說 | 措辭相似 ≠ 正確（數字錯了分數仍很高）；多一次模型呼叫；難以解釋 | 意義不明確 |
| RAGAS 之類的框架 | 標準指標（faithfulness、context recall） | 依賴很重；多數指標本來就需要 LLM 評審；10 題用不到 | 目前規模用不到 |
| 使用 `/query`（非串流） | 用戶端比較簡單 | 量不到首字延遲；不是介面走的路徑 | 串流量到的才是使用者的感受 |
| 以片段／行號為單位判斷命中 | 更精確 | 行號會隨 `CHUNK_MAX_CHARS` 與程式修改而變；預期值容易失效 | 以檔案為單位比較穩定；報告會列出實際行號給人看 |
| 用 OpenCC 偵測簡體 | 完整的轉換表 | 多一個依賴；兩種字體都合法的字會造成誤判 | 對我們的文件零誤判的保守字表，已足夠作為警示 |

## 後果

- **正面**：一個指令就能在任何環境產生可比較的數字。檢索和生成分開評分，能分辨「模型不好」還是「模型根本沒看到正確的程式碼」。每題都看得到簡體漂移與只取回文件的情況。
- **限制（引用數字前請先讀）**：
  - **關鍵字命中不等於回答正確。** 回答可能同時包含 `INVINCIBLE_MS` 和 `1500`，卻說它定義在錯的檔案（正是 Codespaces 那次的回答）；也可能用別的說法答對，卻沒有命中關鍵字。關鍵字只是篩選訊號，正確性以人工欄位為準。
  - **檔案命中率量的是「取回了什麼」，不是「用了什麼」。** 模型可能忽略取回的檔案，或引用錯的檔案；「回答引用預期檔案」只檢查 `[n]` 標記，而小模型常常不寫。
  - **預期清單是我們自己定的。** 其他片段也可能回答得了問題；沒命中是提醒要去看，不是失敗的證明。
  - **拒答偵測只是比對用語。** 「沒有」會出現在很多句子裡；陷阱題顯示「已拒答」仍需要人讀過。
  - **簡體字表很保守**：能抓到明顯的漂移，但不會抓到每一個簡體字。
  - **10 題是很小的樣本**，而且全部來自同一個範例專案，差一題的差異屬於雜訊。耗時取決於機器與同時執行的其他工作；每筆結果都要記下環境。
  - 提示詞快取：同一題緊接著再問一次，量到的是快取命中（Codespaces 上是 0.8 秒對 30.4 秒），不是一般的延遲。腳本在同一次執行中不會重複問同一題。
- **隱私**：結果包含回答與引用的路徑。只有範例專案的結果可以提交；其他專案請用 `--out-dir` 寫到 repo 以外的地方。
- **後續工作**：在 Codespaces 以 `TOP_K` 4 與 8、在 Mac 以 14B 跑這組題目，填好人工欄位，再決定 `.env.codespaces` 的 `TOP_K`。等數字穩定顯示問題後，才考慮調整檢索（例如定位設定題優先取回程式碼、用混合關鍵字搜尋處理識別字）。累積足夠人工分數後，再考慮 LLM 評審。
