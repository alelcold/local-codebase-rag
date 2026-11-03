# 0014. Similarity threshold on the vector channel, with a fixed "not found" answer

- **Status**: Accepted (ships **off**: `SCORE_THRESHOLD` is empty by default; a value is set only after calibration, see [experiment plan](../evaluation/experiment-plan-retrieval.md) group G)
- **Date**: 2026-11-02
- **Related**: ADR [0013](0013-hybrid-retrieval-and-split-retrieval.md) (switch architecture, RRF), ADR [0012](0012-automated-evaluation-metrics.md) (evaluation), ADR [0015](0015-rerank.md) (rerank), code `backend/app/rag.py` (`retrieve_detailed`), `scripts/calibrate_threshold.py`

> English first; 繁體中文版本在下方. Privacy: illustrate only with the sample project.

## Context

Retrieval always returns `TOP_K` excerpts, however unrelated they are. For question 10 of `questions.yaml` (「線上多人模式怎麼同步玩家位置？」 — the sample project has no multiplayer code), the model still receives four excerpts about the player and the game loop, and a small model is tempted to build an answer from them. The prompt says "if the excerpts do not contain the answer, say so", but a 3B model does not always obey; whether it refuses depends on the run.

We want a retrieval-side guard: if nothing retrieved is actually similar to the question, do not ask the LLM at all.

Facts that shape the design:

- With `nomic-embed-text` the cosine similarities are compressed: a **relevant** Markdown excerpt has been measured at only **0.60**. The commonly quoted 0.70 would have dropped it. The right value depends on the embedding model, the prefixes, the language mix (Chinese questions, English code) and whether `CHUNK_METADATA` is on.
- With `HYBRID_SEARCH=true`, `source.score` is an RRF score (≈ 0.016–0.05, based on rank only). It says nothing about absolute relevance and cannot be compared with a threshold.
- An exact identifier in the question (`INVINCIBLE_MS`) is strong evidence even when the cosine is low (ADR 0013: vector search is weak on identifiers).

## Decision

1. **`SCORE_THRESHOLD`** (default empty = no filtering) is applied to the **vector channel's cosine similarity only**, and **before RRF fusion**. Vector hits below it are removed from the vector ranking; the remaining ones keep their order.
2. With `HYBRID_SEARCH=true`:
   - the **identifier channel** (chunks that define a name spelled out in the question) is **never filtered** — that is exact evidence;
   - a **keyword (BM25) hit** is kept only if its vector hit passed the threshold **or** its text contains an exact identifier from the question (`contains_identifier`: whole word, case-sensitive). Otherwise plain words such as "player" would let anything through and the trick question in English would never be refused.
3. If nothing is left, the backend **does not call the LLM** and answers with a fixed Traditional Chinese text (`NO_RELEVANT_ANSWER`): 「在目前索引的專案中找不到與這個問題相關的內容…」, with an empty source list. `/query` and `/query/stream` behave the same (the stream sends `sources: []`, the text as one `token`, then `done` with `no_relevant: true` and `below_threshold: N`). The text contains 「找不到」, which `evaluate.py` counts as a refusal for the trick question.
4. **No default value.** `scripts/calibrate_threshold.py` reads the evaluation reports (A–F of the experiment plan) and, per embedding (model, with / without `CHUNK_METADATA`), prints the cosine distribution of excerpts from **expected** and **not expected** files, and for each candidate threshold how many expected excerpts it drops, how many others it blocks, which questions would lose all their expected excerpts, and whether the trick question would be refused. It suggests the highest candidate that keeps an expected excerpt for every question and drops at most 5 % of them — or says the data is insufficient and suggests nothing.
5. To make calibration possible, every source now carries **`vector_score`** (the cosine, `null` if only keyword / identifier search found it) and `rerank_score`; `evaluate.py` records them with `matched_by` in the JSON report. Older reports are still usable when hybrid search was off (`score` was the cosine then).
6. Observability as in ADR 0013: `/health` → `retrieval.score_threshold`; the report header and `compare.py` show it; the report counts "Refused by SCORE_THRESHOLD (LLM not called)".

**top_p.** `LLM_TEMPERATURE` is already 0.1. At that temperature the distribution is so peaked that nucleus sampling (`top_p`) removes almost nothing that temperature has not already made negligible: the two knobs overlap. A `top_p` switch would add a variable to every experiment without a measurable effect, so none is added. Hallucination is addressed where it starts — what the model is given to read.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Fixed default 0.70 | Common in tutorials; works out of the box | Model-specific: with `nomic-embed-text` a relevant Markdown excerpt scored 0.60 and would be dropped, i.e. correct answers turn into refusals | Calibrate per model instead; ship empty |
| Threshold on the fused score | One number for every mode | RRF scores come from ranks, not similarity: the top item always gets ≈ 1/(k+1), relevant or not | Meaningless as a relevance cut |
| Threshold after fusion on each item's cosine | Same effect for vector-only | Items found only by BM25 / identifier have no cosine; decides after the fused ranks were computed with items that should not count | Filtering before fusion keeps ranks honest |
| Apply the threshold to every channel, including identifiers | Simple rule | Drops exactly the case hybrid search exists for: `INVINCIBLE_MS` defined in a chunk whose cosine is low | Exact identifier evidence is exempt |
| Let the LLM decide (stronger "say not found" prompt) | No extra setting | Small models do not reliably obey; costs a full LLM call (minutes on CPU) to produce a refusal | Prompt rule stays as a second line of defence |
| Relative cut (drop hits below X % of the best hit) | Model independent | Never refuses: the best hit always passes | Does not solve the trick question |
| Calibrate automatically at startup | No manual step | Needs labelled questions at runtime; silently changes behaviour when the index changes | A script and a human decision are auditable |
| Add `top_p` | Another anti-randomness knob | Overlaps with temperature 0.1 (see above) | No measurable benefit |

## Consequences

- **Positive**: The trick question can be refused deterministically, without an LLM call (saves the whole generation time on CPU). Identifier questions keep working under a threshold. The threshold is chosen from data, per embedding, and every report says which value was used.
- **Negative / trade-offs**:
  - A threshold set too high turns answerable questions into "not found". The calibration criterion (no question loses every expected excerpt) guards against this only for the questions in the set.
  - "Not expected file" is an approximation of "irrelevant": `expected_files` lists the main files, so useful neighbours are counted as noise; the suggestion is therefore conservative.
  - The value is tied to the embedding model and to `CHUNK_METADATA`; changing either needs a new calibration (the script groups by both).
  - A question that is answerable only through BM25 words (no identifier, low cosine) is refused under a threshold. Such questions are rare in Chinese (BM25 indexes ASCII only), but possible in English.
- **Follow-ups**: Run group G; record Q10 and recall in `docs/metrics.md` §4a; if it is safe, a new ADR sets a default value for `nomic-embed-text`. Consider logging all candidates' cosines (not only the excerpts sent to the LLM) if the calibration data turns out too thin.

---

# 0014. 向量檢索那一路的相似度門檻，以及固定的「找不到」回答

- **狀態**：已接受（預設**關閉**：`SCORE_THRESHOLD` 預設為空；必須先校準才設定數值，見[實驗計畫](../evaluation/experiment-plan-retrieval.md) G 組）
- **日期**：2026-11-02
- **相關**：ADR [0013](0013-hybrid-retrieval-and-split-retrieval.md)（開關架構、RRF）、ADR [0012](0012-automated-evaluation-metrics.md)（評估）、ADR [0015](0015-rerank.md)（Rerank）、程式碼 `backend/app/rag.py`（`retrieve_detailed`）、`scripts/calibrate_threshold.py`

## 背景

檢索永遠回傳 `TOP_K` 段片段，不管多不相關。`questions.yaml` 第 10 題（「線上多人模式怎麼同步玩家位置？」——範例專案沒有任何多人功能）時，模型仍然拿到四段關於玩家與遊戲迴圈的片段，小模型很容易拿它們拼湊出回答。提示雖然寫了「片段中沒有答案就直接說找不到」，但 3B 模型不一定照做，拒不拒答要看運氣。

我們要在檢索端加一道防線：取回的內容如果沒有任何一段真的和問題相似，就根本不要問 LLM。

影響設計的事實：

- `nomic-embed-text` 的 cosine 相似度分布很集中：實測中一個**相關**的 Markdown 片段只有 **0.60**。常見的 0.70 會把它丟掉。合適的值取決於 embedding 模型、前綴、語言組合（中文問題、英文程式碼），以及是否開啟 `CHUNK_METADATA`。
- `HYBRID_SEARCH=true` 時，`source.score` 是 RRF 分數（約 0.016–0.05，只看名次），不代表絕對的相關程度，不能拿來和門檻比較。
- 問題中的精確識別字（`INVINCIBLE_MS`）即使 cosine 很低，也是很強的證據（ADR 0013：向量檢索對識別字很弱）。

## 決策

1. **`SCORE_THRESHOLD`**（預設空值 = 不過濾）**只套用在向量檢索那一路的 cosine 相似度**，而且在 **RRF 合併之前**。低於門檻的向量結果從向量排名中移除，其餘維持原順序。
2. `HYBRID_SEARCH=true` 時：
   - **識別字那一路**（定義了問題中寫出的名稱的片段）**一律不過濾**——那是精確證據；
   - **關鍵字（BM25）結果**只有在它的向量結果通過門檻，**或**內容包含問題中的精確識別字（`contains_identifier`：完整單字、區分大小寫）時才保留。否則 "player" 這種一般單字會讓任何片段通過，英文版的陷阱題永遠不會被拒答。
3. 過濾後什麼都不剩時，後端**不呼叫 LLM**，直接回傳固定的繁體中文訊息（`NO_RELEVANT_ANSWER`）：「在目前索引的專案中找不到與這個問題相關的內容……」，引用清單為空。`/query` 與 `/query/stream` 行為一致（串流送出 `sources: []`、以一個 `token` 送出訊息，再送 `done`，其中 `no_relevant: true`、`below_threshold: N`）。訊息含「找不到」，`evaluate.py` 會把它算成陷阱題的正確拒答。
4. **不設預設值。** `scripts/calibrate_threshold.py` 讀取評估報告（實驗計畫 A～F 組），依 embedding（模型、有無 `CHUNK_METADATA`）分組，列出**預期檔案**與**非預期檔案**片段的 cosine 分布，以及每個候選門檻會丟掉多少正確片段、擋掉多少其他片段、哪些題目會失去所有預期片段、陷阱題是否會被拒答。建議值是「每一題都至少保留一個預期片段、且丟掉的正確片段不超過 5%」的最高候選值；資料不足時明確說明、不給數字。
5. 為了能夠校準，每個引用片段現在都帶有 **`vector_score`**（cosine；只被關鍵字／識別字找到時為 `null`）與 `rerank_score`；`evaluate.py` 把它們連同 `matched_by` 記錄在 JSON 報告中。舊報告在沒有開混合檢索時仍可使用（當時 `score` 就是 cosine）。
6. 可觀察性比照 ADR 0013：`/health` → `retrieval.score_threshold`；報告開頭與 `compare.py` 會顯示；報告另外統計「因門檻直接拒答（未呼叫 LLM）」。

**top_p。** `LLM_TEMPERATURE` 已經是 0.1。在這麼低的溫度下，機率分布非常集中，nucleus sampling（`top_p`）能裁掉的，幾乎都是溫度已經壓到可以忽略的選項：兩個參數的效果重疊。加一個 `top_p` 開關只會讓每次實驗多一個變數，卻量不出差別，所以不加。幻覺要從源頭處理——也就是模型拿到什麼內容來讀。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 固定預設 0.70 | 教學文章常見；開箱即用 | 依模型而定：nomic-embed-text 下相關的 Markdown 片段只有 0.60，會被丟掉，正確回答變成拒答 | 改為依模型校準；預設為空 |
| 門檻套在融合後的分數 | 所有模式共用一個數字 | RRF 分數來自名次而不是相似度：第一名永遠約 1/(k+1)，不管相不相關 | 作為相關性門檻沒有意義 |
| 融合後再依各片段的 cosine 過濾 | 純向量模式下效果相同 | 只被 BM25／識別字找到的片段沒有 cosine；融合名次已經把不該算的片段算進去 | 在融合前過濾，名次才正確 |
| 所有通道都套用門檻，包括識別字 | 規則簡單 | 正好丟掉混合檢索要解決的情況：定義 `INVINCIBLE_MS` 的片段 cosine 偏低 | 精確識別字證據不受門檻影響 |
| 交給 LLM 判斷（更強的「找不到就說」提示） | 不用新設定 | 小模型不一定照做；為了拒答要花一整次 LLM 呼叫（CPU 上要數分鐘） | 提示規則保留作為第二道防線 |
| 相對門檻（低於最高分 X% 就丟） | 與模型無關 | 永遠不會拒答：最高分那段一定通過 | 解決不了陷阱題 |
| 啟動時自動校準 | 不用手動步驟 | 執行時需要標註過的題目；索引改變時行為會默默改變 | 腳本＋人工決定比較容易稽核 |
| 加入 `top_p` | 多一個降低隨機性的參數 | 與溫度 0.1 效果重疊（見上） | 量不出效益 |

## 後果

- **正面**：陷阱題可以穩定拒答，而且不呼叫 LLM（在 CPU 上省下整段生成時間）。開啟門檻時，寫出識別字的問題仍然正常。門檻值依資料、依 embedding 決定，每份報告都記錄用了哪個值。
- **負面／取捨**：
  - 門檻太高會讓可回答的問題變成「找不到」。校準條件（每一題都不能失去所有預期片段）只能保護題組中的題目。
  - 「非預期檔案」只是「不相關」的近似：`expected_files` 列的是主要檔案，有用的相鄰檔案也會被算成雜訊，因此建議值偏保守。
  - 門檻值綁定 embedding 模型與 `CHUNK_METADATA`；任一個改變都要重新校準（腳本依兩者分組）。
  - 只靠 BM25 單字才能回答（沒有識別字、cosine 又低）的問題，在門檻下會被拒答。中文問題很少發生（BM25 只索引 ASCII），英文問題有可能。
- **後續工作**：跑 G 組，把 Q10 與命中率記到 `docs/metrics.md` §4a；若安全，以新的 ADR 為 `nomic-embed-text` 設定預設值。若校準資料太少，考慮記錄所有候選片段（不只送進 LLM 的片段）的 cosine。
