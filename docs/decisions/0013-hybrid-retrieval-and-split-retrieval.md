# 0013. Hybrid retrieval, split code/doc retrieval and chunk metadata

- **Status**: Accepted (all four changes ship **off by default**; defaults change in a later ADR once the evaluation in [experiment-plan-retrieval.md](../evaluation/experiment-plan-retrieval.md) is done)
- **Date**: 2026-11-02
- **Related**: ADR [0004](0004-chunking-by-file-type.md) (chunking), ADR [0012](0012-automated-evaluation-metrics.md) (evaluation metrics), devlog [2026-11-02](../devlog/2026-11-02.md) Problem 3, code `backend/app/retrieval.py`

> English first; 繁體中文版本在下方. Privacy: illustrate only with the sample project.

## Context

The Codespace baseline (`qwen2.5-coder:3b`, `TOP_K=4`, vector search only) fails the 「定位設定」 questions in a consistent way: for 「玩家受傷後的無敵時間在哪裡設定？」 the retrieved excerpts are mostly Markdown (`docs/gameplay.md`, the sample `README.md`), and the code file that defines the value, `src/config/gameConfig.ts` (`export const INVINCIBLE_MS = 1500`), is not among them. The answer then cites a doc or names the wrong file.

Three causes, each addressed separately:

1. **Vector search alone is weak on exact identifiers.** `INVINCIBLE_MS` or `ScoreSystem` in a question is a precise signal, but in embedding space it is one token among many; prose that paraphrases the question scores higher.
2. **Docs crowd out code.** Docs are written in the same natural language as the question, so they are close in embedding space. With `TOP_K=4` a few doc sections can take every slot.
3. **Some code chunks carry no searchable name.** `gameConfig.ts` is a list of top-level `export const` lines. The chunker groups them into one `module` chunk with no symbol, so the embedding header only says `File: src/config/gameConfig.ts`.

Also, small models answer Traditional Chinese questions in Simplified Chinese or English, and lead with prose instead of the location the team asked for.

Every change must be switchable with `.env` so `scripts/evaluate.py` can measure each one against the baseline.

## Decision

Four independent switches, all off by default (off = the previous behaviour):

| Switch | What it does | Needs re-index? |
| --- | --- | --- |
| `HYBRID_SEARCH` | Vector search + BM25 keyword search + identifier-definition matching, merged with Reciprocal Rank Fusion (`RRF_K=60`). Each retriever returns `RETRIEVAL_CANDIDATES` (30). | No |
| `SPLIT_RETRIEVAL` | Of `TOP_K` excerpts, at most `DOC_TOP_K` (1) are documentation; the rest are code. Quotas are caps: a short type gives its slots to the other. Code is listed first. | No |
| `CHUNK_METADATA` | The embedding text gets a header with type (code / documentation), language, symbol, enclosing class of a method, and the names the chunk **defines** and **exports**. | **Yes** (automatic, see below) |
| `PROMPT_VARIANT=v2` | Always Traditional Chinese (no Simplified characters); first paragraph gives file and line numbers and the key constant / function; doc excerpts are labelled as support only. | No |

Details:

- **BM25 in process, not in Qdrant.** `KeywordIndex` (`backend/app/retrieval.py`) is built from the chunks stored in Qdrant (scrolled once) and cached. A signature of all point ids (ids include the file hash) is checked on each hybrid query, so a re-index by the CLI in another process is picked up. The sample project has 67 chunks; a 300-file project a few thousand: building takes milliseconds.
- **Code-aware tokenizer.** `INVINCIBLE_MS` → `invincible_ms`, `invincible`, `ms`; `ScoreSystem` → `scoresystem`, `score`, `system`. The whole identifier is its own rare token (high IDF), so an exact name in the question scores high, and the parts still match prose. Only ASCII words and numbers are indexed (see trade-offs).
- **Identifier channel.** Words in the question that look like code (`snake_CASE`, `camelCase`, `PascalCase` with two humps, `Class.method`, ALL-CAPS of 4+ letters) are matched **case-sensitively** against the names each chunk *defines* (top-level declarations and class methods) and its symbol. This is a third ranked list in RRF. It is what turns "the docs mention `INVINCIBLE_MS`" into "the code that declares `INVINCIBLE_MS` is retrieved".
- **RRF** (`score = Σ 1/(k + rank)`) merges by rank, so cosine similarities and BM25 scores never need a common scale. An item found by several retrievers rises. `k=60` is the value from the original paper and the common default.
- **`defines` / `exports` are always stored in the payload** (comma-separated), whatever `CHUNK_METADATA` says; only the embedding text depends on the switch. So hybrid search can use them without metadata embeddings, and the switches stay independent.
- **Settings fingerprint and automatic full rebuild.** Every point stores `index_config`: chunker version, embedding-text format version, `CHUNK_MAX_CHARS`, `EMBED_MODEL`, document prefix, `CHUNK_METADATA`. When an indexing run (`scripts/index.sh`, the UI button, `POST /index`, the dev container's start script) finds stored values that differ from the current settings — or points without the field, i.e. built by an older version — it drops the collection and rebuilds everything, and says why. `/health` reports `qdrant.reindex_needed`, and `evaluate.py` warns about it. Query-time switches are not in the fingerprint.
- **Observability.** Each source carries `matched_by` (`vector`, `keyword`, `identifier`). `/health` reports the switches under `retrieval`; `evaluate.py` records them in the JSON and prints them in the report header, and `compare.py` shows them for both runs.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Qdrant sparse vectors (BM25 via `Modifier.IDF`) or LlamaIndex `enable_hybrid` | Scales to millions of chunks; one store; server-side fusion | Changes the collection schema (named dense + sparse vectors): a full re-index just to try it, so hybrid could not be toggled per evaluation run; LlamaIndex's default sparse encoder needs `fastembed` and a model download; its default fusion is score-based | Corpus is small; a query-time switch makes A/B runs cheap. Revisit above ~50k chunks |
| `rank_bm25` library | Less code | New dependency; its tokenizer is ours anyway; ~40 lines of BM25 are easy to test | Not worth a dependency |
| Weighted score fusion (`α·cosine + (1−α)·bm25_norm`) | One tunable knob | Needs score normalisation that shifts with every query; α must be tuned | RRF needs no normalisation and is robust with default `k` |
| Index CJK (character bigrams) in BM25 | Chinese questions match Chinese text | In the sample (and a typical team) docs are Chinese and code is not: bigrams pushed the Chinese `README.md` section to the top of BM25 for every Chinese question — the exact crowding we are fixing | Chinese meaning is left to the vector channel |
| Metadata filter in Qdrant (two queries: code, docs) for split retrieval | Guarantees candidates of each type even if one dominates | Two embedding searches, and BM25/identifier lists need their own split anyway | One candidate pool of 30, split in Python, is simpler; in the sample (67 chunks) 30 candidates are almost half the index, so both types are always present. Revisit for large projects |
| Separate `CODE_TOP_K` + `DOC_TOP_K` | Exactly "N code + M docs" | `TOP_K` would stop meaning "excerpts sent to the model", which sizes `LLM_NUM_CTX` | `DOC_TOP_K` caps docs; code gets `TOP_K − DOC_TOP_K` |
| Keep the order by fused rank in split mode | Honest relevance order | Small models cite the first excerpts most | Code first, each group in rank order |
| Re-embed via the existing per-file hash (no fingerprint) | No new payload field | Embedding format is not part of file content; a mixed collection (half old format) is possible after a failed run; no clear message | The fingerprint makes the rule explicit and reports it |
| Turn the switches on by default now | Users get the improvement immediately | No measurement yet; `CHUNK_METADATA` would force every existing install to re-index on upgrade | Measure first (experiment plan), then a new ADR changes defaults |

## Consequences

- **Positive**: Questions that name an identifier retrieve the code that declares it. Docs can no longer take every slot. Each switch can be measured alone with the existing evaluation script, and every report records which switches were on. Settings that change embeddings can no longer leave a mixed index.
- **Negative / trade-offs**:
  - Upgrading triggers **one full re-index** even with every switch off, because existing points have no `index_config` (minutes on CPU for 300 files).
  - With `HYBRID_SEARCH`, `source.score` is an RRF score (about 0.016–0.05), not a cosine similarity; the UI tooltip says so.
  - The BM25 index lives in each backend process's memory and is rebuilt after every re-index (one scroll of all chunks). Fine for thousands of chunks, not for millions.
  - The identifier heuristics can miss (a single-hump name such as `Player` is treated as a plain word) or over-match (an ALL-CAPS acronym). A miss falls back to BM25 + vector; an over-match only adds an empty list.
  - Declaration extraction is regex based (top-level lines and indented members ending in `{`); unusual formatting can hide a name.
  - `PROMPT_VARIANT=v2` answers in Traditional Chinese even for English questions.
- **Follow-ups**: Run the experiment plan on Codespaces and record numbers in `docs/metrics.md`; then a new ADR to change defaults. If projects grow past ~50k chunks, move BM25 to Qdrant sparse vectors.

---

# 0013. 混合檢索、程式碼與文件分開取回、切塊 metadata

- **狀態**：已接受（四項改動預設**全部關閉**；完成 [experiment-plan-retrieval.md](../evaluation/experiment-plan-retrieval.md) 的評估後，再以新的 ADR 調整預設值）
- **日期**：2026-11-02
- **相關**：ADR [0004](0004-chunking-by-file-type.md)（切塊）、ADR [0012](0012-automated-evaluation-metrics.md)（評估指標）、devlog [2026-11-02](../devlog/2026-11-02.md) 問題 3、程式碼 `backend/app/retrieval.py`

## 背景

Codespace 基準線（`qwen2.5-coder:3b`、`TOP_K=4`、只有向量檢索）在「定位設定」類題目上的失敗很一致：問「玩家受傷後的無敵時間在哪裡設定？」時，取回的片段大多是 Markdown（`docs/gameplay.md`、範例專案的 `README.md`），真正定義數值的 `src/config/gameConfig.ts`（`export const INVINCIBLE_MS = 1500`）不在其中，回答就引用文件或說錯檔案。

三個原因，分別處理：

1. **只靠向量檢索，對精確的識別字很弱。** 問題中的 `INVINCIBLE_MS`、`ScoreSystem` 是很明確的線索，但在向量空間裡只是眾多 token 之一；換句話說問題內容的文件反而分數更高。
2. **文件擠掉程式碼。** 文件與問題使用相同的自然語言，在向量空間裡很接近。`TOP_K=4` 時，幾段文件就能占滿所有名額。
3. **有些程式碼片段沒有可搜尋的名稱。** `gameConfig.ts` 是一串頂層 `export const`，切塊器把它們合成一個沒有符號名稱的 `module` 片段，embedding 的標頭只有 `File: src/config/gameConfig.ts`。

此外，小模型常用簡體中文或英文回答繁體中文問題，而且先講一堆說明，而不是團隊想知道的位置。

每項改動都要能用 `.env` 開關，讓 `scripts/evaluate.py` 可以逐項和基準線比較。

## 決策

四個獨立開關，預設全部關閉（關閉 = 原本的行為）：

| 開關 | 作用 | 需要重新索引？ |
| --- | --- | --- |
| `HYBRID_SEARCH` | 向量檢索 + BM25 關鍵字檢索 + 識別字定義比對，以 Reciprocal Rank Fusion 合併（`RRF_K=60`）。每種檢索各取 `RETRIEVAL_CANDIDATES`（30）個候選。 | 不需要 |
| `SPLIT_RETRIEVAL` | `TOP_K` 段中文件最多 `DOC_TOP_K`（1）段，其餘給程式碼。配額是上限：某類不夠時名額讓給另一類。程式碼排在前面。 | 不需要 |
| `CHUNK_METADATA` | embedding 內容加上標頭：類型（程式碼／文件）、語言、符號名稱、method 所屬的 class，以及片段**定義**與 **export** 的名稱。 | **需要**（自動，見下） |
| `PROMPT_VARIANT=v2` | 一律繁體中文（不得有簡體字）；第一段先說檔案與行號、關鍵常數／函式；文件片段標示為僅供補充。 | 不需要 |

細節：

- **BM25 放在後端行程內，不放 Qdrant。** `KeywordIndex`（`backend/app/retrieval.py`）從 Qdrant 中的片段建立（scroll 一次）並快取。每次混合查詢會檢查所有 point id 的簽章（id 包含檔案雜湊），所以 CLI 在另一個行程重新索引也會被偵測到。範例專案有 67 個片段，300 個檔案的專案約數千個，建立只需幾毫秒。
- **理解程式碼的斷詞器。** `INVINCIBLE_MS` → `invincible_ms`、`invincible`、`ms`；`ScoreSystem` → `scoresystem`、`score`、`system`。完整識別字本身是稀有 token（IDF 高），問題中有精確名稱時分數很高；拆開的部分仍能對上一般文字。只索引 ASCII 單字與數字（見取捨）。
- **識別字通道。** 問題中看起來像程式碼的字（`snake_CASE`、`camelCase`、兩段以上的 `PascalCase`、`Class.method`、4 個字母以上的全大寫）會以**區分大小寫**的方式，比對每個片段**定義**的名稱（頂層宣告與 class 的 method）與符號名稱，作為 RRF 的第三份排名。這一步把「文件提到 `INVINCIBLE_MS`」變成「取回宣告 `INVINCIBLE_MS` 的程式碼」。
- **RRF**（`分數 = Σ 1/(k + 名次)`）依名次合併，不需要把 cosine 相似度與 BM25 分數換算到同一尺度。被多種檢索找到的片段會往前排。`k=60` 是原始論文的值，也是常見預設。
- **`defines`／`exports` 一律存進 payload**（逗號分隔），與 `CHUNK_METADATA` 無關；只有 embedding 內容受開關影響。因此混合檢索不必開 metadata embedding 也能用，開關彼此獨立。
- **設定指紋與自動全量重建。** 每個 point 都存 `index_config`：切塊器版本、embedding 內容格式版本、`CHUNK_MAX_CHARS`、`EMBED_MODEL`、文件前綴、`CHUNK_METADATA`。索引時（`scripts/index.sh`、介面按鈕、`POST /index`、dev container 啟動腳本）若發現已存的值與目前設定不同，或 point 沒有這個欄位（舊版建立的索引），就清空 collection 全部重建，並說明原因。`/health` 會回報 `qdrant.reindex_needed`，`evaluate.py` 也會提醒。查詢期的開關不列入指紋。
- **可觀察性。** 每個引用片段都有 `matched_by`（`vector`、`keyword`、`identifier`）。`/health` 在 `retrieval` 下回報各開關；`evaluate.py` 把它們記錄在 JSON 並寫進報告開頭，`compare.py` 也會顯示兩次執行的設定。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| Qdrant sparse vector（以 `Modifier.IDF` 做 BM25）或 LlamaIndex `enable_hybrid` | 可擴展到數百萬片段；單一儲存；由伺服器融合 | 改變 collection 結構（具名 dense + sparse 向量）：光是試用就要全量重建，無法每次評估切換；LlamaIndex 預設的 sparse 編碼器需要 `fastembed` 與下載模型；預設以分數融合 | 語料小；查詢期開關讓 A/B 比較很便宜。超過約 5 萬個片段時再評估 |
| `rank_bm25` 套件 | 程式碼較少 | 多一個依賴；斷詞器反正要自己寫；BM25 約 40 行，容易測試 | 不值得多一個依賴 |
| 加權分數融合（`α·cosine + (1−α)·bm25_norm`） | 一個可調參數 | 需要分數正規化，且每個查詢都不同；α 要調 | RRF 不需正規化，用預設 `k` 就很穩定 |
| BM25 索引中文（字元 bigram） | 中文問題能對上中文內容 | 範例專案（以及一般團隊）文件是中文、程式碼不是：bigram 讓中文 `README.md` 段落在每個中文問題的 BM25 排第一，正是我們要解決的「文件擠掉程式碼」 | 中文語意交給向量通道 |
| 分類取回時在 Qdrant 用 metadata 過濾（程式碼、文件各查一次） | 即使某類壓倒性多，也保證兩類都有候選 | 兩次向量搜尋，而且 BM25／識別字清單還是要自己分 | 單一 30 個候選池在 Python 分類比較簡單；範例專案只有 67 個片段，30 個候選幾乎是一半的索引，兩類一定都有。大型專案再重新評估 |
| 分開的 `CODE_TOP_K` + `DOC_TOP_K` | 完全照「程式碼 N 個 + 文件 M 個」 | `TOP_K` 不再代表「送給模型的片段數」，而 `LLM_NUM_CTX` 是依它估算的 | 以 `DOC_TOP_K` 限制文件數，程式碼得到 `TOP_K − DOC_TOP_K` |
| 分類模式下仍依融合名次排序 | 忠實呈現相關度 | 小模型最常引用前面幾段 | 程式碼在前，各組內依名次排序 |
| 沿用每檔雜湊重新 embedding（不加指紋） | 不需新的 payload 欄位 | embedding 格式不屬於檔案內容；中途失敗可能留下新舊格式混雜的 collection；也沒有清楚的訊息 | 指紋讓規則明確，並會說明原因 |
| 現在就預設開啟 | 使用者立即受益 | 還沒有量測；`CHUNK_METADATA` 會讓所有既有安裝在升級時重新索引 | 先量測（實驗計畫），再以新的 ADR 調整預設值 |

## 後果

- **正面**：提到識別字的問題會取回宣告它的程式碼；文件不再能占滿所有名額；每個開關都能用既有的評估腳本單獨量測，每份報告都記錄開了哪些開關；會改變 embedding 的設定不再造成新舊混雜的索引。
- **負面／取捨**：
  - 升級後即使全部開關都關閉，也會**全量重建一次**索引，因為既有的 point 沒有 `index_config`（300 個檔案在 CPU 上需要數分鐘）。
  - 開啟 `HYBRID_SEARCH` 時，`source.score` 是 RRF 分數（約 0.016–0.05），不是 cosine 相似度；介面的提示文字有說明。
  - BM25 索引存在每個後端行程的記憶體中，每次重新索引後要重建（scroll 一次所有片段）。數千個片段沒問題，數百萬個就不行。
  - 識別字的判斷規則可能漏掉（只有一段的 `Player` 被當成一般單字），也可能誤判（全大寫縮寫）。漏掉時退回 BM25 + 向量；誤判只會多一份空清單。
  - 宣告名稱以正規表示式擷取（頂層的行，以及以 `{` 結尾的縮排成員）；格式特殊時可能抓不到。
  - `PROMPT_VARIANT=v2` 即使是英文問題也會用繁體中文回答。
- **後續工作**：在 Codespaces 跑完實驗計畫，數據記到 `docs/metrics.md`；再以新的 ADR 調整預設值。專案成長到約 5 萬個片段以上時，把 BM25 改為 Qdrant sparse vector。
