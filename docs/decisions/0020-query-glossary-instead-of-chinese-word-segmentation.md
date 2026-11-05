# 0020. Query glossary (Chinese terms → identifiers) instead of Chinese word segmentation

- **Status**: Accepted (ships **off**: `QUERY_GLOSSARY=false`; `.env.codespaces` and `.env.example` defaults unchanged until group K is run)
- **Date**: 2026-11-05
- **Related**: ADR [0013](0013-hybrid-retrieval-and-split-retrieval.md) (hybrid retrieval, switch architecture), ADR [0018](0018-codespaces-default-retrieval-settings.md) (Codespaces defaults), [experiment plan](../evaluation/experiment-plan-retrieval.md) group K, [devlog 2026-11-05](../devlog/2026-11-05.md), [`docs/metrics.md`](../metrics.md) §4a, code `backend/app/glossary.py`, `backend/app/rag.py`, `scripts/build_glossary.py`, glossary `glossary/sample-game-frontend.yaml`

> English first; 繁體中文版本在下方. Privacy: illustrate only with the sample project.

## Context

The team asks in Chinese; the code is in English. ADR 0013's keyword channel (BM25) and identifier channel index **ASCII tokens only**, on purpose: the Markdown docs are Chinese, so indexing CJK would make the keyword channel favour exactly the docs that crowd out code. The consequence, visible in groups A–J and noted in the 2026-11-03 devlog and article 6: for a question such as 「連擊倍率怎麼計算？什麼時候會歸零？」 (main Q2), BM25 has no token to match and the identifier channel has no name to look up. Hybrid search therefore did little on the main set (Code file retrieved: A 1/9 → B 3/9, C 6/9 → D 6/9), while it reached 3/3 on the identifier set, where the question spells out `INVINCIBLE_MS`. Q2 retrieved neither `src/systems/ScoreSystem.ts` nor `src/config/gameConfig.ts` in any of the 8 groups run. The vector channel alone does not bridge 連擊 ↔ `combo` reliably with `nomic-embed-text`; adding the defined names to the embedded text (`CHUNK_METADATA`, group F) did not help either.

The missing piece is a mapping from the team's Chinese vocabulary to the project's identifiers. A project of 50–300 files has hundreds of such terms, so the mapping cannot be written entirely by hand.

## Decision

1. **New switch `QUERY_GLOSSARY` (default `false`)**, in the ADR 0013 switch architecture: a setting in `config.py`, query time only (no re-index), reported by `/health` (`retrieval.query_glossary`, `retrieval.query_glossary_active`, and a `glossary` block with path, number of terms, load errors and a note when it has no effect), recorded by `scripts/evaluate.py` in every report (the run table and a `- **Glossary**:` line per answer, from the `done` event).
2. **Glossary file**: YAML, `version: 1`, `terms:` mapping a Chinese term to a list of identifiers (`連擊: [combo, COMBO_STEP, COMBO_WINDOW_MS, MAX_COMBO_MULTIPLIER, ScoreSystem]`). Path `QUERY_GLOSSARY_PATH` (default `/glossary/sample-game-frontend.yaml`), read from `GLOSSARY_DIR` (default `./glossary`) mounted read-only at `/glossary`. It is reloaded when the file changes. A missing or invalid file makes `/health` `degraded` and queries go on without expansion. A real project's glossary contains its internal identifiers, so it lives outside this repository (CLAUDE.md, privacy). Only the sample project's glossary is committed.
3. **Matching**: plain substring search in the question, longest term first, without overlaps (「連擊倍率」 wins over 「連擊」 inside it). ASCII terms match case-insensitively.
4. **Where the identifiers go**: appended to the **BM25 query** and to the **identifier channel's** lookup list. The vector channel, rerank and the prompt keep the original question. With `SCORE_THRESHOLD`, glossary identifiers do **not** exempt keyword hits from the threshold, because they are inferred, not spelled out. Hits of the identifier channel stay exempt as before. Because only the keyword and identifier channels use it, **`QUERY_GLOSSARY` does nothing without `HYBRID_SEARCH=true`**: `/health` says so, as do `.env.example`, the README and the experiment plan.
5. **Semi-automatic drafts**: `scripts/build_glossary.py <project>` lists top-level constants, classes, functions, types and file names. It then pairs them with Chinese terms from parentheses in the docs (「衝刺（dash）」 → every name containing `dash`), from a Chinese phrase right before a backticked name, from Markdown table rows, and from Chinese comments on declarations. Each entry is printed with where it came from, and unmapped declarations are grouped as comments. The draft is for a person to review. It writes to stdout by default, so a real project's draft stays out of the repo.
6. **Sample glossary** `glossary/sample-game-frontend.yaml`: the generator's draft, reviewed, plus domain terms (31 terms). A unit test checks every identifier exists in the sample code.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| **Chinese word segmentation (e.g. jieba) for the BM25 index and the query** | No vocabulary to maintain; covers every Chinese word | Only matches Chinese to Chinese: the Chinese tokens would hit the Chinese docs and comments, i.e. strengthen exactly the docs that already crowd out code (ADR 0013), and never reach `COMBO_STEP` in code. A new dependency of about 20 MB plus a dictionary, and segmentation errors on domain words (連擊倍率) unless a custom dictionary is kept. A full re-index, because the index content changes | It solves a different problem. Mapping 連擊 → `combo` still needs a vocabulary |
| Segment the query only, match tokens against identifier parts | No index change | Still needs a Chinese → English translation step for every token | Same vocabulary problem as the glossary, with less control |
| CJK character n-grams in BM25 | No dependency | Same as segmentation: matches Chinese docs, not code; many noisy n-grams | Same reason as jieba |
| LLM query rewriting / translation to English before retrieval | No vocabulary; handles phrasing | One more LLM call before retrieval: tens of seconds on CPU with 3B. Non-deterministic. It may invent identifiers the project does not have | Too slow on the target machines and not reviewable |
| Rely on embeddings (`CHUNK_METADATA`, another embedding model) | No new mechanism | Group F showed no retrieval gain from metadata. Changing the embedding model re-indexes and was not measured | Already tried; no gain |
| Use the generator's draft automatically, without review | No manual work | The draft contains noise (「再以」 → `FIXED_DT`, 「條命」), and a wrong pair pulls in wrong files on every matching question | A reviewed file is a small cost for a team that maintains the project |

## Consequences

- **Positive**: Chinese questions can use the keyword and identifier channels that already work for identifier questions. The mapping is explicit, reviewable and deterministic, with no new model and no re-index. It can be edited while the backend runs. In an offline check of the keyword and identifier channels only (no vector channel, no LLM; the sample project chunked by the backend chunker), the expected code files of the main set that reach the top 4 retrieved files went from **3 of 19 to 16 of 19** with the sample glossary. Q2 went from 0/2 to 2/2 (`gameConfig.ts`, `ScoreSystem.ts`). This is not an end-to-end result. Group K measures that (`docs/metrics.md` §4a: {待填}).
- **Negative / trade-offs**: someone has to keep the glossary up to date when code is renamed. The generator and the unit test of the sample glossary help, but nothing checks a real project's glossary automatically. Coverage is limited to listed terms, and a synonym nobody listed does not match. Substring matching has no notion of words, so a short term can match inside an unrelated phrase. Keep terms specific (two or more characters, and the generator drops single characters). The sample glossary was written by someone who had seen the evaluation questions, so group K is an **upper bound**. Hybrid search must be on.
- **Follow-ups**: run group K (experiment plan) and fill §4a. Test with questions written after the glossary. Optionally add `/health` warnings for glossary identifiers that no indexed chunk contains. Decide the Codespaces default in a new ADR only after K.

---

# 0020. 查詢詞彙表（中文詞 → 識別字），不用中文斷詞

- **狀態**：已接受（預設**關閉**：`QUERY_GLOSSARY=false`；在 K 組執行之前，`.env.codespaces` 與 `.env.example` 的預設值都不變）
- **日期**：2026-11-05
- **相關**：ADR [0013](0013-hybrid-retrieval-and-split-retrieval.md)（混合檢索、開關架構）、ADR [0018](0018-codespaces-default-retrieval-settings.md)（Codespaces 預設值）、[實驗計畫](../evaluation/experiment-plan-retrieval.md) K 組、[devlog 2026-11-05](../devlog/2026-11-05.md)、[`docs/metrics.md`](../metrics.md) §4a、程式 `backend/app/glossary.py`、`backend/app/rag.py`、`scripts/build_glossary.py`、詞彙表 `glossary/sample-game-frontend.yaml`

## 背景

團隊用中文提問，程式碼是英文。ADR 0013 的關鍵字通道（BM25）與識別字通道**只索引英文（ASCII）字詞**，這是刻意的：Markdown 文件是中文，索引中文會讓關鍵字通道偏向那些已經把程式碼擠掉的文件。後果在 A–J 組都看得到，2026-11-03 的 devlog 與第 6 篇文章也提過：像「連擊倍率怎麼計算？什麼時候會歸零？」（主要題組第 2 題）這樣的問題，BM25 沒有可比對的字詞，識別字通道也沒有可查的名稱。所以混合檢索對主要題組作用不大（程式碼檔命中：A 1/9 → B 3/9、C 6/9 → D 6/9），在問題直接寫出 `INVINCIBLE_MS` 的識別字題組卻達到 3/3。第 2 題在跑過的 8 組中，都沒有取回 `src/systems/ScoreSystem.ts` 或 `src/config/gameConfig.ts`。單靠 `nomic-embed-text` 的向量檢索，無法穩定對上「連擊 ↔ `combo`」。把定義的名稱放進 embedding 內容（`CHUNK_METADATA`，F 組）也沒有幫助。

缺的是一份從團隊的中文用詞到專案識別字的對照。50–300 個檔案的專案就有上百個這樣的詞，不可能全部手寫。

## 決策

1. **新開關 `QUERY_GLOSSARY`（預設 `false`）**，沿用 ADR 0013 的開關架構：在 `config.py` 設定，只影響查詢（不需重新索引）。`/health` 會回報 `retrieval.query_glossary`、`retrieval.query_glossary_active`，以及 `glossary` 區塊（路徑、詞數、載入錯誤、沒有作用時的提示）。`scripts/evaluate.py` 每份報告都會記錄（執行設定表，以及每題回答下方取自 `done` 事件的「- **Glossary**:」）。
2. **詞彙表檔案**：YAML，`version: 1`，`terms:` 把中文詞對應到識別字清單（`連擊: [combo, COMBO_STEP, COMBO_WINDOW_MS, MAX_COMBO_MULTIPLIER, ScoreSystem]`）。路徑為 `QUERY_GLOSSARY_PATH`（預設 `/glossary/sample-game-frontend.yaml`），從 `GLOSSARY_DIR`（預設 `./glossary`）以唯讀方式掛載到 `/glossary`。檔案改變時會重新載入。檔案不存在或格式錯誤時，`/health` 顯示 `degraded`，查詢照常進行但不擴充。真實專案的詞彙表含有內部識別字，必須放在這個 repo 之外（CLAUDE.md，隱私）；repo 中只提交範例專案的詞彙表。
3. **比對方式**：在問題中做單純的子字串比對，長詞優先、不重疊（「連擊倍率」優先於包含在內的「連擊」）。英文詞不分大小寫。
4. **識別字加到哪裡**：加進 **BM25 查詢**與**識別字通道**的查詢清單。向量檢索、Rerank 與提示仍使用原始問題。開啟 `SCORE_THRESHOLD` 時，詞彙表的識別字**不能**讓關鍵字結果免受門檻過濾，因為那是推論出來的，不是問題中寫出來的；識別字通道的結果則照舊不受門檻影響。只有關鍵字與識別字通道會用到詞彙表，所以 **`QUERY_GLOSSARY` 必須搭配 `HYBRID_SEARCH=true` 才有作用**：`/health`、`.env.example`、README 與實驗計畫都有說明。
5. **半自動草稿**：`scripts/build_glossary.py <專案>` 列出最上層的常數、class、函式、型別與檔名，再從以下來源配對中文詞：文件中的括號（「衝刺（dash）」→ 名稱含 `dash` 的所有宣告）、反引號名稱前緊接的中文詞、Markdown 表格列、宣告上的中文註解。每一條都附上出處，沒有對到中文詞的宣告則分組列成註解，供人工審核。預設輸出到 stdout，讓真實專案的草稿不會進到 repo。
6. **範例詞彙表** `glossary/sample-game-frontend.yaml`：產生器的草稿經人工審核，再補上領域詞（共 31 個詞）。單元測試會檢查每個識別字都存在於範例程式碼中。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| **中文斷詞（例如 jieba），用於 BM25 索引與查詢** | 不用維護詞彙；涵蓋所有中文詞 | 只能讓中文對上中文：中文字詞會命中中文文件與註解，也就是加強了那些已經把程式碼擠掉的文件（ADR 0013），永遠對不到程式碼裡的 `COMBO_STEP`。新增約 20 MB 的相依套件與詞典；除非另外維護自訂詞典，否則領域詞（連擊倍率）會斷錯。索引內容改變，需要全量重建 | 解決的是另一個問題；要把「連擊」對到 `combo`，還是需要詞彙對照 |
| 只對查詢斷詞，再拿字詞比對識別字的組成字 | 不用改索引 | 每個詞仍需要中翻英 | 和詞彙表一樣要有詞彙，但更難控制 |
| BM25 加入中文字元 n-gram | 沒有相依套件 | 和斷詞相同：對上的是中文文件，不是程式碼；雜訊 n-gram 很多 | 與 jieba 相同的理由 |
| 檢索前用 LLM 改寫／翻譯成英文 | 不用詞彙表；能處理各種說法 | 檢索前多一次 LLM 呼叫：3B 在 CPU 上要數十秒。結果不固定，可能編出專案沒有的識別字 | 在目標機器上太慢，也無法審核 |
| 依賴 embedding（`CHUNK_METADATA`、換 embedding 模型） | 不用新機制 | F 組顯示 metadata 沒有提升檢索；換 embedding 模型要重新索引，也沒有量測過 | 已經試過，沒有改善 |
| 直接使用產生器的草稿，不經審核 | 不用人工 | 草稿有雜訊（「再以」→ `FIXED_DT`、「條命」），錯的對應會讓每個比對到的問題都帶進錯誤的檔案 | 對維護專案的團隊來說，審核一份檔案的成本不高 |

## 後果

- **正面**：中文問題可以用到原本只對識別字問題有效的關鍵字與識別字通道。對照明確、可審核、結果固定，不需新模型，也不需重新索引；backend 執行中也能直接修改。離線檢查只測關鍵字與識別字通道（沒有向量檢索、沒有 LLM；範例專案以後端的 chunker 切塊）：使用範例詞彙表後，主要題組預期的程式碼檔出現在前 4 個取回檔案中的數量，從 **19 個中的 3 個增加到 16 個**；第 2 題從 0/2 變成 2/2（`gameConfig.ts`、`ScoreSystem.ts`）。這不是端到端的結果，端到端由 K 組量測（`docs/metrics.md` §4a：{待填}）。
- **負面／取捨**：程式碼改名時要有人更新詞彙表。產生器和範例詞彙表的單元測試有幫助，但真實專案的詞彙表沒有自動檢查。只涵蓋列出的詞，沒人列出的同義詞就比對不到。子字串比對沒有「詞」的概念，太短的詞可能在無關的句子裡被比對到，所以詞要具體（兩個字以上，產生器會丟掉單字）。範例詞彙表是看過評估題目的人寫的，所以 K 組是**上限**。必須開啟混合檢索。
- **後續工作**：執行 K 組（實驗計畫）並填入 §4a。用詞彙表完成後才寫的題目再測一次。可考慮在 `/health` 警告沒有任何已索引片段包含的詞彙表識別字。等 K 組結果出來，再以新的 ADR 決定 Codespaces 的預設值。
