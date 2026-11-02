# Experiment plan: hybrid retrieval, split retrieval, chunk metadata, prompt v2

> English first; 繁體中文版本在下方.
> Privacy: only the sample project (`examples/sample-game-frontend/`) is indexed and evaluated.
> Design: [ADR 0013](../decisions/0013-hybrid-retrieval-and-split-retrieval.md). Metrics: [ADR 0012](../decisions/0012-automated-evaluation-metrics.md).

## Goal

Measure each switch from ADR 0013 against the Codespace baseline, one at a time and all together, and decide which to turn on by default. The problem being fixed: for 定位設定 questions the retrieved excerpts are mostly Markdown and the code file that defines the setting is missing.

## Fixed conditions

Everything except the switch under test stays the same in every run:

| Item | Value |
| --- | --- |
| Environment | GitHub Codespaces, 4 cores / 16 GB, CPU only (`.env.codespaces`) |
| Models | `qwen2.5-coder:3b`, `nomic-embed-text` |
| `TOP_K` / `LLM_NUM_CTX` | 4 / 8192 |
| Questions | `questions.yaml` (10, Chinese) **and** `questions-identifiers.yaml` (5, name an identifier) |
| Warm-up | on (default) |

Why two question sets: the main set is phrased the way the team asks and mostly contains **no identifier** (question 1 does not say `INVINCIBLE_MS`). BM25 indexes only ASCII words (ADR 0013), so on those questions the keyword and identifier channels have little to work with; the effect of hybrid search shows mainly on `questions-identifiers.yaml` (ids 11–15).

## How switches are set

Shell variables override `.env` in `docker compose`, so no file is edited and each command shows exactly what is on. Query-time switches only need the backend recreated (`docker compose up -d backend`); `CHUNK_METADATA` also needs an index run, which detects the change and rebuilds everything by itself.

`./scripts/index.sh` first runs `docker compose up -d backend` so the container has the current settings. **Give it the same variables as the run**, or it recreates the backend with the defaults. (Setting the switches in `.env` instead avoids this, at the cost of editing the file between runs.)

Check before every run that `/health` shows the intended settings (`evaluate.py` also prints them and writes them into the report):

```bash
curl -s localhost:8000/health | python3 -m json.tool | grep -A8 '"retrieval"'
```

## Runs

Run them in this order: groups A–D share one index, E–F share the other, so the index is rebuilt only twice.

| Group | Switches | Answers the question |
| --- | --- | --- |
| A. baseline | all off | Reference numbers (current behaviour) |
| B. + hybrid | `HYBRID_SEARCH=true` | Does keyword + identifier search bring the defining code in? |
| C. + split | `SPLIT_RETRIEVAL=true DOC_TOP_K=1` | Does capping docs stop them crowding out code? |
| D. + hybrid + split | both | Do they add up? (optional) |
| E. + metadata | `CHUNK_METADATA=true` (re-index) | Does the "Defines: … INVINCIBLE_MS" header help vector search alone? (optional) |
| F. all on | `HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 CHUNK_METADATA=true PROMPT_VARIANT=v2` | Full package incl. the Traditional-Chinese / code-first prompt |

### A. baseline

```bash
docker compose up -d backend
```

```bash
./scripts/index.sh
```

```bash
python3 scripts/evaluate.py --label codespace-3b-k4-baseline
```

```bash
python3 scripts/evaluate.py --questions docs/evaluation/questions-identifiers.yaml --label codespace-3b-k4-baseline-ident
```

The first `index.sh` after upgrading rebuilds the whole index once (points from older versions have no `index_config`).

### B. + hybrid

```bash
HYBRID_SEARCH=true docker compose up -d backend
```

```bash
python3 scripts/evaluate.py --label codespace-3b-k4-hybrid
```

```bash
python3 scripts/evaluate.py --questions docs/evaluation/questions-identifiers.yaml --label codespace-3b-k4-hybrid-ident
```

### C. + split

```bash
SPLIT_RETRIEVAL=true DOC_TOP_K=1 docker compose up -d backend
```

```bash
python3 scripts/evaluate.py --label codespace-3b-k4-split
```

```bash
python3 scripts/evaluate.py --questions docs/evaluation/questions-identifiers.yaml --label codespace-3b-k4-split-ident
```

### D. + hybrid + split (optional)

```bash
HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 docker compose up -d backend
```

```bash
python3 scripts/evaluate.py --label codespace-3b-k4-hybrid-split
```

### E. + metadata (optional; re-indexes)

```bash
CHUNK_METADATA=true ./scripts/index.sh
```

`index.sh` first runs `docker compose up -d backend`, so it recreates the backend with the variables given to it and then indexes.

The index run should print `Index settings changed, rebuilding everything` with `chunk_metadata=off` → `on`.

```bash
python3 scripts/evaluate.py --label codespace-3b-k4-metadata
```

### F. all on

```bash
HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 CHUNK_METADATA=true PROMPT_VARIANT=v2 ./scripts/index.sh
```

(Nothing to rebuild if E ran just before; otherwise a full rebuild.)

```bash
python3 scripts/evaluate.py --label codespace-3b-k4-all
```

```bash
python3 scripts/evaluate.py --questions docs/evaluation/questions-identifiers.yaml --label codespace-3b-k4-all-ident
```

### Back to the baseline afterwards

```bash
docker compose up -d backend
```

```bash
./scripts/index.sh
```

### Judge and compare

Fill in 「人工判定正確性」 in every `.md` report, then `--apply-manual` it (see [README](README.md)). Compare each group with A:

```bash
python3 scripts/compare.py docs/evaluation/results/<date>-codespace-3b-k4-baseline.json docs/evaluation/results/<date>-codespace-3b-k4-hybrid.json --out docs/evaluation/results/<date>-baseline-vs-hybrid.md
```

Same for `-split`, `-all`, and the `-ident` pairs.

## What to look at, per group

Metric names are those in the report summary and `compare.py`. "Retrieval" metrics do not depend on the LLM, so they are the most reliable signal with a 3B model.

| Group | Primary metrics (expected direction) | Watch for |
| --- | --- | --- |
| B. hybrid | `-ident` set: **Defining file retrieved ↑** (questions 11, 13, 14 should all retrieve their defining file), Code file retrieved ↑. Main set: little change expected | Main-set metrics should not drop; check `matched_by` in the JSON sources to see which channel found what. Latency: retrieval adds milliseconds, first-token time should not move |
| C. split | **Docs among retrieved chunks ↓** (≤ 25 % with `TOP_K=4`, `DOC_TOP_K=1`), **Code file retrieved ↑**, Defining file retrieved ↑ (questions 1, 8, 9) | Doc file retrieved will drop — expected; check questions whose key facts live in docs (2, 3, 6) did not lose correctness |
| D. hybrid + split | Better than B and C alone on Defining file retrieved | If not better than C, hybrid adds little for Chinese questions |
| E. metadata | Main set question 1: Defining file retrieved (`gameConfig.ts` now has `Defines: … INVINCIBLE_MS`) | Whether cross-lingual matching (無敵 ↔ invincible) is enough for nomic-embed-text |
| F. all on | Defining file retrieved, Expected file cited with [n] ↑, **Answers with Simplified = 0**, Manual correctness ↑, Trick question refused unchanged | Does v2 make the 3B model cite locations first (read the answers)? Token count and total time (v2 prompt is longer) |

Record the summary rows in [`docs/metrics.md`](../metrics.md) section 4 (one row per group, with the report link). Never fill in numbers that were not measured.

## Decision rule

- Turn a switch on by default when it improves Defining file retrieved or Manual correctness and does not lower Manual correctness on any question type. Write a new ADR for the change of defaults.
- If C alone gives most of the gain, keep hybrid optional (it then mainly helps questions that name identifiers).

---

# 實驗計畫：混合檢索、分類取回、切塊 metadata、提示 v2

> 隱私：只索引與評估範例專案（`examples/sample-game-frontend/`）。
> 設計：[ADR 0013](../decisions/0013-hybrid-retrieval-and-split-retrieval.md)。指標：[ADR 0012](../decisions/0012-automated-evaluation-metrics.md)。

## 目標

逐一、以及全部一起量測 ADR 0013 的各個開關，和 Codespace 基準線比較，決定哪些要預設開啟。要解決的問題：「定位設定」類題目取回的片段多半是 Markdown，定義設定的程式碼檔沒有被取回。

## 固定條件

除了要測的開關，每次執行都相同：

| 項目 | 值 |
| --- | --- |
| 環境 | GitHub Codespaces，4 核心／16GB，只有 CPU（`.env.codespaces`） |
| 模型 | `qwen2.5-coder:3b`、`nomic-embed-text` |
| `TOP_K`／`LLM_NUM_CTX` | 4／8192 |
| 題目 | `questions.yaml`（10 題，中文）**以及** `questions-identifiers.yaml`（5 題，題目直接寫出識別字） |
| 暖機 | 開啟（預設） |

為什麼要兩組題目：主要題組是團隊平常的問法，大多**沒有識別字**（第 1 題沒有寫 `INVINCIBLE_MS`）。BM25 只索引 ASCII 單字（ADR 0013），所以這些題目上關鍵字與識別字通道能用的線索很少；混合檢索的效果主要會出現在 `questions-identifiers.yaml`（11–15 題）。

## 如何設定開關

`docker compose` 會以 shell 變數覆蓋 `.env`，因此不用改檔案，每條指令也清楚顯示開了什麼。查詢期開關只要重建 backend 容器（`docker compose up -d backend`）；`CHUNK_METADATA` 還要執行一次索引，索引器會自己偵測到設定改變並全量重建。

`./scripts/index.sh` 會先執行 `docker compose up -d backend`，確保容器使用目前的設定。**執行它時要帶上與該組相同的變數**，否則會以預設值重建 backend（例如 `CHUNK_METADATA=true ./scripts/index.sh`）。改用 `.env` 設定開關可以避免這個問題，代價是每組之間要改檔案。

每次執行前確認 `/health` 顯示的是預期設定（`evaluate.py` 也會印出並寫進報告）：

```bash
curl -s localhost:8000/health | python3 -m json.tool | grep -A8 '"retrieval"'
```

## 執行組合

依這個順序執行：A–D 共用一份索引，E–F 共用另一份，索引只需要重建兩次。

| 組別 | 開關 | 回答的問題 |
| --- | --- | --- |
| A. 基準線 | 全部關閉 | 參考數據（目前行為） |
| B. + 混合檢索 | `HYBRID_SEARCH=true` | 關鍵字＋識別字檢索能否把定義的程式碼帶進來？ |
| C. + 分類取回 | `SPLIT_RETRIEVAL=true DOC_TOP_K=1` | 限制文件數量能否避免文件擠掉程式碼？ |
| D. + 混合 + 分類 | 兩者 | 效果能否疊加？（選用） |
| E. + metadata | `CHUNK_METADATA=true`（重新索引） | 「Defines: … INVINCIBLE_MS」標頭能否單靠向量檢索改善？（選用） |
| F. 全部開啟 | `HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 CHUNK_METADATA=true PROMPT_VARIANT=v2` | 完整組合，含繁體中文／程式碼位置優先的提示 |

各組指令與上方英文版相同（指令不需翻譯），label 依序為 `codespace-3b-k4-baseline`、`-hybrid`、`-split`、`-hybrid-split`、`-metadata`、`-all`；補充題組加上 `--questions docs/evaluation/questions-identifiers.yaml` 並在 label 後加 `-ident`。

注意事項：

- 升級後第一次執行 `index.sh` 會全量重建一次（舊版的 point 沒有 `index_config`）。
- E、F 組直接以 `CHUNK_METADATA=true ./scripts/index.sh`（F 組加上其他變數）重建容器並索引。
- E 組的索引輸出應出現 `Index settings changed, rebuilding everything`，並顯示 `chunk_metadata=off` → `on`。
- 全部跑完後，執行 `docker compose up -d backend` 與 `./scripts/index.sh` 回到基準線。
- 每份 `.md` 報告都要填寫「人工判定正確性」並執行 `--apply-manual`，再用 `compare.py` 把每一組與 A 比較。

## 各組要看的指標

指標名稱與報告摘要、`compare.py` 相同。「取回」類指標與 LLM 無關，用 3B 模型時是最可靠的訊號。

| 組別 | 主要指標（預期方向） | 需要注意 |
| --- | --- | --- |
| B. 混合檢索 | `-ident` 題組：**定義檔命中 ↑**（11、13、14 題都應取回定義檔）、程式碼檔命中 ↑。主要題組：預期變化不大 | 主要題組的指標不應下降；可從 JSON 中 sources 的 `matched_by` 看是哪個通道找到的。延遲：檢索只多幾毫秒，首字延遲不應改變 |
| C. 分類取回 | **取回片段中文件比例 ↓**（`TOP_K=4`、`DOC_TOP_K=1` 時 ≤ 25%）、**程式碼檔命中 ↑**、定義檔命中 ↑（1、8、9 題） | 文件檔命中會下降，這是預期的；確認重點在文件中的題目（2、3、6）正確性沒有變差 |
| D. 混合 + 分類 | 定義檔命中優於 B、C 單獨開啟 | 若沒有優於 C，表示混合檢索對中文問題幫助有限 |
| E. metadata | 主要題組第 1 題的定義檔命中（`gameConfig.ts` 現在有 `Defines: … INVINCIBLE_MS`） | nomic-embed-text 的跨語言對應（無敵 ↔ invincible）是否足夠 |
| F. 全部開啟 | 定義檔命中、回答引用預期檔案 ↑、**混入簡體字的回答 = 0**、人工判定正確性 ↑、陷阱題拒答不變 | v2 是否讓 3B 模型先說位置（要讀回答）；token 數與總耗時（v2 提示較長） |

把摘要數據記到 [`docs/metrics.md`](../metrics.md) 第 4 節（每組一列，附報告連結）。沒有量測的數字不要填。

## 決策規則

- 某個開關若能提升定義檔命中或人工判定正確性，且沒有讓任何題型的人工判定正確性下降，就改為預設開啟，並新增 ADR 記錄預設值的改變。
- 若 C 單獨就帶來大部分的改善，混合檢索維持選用（主要幫助直接寫出識別字的問題）。
