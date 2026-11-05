# 0019. Refusal scoring: Simplified refusal phrases and a fabrication check

- **Status**: Accepted
- **Date**: 2026-11-05
- **Related**: ADR [0012](0012-automated-evaluation-metrics.md) (evaluation metrics; refusal row extended here), ADR [0016](0016-refuse-out-of-scope-questions-in-the-prompt.md) (false refusals, out-of-scope set), [devlog 2026-11-03](../devlog/2026-11-03.md) (where the holes were found), [devlog 2026-11-05](../devlog/2026-11-05.md), `scripts/evaluate.py`, `scripts/compare.py`

> English first; 繁體中文版本在下方. Privacy: illustrate only with the sample project.

## Context

Reading group D's out-of-scope answers on 2026-11-03 showed two holes in the automatic refusal score (ADR 0012: "a refusal phrase and no forbidden keyword"):

1. **Simplified refusals were missed.** Q22 answered 「我无法提供关于付款流程的详细信息」. The keyword list has 無法 but not 无法, so a refusal scored "not refused". The 3B model often answers in Simplified, and every new refusal keyword had to be remembered twice in five places (each trick question's list, and `REFUSAL_PHRASES`).
2. **Invented answers could pass.** The only fabrication signal was a short per-question list of forbidden words (`WebSocket`, `Stripe`…). An answer that says "not found" and then describes `src/net/Sync.ts` or a `syncPlayers()` function the project does not have would count as a refusal. Real examples from the reports: `src/game/Player.ts` (does not exist; `Player.ts` is in `src/entities/`), `checkCollisions()`, `invincibilityTime`, `PLANET_SPAWN_RATE`.

## Decision

1. **One Traditional / Simplified list** (`REFUSAL_TRAD_SIMP` in `evaluate.py`, 繁簡對照清單): each Chinese refusal phrase with its Simplified forms (無法 → 无法, 沒有找到 → 没有找到, 只支援鍵盤 → 只支援键盘 / 只支持键盘). Trick-question refusal keywords and `REFUSAL_PHRASES` are matched with these forms added. The question files stay Traditional. A unit test fails when a Chinese refusal keyword in any question file (or in `REFUSAL_PHRASES`) is not in the list, and checks each Simplified form against a character map. `沒有找到` and `未找到` were added to `REFUSAL_PHRASES` (沒找到 does not match 沒有找到).
2. **Fabrication check against the indexed project.** `evaluate.py` scans the question file's `project:` (default the sample project; `--project` to override) for file paths and every identifier-like token. In each answer it looks for file references (a name with a known extension) and code-shaped symbols (called with `()`, snake / CONSTANT case, or camel / Pascal case). A file or symbol that exists nowhere in the project (case-insensitive; a short list of language and browser names is allowed) is recorded in `unknown_refs`. `suspected_fabrication` = an unknown file or symbol, or a forbidden word.
3. **A trick question is refused only if it is not suspected.** A refusal phrase plus a forbidden word or an unknown file / symbol is "not refused: refusal phrase, but suspected fabrication", for a person to check. For answerable questions the flag is shown but changes no other metric. The summary adds 「疑似編造」 (count over all answers), and `compare.py` compares it.
4. **Re-score instead of re-run.** `evaluate.py --rescore REPORT.json …` recomputes the automatic metrics from the stored answers and sources with the current rules and question files, keeps timing, server data, manual scores, the Notes column and any note above the generated header, and records `rescored.scoring` (scoring version 2). All existing reports in `docs/evaluation/results/` were re-scored and the comparisons regenerated.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Add 无法 etc. to each question's keyword list (the devlog's to-do) | No code change | Five copies to keep in sync; the next keyword would be missed again | The list plus a test makes forgetting fail loudly |
| Convert the whole answer to Traditional (OpenCC) before matching | Covers every phrase | New dependency; Simplified → Traditional is ambiguous (发 → 發 / 髮); would also change keyword hits of real questions | Only refusal phrases need it; the list is small and reviewable |
| Treat a forbidden word or unknown symbol as an outright failure, without a label | Simpler | "沒有找到 WebSocket 相關程式碼" is a correct refusal that names a forbidden word | Not passed, but labelled so a person decides |
| Check names only against the retrieved excerpts | Measures "invented beyond what the model saw" | A real file the model did not see would be flagged | The question is whether the project has it |
| Ask an LLM to judge fabrication | Would catch invented behaviour with real names | Non-deterministic, slow, needs a model in CI | The check must run offline in unit tests and on old reports |

## Consequences

- **Positive**: group D's out-of-scope refusal rate is 2/5 by keyword screen, matching what reading the answers found (Q22). Of the 31 answers flagged in the 2026-11-03 reports, 29 were scored 0 by AI reading. Old reports can be re-scored when rules change, without a model.
- **Negative / trade-offs**: the check is lexical. It misses invented behaviour built from real names (D-oos Q23 「`syncUi` 會把存檔同步到雲端」, Q25 keyboard keys described as gamepad buttons): of 59 answers scored 0, 29 are flagged. It can flag a real member under another name (`getMultiplier` for the getter `get multiplier()`, AI score 2). Plain-word names (`Player`, `score`) are not checked. The flag is a screen, not correctness (ADR 0012 still applies).
- **Follow-ups**: if fabrication with real names matters, compare the behaviour the answer claims with the retrieved excerpts (would need an LLM judge or rules per question).

---

# 0019. 拒答計分：簡體拒答字句與編造檢查

- **狀態**：已接受
- **日期**：2026-11-05
- **相關**：ADR [0012](0012-automated-evaluation-metrics.md)（評估指標；本文擴充其拒答一列）、ADR [0016](0016-refuse-out-of-scope-questions-in-the-prompt.md)（誤拒、範圍外題組）、[devlog 2026-11-03](../devlog/2026-11-03.md)（發現漏洞的地方）、[devlog 2026-11-05](../devlog/2026-11-05.md)、`scripts/evaluate.py`、`scripts/compare.py`

## 背景

2026-11-03 讀 D 組範圍外題組的回答時，發現自動拒答計分（ADR 0012：「命中拒答字句且沒有禁用字」）有兩個漏洞：

1. **漏算簡體拒答。** 第 22 題回答「我无法提供关于付款流程的详细信息」。關鍵字清單有「無法」但沒有「无法」，所以拒答被算成「未拒答」。3B 模型常用簡體回答，而每個新拒答字都要在五個地方（每題陷阱題的清單與 `REFUSAL_PHRASES`）各記兩次。
2. **編造的回答也能過關。** 唯一的編造訊號是每題一小串禁用字（`WebSocket`、`Stripe`…）。回答先說「找不到」，再描述專案中沒有的 `src/net/Sync.ts` 或 `syncPlayers()`，仍會被算成拒答。報告中的實例：`src/game/Player.ts`（不存在；`Player.ts` 在 `src/entities/`）、`checkCollisions()`、`invincibilityTime`、`PLANET_SPAWN_RATE`。

## 決策

1. **一份繁簡對照清單**（`evaluate.py` 的 `REFUSAL_TRAD_SIMP`）：每個中文拒答字句與它的簡體寫法（無法 → 无法、沒有找到 → 没有找到、只支援鍵盤 → 只支援键盘／只支持键盘）。陷阱題的拒答關鍵字與 `REFUSAL_PHRASES` 比對時會加上這些寫法；題目檔維持繁體。題目檔（或 `REFUSAL_PHRASES`）中有中文拒答關鍵字不在清單裡時，單元測試會失敗；測試也用字元對照表檢查每個簡體寫法。`REFUSAL_PHRASES` 新增「沒有找到」「未找到」（「沒找到」比對不到「沒有找到」）。
2. **對照索引的專案檢查編造。** `evaluate.py` 掃描題目檔 `project:` 指定的專案（預設範例專案；可用 `--project` 指定），收集檔案路徑與所有識別字形式的字詞。在每個回答中找出檔案引用（帶已知副檔名的名稱）與程式碼形式的符號（帶 `()`、snake／全大寫底線、camel／Pascal 大小寫）。專案中完全不存在的檔案或符號（不分大小寫；少數語言與瀏覽器內建名稱除外）記在 `unknown_refs`。`suspected_fabrication`（疑似編造）= 有不存在的檔案或符號，或有禁用字。
3. **陷阱題只有在沒有疑似編造時才算拒答。** 命中拒答字句但有禁用字或不存在的檔案／符號，標示為「not refused: refusal phrase, but suspected fabrication」，由人確認。可回答的題目只顯示標記，不影響其他指標。摘要新增「疑似編造」（所有回答中的題數），`compare.py` 也會比較它。
4. **重新計分，不重跑。** `evaluate.py --rescore REPORT.json …` 用報告中保存的回答與來源，以目前的規則與題目檔重新計算自動指標，保留延遲、伺服器資料、人工分數、Notes 欄與產生的標頭上方的說明，並記錄 `rescored.scoring`（計分版本 2）。`docs/evaluation/results/` 中所有既有報告都已重新計分，比較報告也已重新產生。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 在每題關鍵字清單加上「无法」等（devlog 的待辦） | 不用改程式 | 五份要同步；下一個關鍵字又會漏 | 清單加測試，忘記時會直接失敗 |
| 比對前把整個回答轉成繁體（OpenCC） | 所有字句都涵蓋 | 新增相依套件；簡轉繁有歧義（发 → 發／髮）；也會改變真實題目的關鍵字命中 | 只有拒答字句需要；清單小、容易審查 |
| 有禁用字或不存在的符號就直接判失敗，不加標示 | 較簡單 | 「沒有找到 WebSocket 相關程式碼」是正確的拒答，卻提到禁用字 | 不算通過，但加上標示交給人判斷 |
| 只對照取回的片段 | 量的是「超出模型看到的內容」 | 模型沒看到的真實檔案也會被標記 | 要問的是專案裡有沒有 |
| 用 LLM 判斷是否編造 | 能抓到用真實名稱編出的行為 | 結果不固定、慢、CI 需要模型 | 檢查必須能離線在單元測試與舊報告上執行 |

## 後果

- **正面**：D 組範圍外題組的拒答率以關鍵字篩選為 2/5，與人讀回答的結果一致（第 22 題）。2026-11-03 報告中被標記的 31 個回答，有 29 個被 AI 判為 0 分。規則改變時，不需要模型就能重新計分舊報告。
- **負面／取捨**：這是字面檢查。用真實名稱編出不存在的行為抓不到（D 組範圍外第 23 題「`syncUi` 會把存檔同步到雲端」、第 25 題把鍵盤按鍵說成手把）：59 個 0 分回答中有 29 個被標記。真實成員換個名字也會被標記（getter `get multiplier()` 寫成 `getMultiplier`，AI 判 2 分）。一般單字的名稱（`Player`、`score`）不檢查。這個標記只是篩選，不等於正確性（ADR 0012 仍適用）。
- **後續工作**：若要抓到用真實名稱的編造，需比對回答宣稱的行為與取回片段（需要 LLM 判斷或逐題規則）。
