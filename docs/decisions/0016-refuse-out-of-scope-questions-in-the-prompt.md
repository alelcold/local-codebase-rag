# 0016. Refuse out-of-scope questions in the prompt (PROMPT_VARIANT=v3)

- **Status**: Accepted (ships **off**: `PROMPT_VARIANT` stays `v1`, `.env.codespaces` unchanged; see [experiment plan](../evaluation/experiment-plan-retrieval.md) group J)
- **Date**: 2026-11-03
- **Related**: ADR [0012](0012-automated-evaluation-metrics.md) (evaluation metrics), ADR [0013](0013-hybrid-retrieval-and-split-retrieval.md) (prompt v2), ADR [0014](0014-similarity-threshold.md) (threshold), ADR [0015](0015-rerank.md) (rerank), [devlog 2026-11-03](../devlog/2026-11-03.md), [`docs/metrics.md`](../metrics.md) §4a, §4c, code `backend/app/rag.py`, `scripts/evaluate.py`, questions `docs/evaluation/questions-out-of-scope.yaml`

> English first; 繁體中文版本在下方. Privacy: illustrate only with the sample project.

## Context

`questions.yaml` question 10 (「線上多人模式怎麼同步玩家位置？」) asks about a feature the sample project does not have. In every group A–I of the experiment plan, `qwen2.5-coder:3b` answered it instead of saying "not found". A typical answer (group D) starts with general knowledge ("position sync usually uses WebSockets or Server-Sent Events") and then presents `Game.syncUi()`, which copies the score to the HUD, as the "sync logic", because its name contains *sync*.

Two retrieval-side fixes were tried and neither separates the trick question from real ones:

- **Similarity threshold (ADR 0014)**: the calibration on the A and C reports found no usable value. Expected and other excerpts have nearly the same cosine distribution (median 0.616 vs 0.604); Q10's 7 excerpts score 0.478–0.570 (median 0.542), and it is only refused from 0.60, where 6 real questions already lose every correct excerpt. Group G was not run.
- **Rerank score (ADR 0015)**: in group I, Q10's best cross-encoder score was 0.33, while a real question (Q9) had a best score of only 0.0165. Any rerank threshold that refuses Q10 also refuses Q9.

The reason is the same for both: retrieval always returns the *closest* excerpts, and a small game project always has something close to "player position" or "sync". Whether those excerpts actually talk about the topic is a reading task, and the only component that reads them is the LLM.

The v1 prompt does have a rule for this ("If the excerpts do not contain the answer, say so plainly and suggest what to search for instead"), but the 3B model ignores it: it is the fourth of five sentences, describes what to do instead of what to write, and "suggest what to search for" invites the model to talk about related code. Prompt v2 (ADR 0013) did not help either: group F answered Q10 too, and v2's other changes (code locations first, doc / code labels) did not improve retrieval or citations over C.

## Decision

Add `PROMPT_VARIANT=v3`: **v1 plus one refusal rule, and always Traditional Chinese**. Nothing else from v2.

```text
Rules:
1. Answer ONLY from the code excerpts below. Do not guess. Do not use general knowledge.
2. If no excerpt directly mentions the topic of the question, reply with exactly: 在索引的專案中找不到相關內容。
   A similar word in a function or variable name is not enough.
3. Cite every claim with the excerpt number and location, e.g. [2] src/game/Player.ts:12-30. Never invent files, functions or line numbers.
4. Quote short code snippets in fenced code blocks when they help.
5. Always answer in Traditional Chinese (繁體中文), even if the question is in English.
```

and, between the question and `## Answer`:

```text
(If no excerpt directly mentions this topic, reply only: 在索引的專案中找不到相關內容。)
```

Design choices for a 3B model that drops rules from long instructions:

- **Short and numbered**: five one-line rules, about the length of v1 (a unit test keeps v3 within two lines of v1 and shorter than v2). One rule per line, so no rule hides in the middle of a sentence.
- **Refusal rule second**, right after "use only the excerpts": the two belong together, and early rules are followed more reliably than late ones.
- **A fixed sentence to copy**, not a description ("say so plainly"). Small models copy a quoted sentence much better than they paraphrase an instruction, and a fixed sentence is easy to detect. It contains 「找不到」, which `evaluate.py` and the backend's canned answers (`NO_RELEVANT_ANSWER`) already use.
- **Names the two failure modes seen in Q10's answers**: general knowledge ("Do not use general knowledge") and a similar identifier ("A similar word in a function or variable name is not enough"). The rule stays generic: it does not mention multiplayer or `syncUi`, so it is not tuned to the one question it is measured on.
- **Repeated after the question**: with `TOP_K=4` the excerpts are often over 100 lines, so for a small model the rules at the top are far away when it starts writing; the last thing it reads is the reminder.
- **Dropped from v1**: "suggest what to search for instead" (invites related code instead of a refusal) and "reply in the same language as the question" (replaced by rule 5).
- **English rule text, Chinese output**, as in v1: it keeps v3 a minimal diff from v1, so J measures the refusal rule and not a translation of the whole prompt. The refusal sentence itself is in Chinese because it is copied into the answer.

Measuring it:

- `docs/evaluation/questions-out-of-scope.yaml`: 5 trick questions about features the sample project does not have (online rooms, in-app purchases, cloud saves, a global leaderboard, gamepad support) and 3 **control questions** about features that exist but are easy to mistake for missing: the high score saved in `localStorage` (next to the cloud-save trick), sound effects with no audio files (synthesized by `SoundManager`), and the `blur` handler inside `InputManager` (a few lines, no file or doc section of its own). A stricter prompt that refuses more easily would show up on these.
- `scripts/evaluate.py` reports **拒答率** (refusal rate: trick questions answered "not found" without forbidden words, as before) and **誤拒率** (false refusal rate: answerable questions whose answer contains a "not found" phrase *and* hits none of the question's keywords). The phrase list (`REFUSAL_PHRASES`) leaves out a bare 「沒有」, which is common in correct answers. `compare.py` shows both; for 誤拒率 lower is better.
- Group J = D + `PROMPT_VARIANT=v3`: D is the reference because J changes only the prompt. Re-scoring every A–I report gives a false refusal rate of 0 on all 14 answerable main and identifier questions, so any false refusal in J comes from v3.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Similarity threshold (ADR 0014) | No LLM call when refused; deterministic | Distributions overlap: refusing Q10 (≥ 0.60) drops every correct excerpt of 6 real questions | Calibration found no value (group G not run) |
| Rerank-score threshold (ADR 0015) | Cross-encoder reads question and excerpt together | Scores are not calibrated across questions: Q10 0.33 > Q9 0.0165; +1.5 GB image, seconds per query on CPU | Cannot separate the trick question from a real one |
| Build on v2 instead of v1 | Already always Chinese | Longer prompt (more rules for a 3B model to drop); group F showed no gain from v2's other changes | Would mix two changes; J must measure only the refusal rule |
| Long, detailed refusal instructions with examples | More explicit | 3B model ignores long instructions; examples about multiplayer would tune the prompt to the test question | Against the goal of short rules; overfits |
| A second LLM call to check "is the topic in the excerpts?" | Separates reading from answering | Doubles latency on CPU (first token is already 13–27 s) | Too slow for the Codespaces target; reconsider with a larger model |
| Bigger model (14B) | Follows instructions better | Not available on Codespaces CPU in reasonable time | Out of scope here; v3 can be measured on 14B later |

## Consequences

- **Positive**: One switch, query time only, no re-index and no extra dependency. It works with every retrieval setting, including rerank. The refusal is a fixed sentence, so it is easy to detect and easy for the team to recognize. The evaluation now measures both sides of refusing: how often trick questions are refused and how often real questions are wrongly refused.
- **Negative / trade-offs**: A prompt rule is a request, not a guarantee; a 3B model may still answer trick questions. "Directly mentions the topic" is a judgement the model can also get wrong the other way (false refusals, e.g. "sound files" → no files → "not found"); the control questions exist to catch that. A wrong "not found" is worse than a weak answer, because it hides code that exists. The automatic refusal checks are keyword screens; flagged answers must be read.
- **Follow-ups**: Run group J (experiment plan) and fill in `docs/metrics.md` §4a and §4c. Make v3 the default (new ADR, and only then `.env.codespaces`) only if the refusal rate rises and the false refusal rate stays 0 on every set. If the 3B model still does not refuse, measure v3 on 14B before trying more prompt text.

---

# 0016. 從提示處理範圍外問題的拒答（PROMPT_VARIANT=v3）

- **狀態**：已接受（預設**不開啟**：`PROMPT_VARIANT` 維持 `v1`，`.env.codespaces` 不變；見[實驗計畫](../evaluation/experiment-plan-retrieval.md) J 組）
- **日期**：2026-11-03
- **相關**：ADR [0012](0012-automated-evaluation-metrics.md)（評估指標）、ADR [0013](0013-hybrid-retrieval-and-split-retrieval.md)（提示 v2）、ADR [0014](0014-similarity-threshold.md)（門檻）、ADR [0015](0015-rerank.md)（Rerank）、[devlog 2026-11-03](../devlog/2026-11-03.md)、[`docs/metrics.md`](../metrics.md) §4a、§4c，程式碼 `backend/app/rag.py`、`scripts/evaluate.py`，題目 `docs/evaluation/questions-out-of-scope.yaml`

## 背景

`questions.yaml` 第 10 題（「線上多人模式怎麼同步玩家位置？」）問的是範例專案沒有的功能。在實驗計畫的 A～I 每一組，`qwen2.5-coder:3b` 都直接回答，而不是說找不到。典型的回答（D 組）先用一般知識開頭（「位置同步通常使用 WebSockets 或 Server-Sent Events」），再把 `Game.syncUi()`（把分數同步到 HUD）當成「同步邏輯」，只因為名稱裡有 *sync*。

試過兩種檢索端的做法，都分不開陷阱題與真實問題：

- **相似度門檻（ADR 0014）**：用 A、C 組報告校準，找不到可用的值。預期片段與其他片段的 cosine 分布幾乎相同（中位數 0.616 與 0.604）；第 10 題的 7 個片段是 0.478–0.570（中位數 0.542），門檻要到 0.60 才會拒答，而那時已有 6 題真實問題失去所有正確片段。G 組沒有執行。
- **Rerank 分數（ADR 0015）**：I 組第 10 題最高的交叉編碼器分數是 0.33，而真實問題（第 9 題）最高只有 0.0165。任何能拒答第 10 題的 rerank 門檻也會拒答第 9 題。

兩者的原因相同：檢索永遠會回傳「最接近」的片段，而小型遊戲專案裡一定有和「玩家位置」或「同步」接近的東西。這些片段到底有沒有談到問題的主題，是閱讀理解的問題，而唯一會讀片段的元件是 LLM。

v1 提示其實有相關規則（「片段中沒有答案時直接說明，並建議改搜尋什麼」），但 3B 模型忽略了它：它是五句中的第四句，描述的是要怎麼做而不是要寫什麼，而「建議改搜尋什麼」反而引導模型去談相關的程式碼。提示 v2（ADR 0013）也沒有幫助：F 組同樣回答了第 10 題，v2 的其他改動（先說程式碼位置、文件／程式碼標籤）也沒有讓檢索或引用比 C 好。

## 決策

新增 `PROMPT_VARIANT=v3`：**v1 加上一條拒答規則，並一律使用繁體中文**。不沿用 v2 的其他改動。規則內容見上方英文版（提示本身是英文，不翻譯），並在問題與 `## Answer` 之間再提醒一次：

```text
(If no excerpt directly mentions this topic, reply only: 在索引的專案中找不到相關內容。)
```

針對會忽略長指令的 3B 模型的設計考量：

- **簡短、編號**：五條各一行的規則，長度與 v1 相近（單元測試限制 v3 最多比 v1 多兩行，而且比 v2 短）。一行一條，規則不會藏在句子中間。
- **拒答規則排第二**，緊接在「只能根據片段」之後：兩者是同一件事；前面的規則比後面的更容易被遵守。
- **給一句固定的句子照抄**，而不是描述（「直接說明」）。小模型照抄引號中的句子，遠比改寫一條指令可靠，固定句子也容易偵測。句子含有「找不到」，與 `evaluate.py` 及後端固定回答（`NO_RELEVANT_ANSWER`）一致。
- **點出第 10 題回答中的兩種錯誤**：使用一般知識（「Do not use general knowledge」）與名稱相似的識別字（「函式或變數名稱中有相似的字不算」）。規則維持通用：沒有提到多人模式或 `syncUi`，不會針對用來量測的那一題調整。
- **在問題之後重複一次**：`TOP_K=4` 時片段常超過 100 行，小模型開始寫回答時，最上面的規則已經很遠；它最後讀到的是這句提醒。
- **從 v1 拿掉的**：「建議改搜尋什麼」（引導模型談相關程式碼而不是拒答）與「用問題的語言回答」（由第 5 條取代）。
- **規則用英文、輸出用中文**，與 v1 相同：讓 v3 與 v1 的差異最小，J 組量到的是拒答規則，而不是整份提示翻譯成中文的效果。拒答句本身用中文，因為它會被照抄進回答。

量測方式：

- `docs/evaluation/questions-out-of-scope.yaml`：5 題範例專案沒有的功能（線上房間、內購、雲端存檔、全球排行榜、手把支援），以及 3 題**對照題**，問存在但容易被誤判為不存在的功能：存在 `localStorage` 的最高分（和雲端存檔陷阱題相鄰）、沒有音效檔的音效（由 `SoundManager` 合成）、`InputManager` 裡的 `blur` 處理（只有幾行，沒有自己的檔案或文件段落）。更容易拒答的提示，會在這幾題上露出來。
- `scripts/evaluate.py` 報告**拒答率**（陷阱題回答找不到且沒有禁用字，判定方式不變）與**誤拒率**（可回答的題目，回答含有「找不到」類字句，**而且**沒有命中任何關鍵字）。字句清單（`REFUSAL_PHRASES`）不包含單獨的「沒有」，因為正確回答也常出現。`compare.py` 兩者都會顯示；誤拒率越低越好。
- J 組 = D + `PROMPT_VARIANT=v3`：J 只改提示，所以以 D 為參考。重新計分 A～I 組所有報告，主要與識別字題組 14 題可回答的題目誤拒率都是 0，因此 J 組若有誤拒，就是 v3 造成的。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 相似度門檻（ADR 0014） | 拒答時不呼叫 LLM；結果固定 | 分布重疊：要拒答第 10 題（≥ 0.60）會讓 6 題真實問題失去所有正確片段 | 校準找不到可用的值（G 組未執行） |
| Rerank 分數門檻（ADR 0015） | 交叉編碼器同時讀問題與片段 | 分數在不同問題之間不可比：第 10 題 0.33 > 第 9 題 0.0165；映像檔多 1.5 GB，CPU 上每次查詢多幾秒 | 分不開陷阱題與真實問題 |
| 以 v2 為基礎 | 已經一律中文 | 提示較長（3B 模型會漏掉更多規則）；F 組顯示 v2 的其他改動沒有幫助 | 會混入兩個變因；J 組只能量拒答規則 |
| 很長、附範例的拒答說明 | 更明確 | 3B 模型會忽略長指令；用多人模式當範例等於針對考題調整 | 違反規則要簡短的目標；過度擬合 |
| 再呼叫一次 LLM 判斷「片段有沒有提到主題」 | 閱讀判斷與回答分開 | CPU 上延遲加倍（首字延遲已經 13–27 秒） | 對 Codespaces 太慢；換大模型時再考慮 |
| 改用更大的模型（14B） | 更會遵守指令 | 在 Codespaces 的 CPU 上無法在合理時間內執行 | 不在這次範圍；之後可在 14B 上量測 v3 |

## 後果

- **正面**：一個開關，只影響查詢，不需要重新索引，也不增加依賴。可以搭配任何檢索設定，包括 Rerank。拒答是固定的句子，容易偵測，團隊也一眼就認得。評估現在同時量測拒答的兩面：陷阱題被拒答的比例，以及真實問題被誤拒的比例。
- **負面／取捨**：提示規則是要求，不是保證；3B 模型仍可能回答陷阱題。「直接提到主題」是模型的判斷，也可能錯在另一個方向（誤拒，例如「音效檔」→ 沒有檔案 →「找不到」）；對照題就是為了抓這種情況。錯誤的「找不到」比不完整的回答更糟，因為它會把存在的程式碼藏起來。自動拒答判定只是關鍵字篩選，被標記的回答要人工讀過。
- **後續工作**：執行 J 組（實驗計畫），填寫 `docs/metrics.md` §4a 與 §4c。只有在拒答率提升、而且每個題組的誤拒率都維持 0 時，才把 v3 改為預設（新增 ADR，之後才修改 `.env.codespaces`）。如果 3B 模型仍然不拒答，先在 14B 上量測 v3，再考慮增加提示內容。
