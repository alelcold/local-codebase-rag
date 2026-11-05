# Experiment plan: hybrid retrieval, split retrieval, chunk metadata, prompt v2, threshold, rerank, prompt v3

> English first; 繁體中文版本在下方.
> Privacy: only the sample project (`examples/sample-game-frontend/`) is indexed and evaluated.
> Design: [ADR 0013](../decisions/0013-hybrid-retrieval-and-split-retrieval.md), [ADR 0014](../decisions/0014-similarity-threshold.md) (threshold), [ADR 0015](../decisions/0015-rerank.md) (rerank), [ADR 0016](../decisions/0016-refuse-out-of-scope-questions-in-the-prompt.md) (prompt v3, refusing out-of-scope questions). Metrics: [ADR 0012](../decisions/0012-automated-evaluation-metrics.md).

## Goal

Measure each switch from ADR 0013 against the Codespace baseline, one at a time and all together, and decide which to turn on by default. The problem being fixed: for 定位設定 questions the retrieved excerpts are mostly Markdown and the code file that defines the setting is missing.

## Fixed conditions

Everything except the switch under test stays the same in every run:

| Item | Value |
| --- | --- |
| Environment | GitHub Codespaces, 4 cores / 16 GB, CPU only (`.env.codespaces`) |
| Models | `qwen2.5-coder:3b`, `nomic-embed-text` |
| `TOP_K` / `LLM_NUM_CTX` | 4 / 8192 |
| Questions | `questions.yaml` (10, Chinese) **and** `questions-identifiers.yaml` (5, name an identifier); group J also `questions-out-of-scope.yaml` (8: 5 trick, 3 control) |
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

Run them in this order: groups A–D, then G and H, share one index; E, F and I share the other, so the index is rebuilt only twice. G and I need the results of A–F first (the threshold is calibrated from them).

| Group | Switches | Answers the question |
| --- | --- | --- |
| A. baseline | all off | Reference numbers (current behaviour) |
| B. + hybrid | `HYBRID_SEARCH=true` | Does keyword + identifier search bring the defining code in? |
| C. + split | `SPLIT_RETRIEVAL=true DOC_TOP_K=1` | Does capping docs stop them crowding out code? |
| D. + hybrid + split | both | Do they add up? (optional) |
| E. + metadata | `CHUNK_METADATA=true` (re-index) | Does the "Defines: … INVINCIBLE_MS" header help vector search alone? (optional) |
| F. all on | `HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 CHUNK_METADATA=true PROMPT_VARIANT=v2` | Full package incl. the Traditional-Chinese / code-first prompt |
| G. + threshold | `SCORE_THRESHOLD=<calibrated>` (ADR 0014) | Does the trick question (Q10) get refused without the LLM, and at what cost to correct answers? |
| H. + rerank | `RERANK=true RERANK_CANDIDATES=10 RERANK_TOP_N=4` (ADR 0015; image built with `INSTALL_RERANK=true`) | Does a cross-encoder put the defining code into the top 4, and how many seconds does it cost on CPU? |
| I. hybrid + split + rerank | `HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 RERANK=true RERANK_TOP_N=4` (`RERANK_CANDIDATES` default 10). **Redefined on 2026-11-03**, see [I](#i-hybrid--split--rerank-redefined-2026-11-03) | Does rerank, with hybrid, improve on C (split), the best main-set retrieval so far? |
| J. D + prompt v3 | `HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 PROMPT_VARIANT=v3` (ADR 0016) | Does an explicit "not found" rule make the 3B model refuse features that do not exist (Q10, ids 21–25), without refusing real questions (ids 26–28, main set)? |

`RERANK_TOP_N=4` (not the default 3) in H and I keeps the number of excerpts sent to the model equal to the other groups' `TOP_K=4`, so only the choice of excerpts changes. Run H once more with `RERANK_TOP_N=3` if you want to measure the default.

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

### G. + threshold (after A–F)

**The threshold value is not chosen by hand.** Calibrate it from the A–F reports first. The script groups reports by embedding (with or without `CHUNK_METADATA`, which changes every vector) and prints, for each candidate, how many expected excerpts would be dropped and how many other excerpts blocked, plus a suggestion — or says the data is not enough.

```bash
python3 scripts/calibrate_threshold.py --out docs/evaluation/results/<date>-calibration.md
```

Use the suggestion from the `nomic-embed-text` group (no metadata) for G. Do not use a generic 0.70: with `nomic-embed-text` a relevant Markdown excerpt has been measured at only 0.60 (ADR 0014). If the script suggests nothing, skip G and I and record why in `docs/metrics.md`.

G runs on the A–D index. Re-run `index.sh` without variables first if E or F already rebuilt it with metadata:

```bash
./scripts/index.sh
```

```bash
SCORE_THRESHOLD=<value> docker compose up -d backend
```

```bash
python3 scripts/evaluate.py --label codespace-3b-k4-threshold
```

```bash
python3 scripts/evaluate.py --questions docs/evaluation/questions-identifiers.yaml --label codespace-3b-k4-threshold-ident
```

Check in the report: 「因門檻直接拒答」 should be 1 (question 10) and 0 for the others; 「陷阱題正確拒答」 1/1.

**Result (2026-11-03): G skipped.** The calibration ([2026-11-03-threshold-calibration.md](results/2026-11-03-threshold-calibration.md), from the A and C reports) suggests no value: expected and other excerpts have almost the same cosine distribution (median 0.616 vs 0.604), every threshold up to 0.45 blocks nothing, and 0.50 already drops 2 of 27 expected excerpts. The generic 0.70 would drop 25 of 27 (93%). Details in the devlog of 2026-11-03.

### H. + rerank

Rerank needs the optional dependencies (about +1.5 GB, ADR 0015). Build once:

```bash
INSTALL_RERANK=true docker compose build backend
```

```bash
RERANK=true RERANK_CANDIDATES=10 RERANK_TOP_N=4 docker compose up -d backend
```

The first query downloads the model into the `reranker_models` volume (about 1 GB for `bge-reranker-base`) and loads it; `evaluate.py`'s warm-up query absorbs this, and the `done` event reports it separately as `rerank_load_seconds`.

```bash
python3 scripts/evaluate.py --label codespace-3b-k4-rerank
```

```bash
python3 scripts/evaluate.py --questions docs/evaluation/questions-identifiers.yaml --label codespace-3b-k4-rerank-ident
```

Optional H′: the same with `RERANK_MODEL=BAAI/bge-reranker-v2-m3` (label `codespace-3b-k4-rerank-m3`), to see whether the stronger model is worth about three times the CPU time (ADR 0015, metrics §4b). Add a row to metrics §4a if you run it.

### I. hybrid + split + rerank (redefined 2026-11-03)

**Original definition**: F + `SCORE_THRESHOLD` (metadata calibration) + rerank. **Changed** because:

- There is no threshold to use: the calibration found none for the A–D index, and none can be calibrated for the metadata index at all — F's reports are hybrid runs written before `vector_score` existed, so they hold no cosine scores ([calibration](results/2026-11-03-threshold-calibration.md), "Not used").
- F did not beat C on retrieval: defining file retrieved (main) 0/3 vs C's 1/3, code file retrieved 56 % vs 67 % (`docs/metrics.md` §4a). Metadata and prompt v2 would only add variables.
- Hybrid search made the identifier questions retrieve their defining file 3/3 (B), and split retrieval brought code into the main set (C). Rerank on top of both tests whether a cross-encoder improves the *choice* among those candidates.

I runs on the A–D index (no `CHUNK_METADATA`) with the rerank image built for H. `index.sh` recreates the backend with the variables given, and rebuilds the index only if F's metadata index is still there:

```bash
HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 RERANK=true RERANK_TOP_N=4 ./scripts/index.sh
```

```bash
python3 scripts/evaluate.py --label codespace-3b-k4-hybrid-split-rerank
```

```bash
python3 scripts/evaluate.py --questions docs/evaluation/questions-identifiers.yaml --label codespace-3b-k4-hybrid-split-rerank-ident
```

Compare (main and `-ident` each): A → H (rerank alone), A → I, and **C → I** (what rerank and hybrid add to split). D (hybrid + split without rerank) was not run, so C → I shows hybrid and rerank together; run D as well to separate them.

```bash
python3 scripts/compare.py docs/evaluation/results/2026-11-03-codespace-3b-k4-baseline.json docs/evaluation/results/<date>-codespace-3b-k4-rerank.json --out docs/evaluation/results/<date>-baseline-vs-rerank.md
```

```bash
python3 scripts/compare.py docs/evaluation/results/2026-11-03-codespace-3b-k4-baseline.json docs/evaluation/results/<date>-codespace-3b-k4-hybrid-split-rerank.json --out docs/evaluation/results/<date>-baseline-vs-hybrid-split-rerank.md
```

```bash
python3 scripts/compare.py docs/evaluation/results/2026-11-03-codespace-3b-k4-split.json docs/evaluation/results/<date>-codespace-3b-k4-hybrid-split-rerank.json --out docs/evaluation/results/<date>-split-vs-hybrid-split-rerank.md
```

### J. D + prompt v3 (ADR 0016)

Q10 was not refused in any group A–I, the threshold could not be calibrated (G) and rerank scores do not separate it either (Q10 0.33 vs Q9 0.0165 in I). J changes **only the prompt** on top of D, so D is its reference: same retrieval, same index (A–D, no `CHUNK_METADATA`), no rerank image needed.

First, the reference for the new question set: D with prompt v1 on `questions-out-of-scope.yaml` (D's main and `-ident` reports already exist):

```bash
HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 ./scripts/index.sh
```

```bash
python3 scripts/evaluate.py --questions docs/evaluation/questions-out-of-scope.yaml --label codespace-3b-k4-hybrid-split-oos
```

Then J. `PROMPT_VARIANT` is query time only, so recreating the backend is enough:

```bash
HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 PROMPT_VARIANT=v3 docker compose up -d backend
```

Check that `/health` reports `"prompt_variant": "v3"`, then:

```bash
python3 scripts/evaluate.py --label codespace-3b-k4-hybrid-split-v3
```

```bash
python3 scripts/evaluate.py --questions docs/evaluation/questions-identifiers.yaml --label codespace-3b-k4-hybrid-split-v3-ident
```

```bash
python3 scripts/evaluate.py --questions docs/evaluation/questions-out-of-scope.yaml --label codespace-3b-k4-hybrid-split-v3-oos
```

Compare D → J for all three sets:

```bash
python3 scripts/compare.py docs/evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split.json docs/evaluation/results/<date>-codespace-3b-k4-hybrid-split-v3.json --out docs/evaluation/results/<date>-hybrid-split-vs-hybrid-split-v3.md
```

```bash
python3 scripts/compare.py docs/evaluation/results/2026-11-03-codespace-3b-k4-hybrid-split-ident.json docs/evaluation/results/<date>-codespace-3b-k4-hybrid-split-v3-ident.json --out docs/evaluation/results/<date>-hybrid-split-vs-hybrid-split-v3-ident.md
```

```bash
python3 scripts/compare.py docs/evaluation/results/<date>-codespace-3b-k4-hybrid-split-oos.json docs/evaluation/results/<date>-codespace-3b-k4-hybrid-split-v3-oos.json --out docs/evaluation/results/<date>-hybrid-split-vs-hybrid-split-v3-oos.md
```

Read every answer flagged `(**falsely refused**)` and every trick-question answer: the automatic refusal check is a keyword screen (a 「沒有」 next to invented code would still need the forbidden-word check to catch it).

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

## Mac M2 run (`scripts/benchmark-mac.sh`)

The Codespaces conditions above do not apply on the Mac. There, `scripts/benchmark-mac.sh` (ADR 0017) runs groups **A** (`baseline`) and **D** (`hybrid-split`), and with `--with-rerank` also **I** (`hybrid-split-rerank`, `RERANK_CANDIDATES=20 RERANK_TOP_N=8`), on both question sets, with `qwen2.5-coder:14b` and `TOP_K=8`. Labels: `mac-m2-14b-k8-<group>[-ident]`. Switches are exported per group as shown in [How switches are set](#how-switches-are-set), `/health` is checked before each group, and the model is unloaded before each run so no group reuses another's cached prompt. It ends with `compare.py` (A → D, D → I) and a summary in the column layout of `docs/metrics.md`.

## What to look at, per group

Metric names are those in the report summary and `compare.py`. "Retrieval" metrics do not depend on the LLM, so they are the most reliable signal with a 3B model.

| Group | Primary metrics (expected direction) | Watch for |
| --- | --- | --- |
| B. hybrid | `-ident` set: **Defining file retrieved ↑** (questions 11, 13, 14 should all retrieve their defining file), Code file retrieved ↑. Main set: little change expected | Main-set metrics should not drop; check `matched_by` in the JSON sources to see which channel found what. Latency: retrieval adds milliseconds, first-token time should not move |
| C. split | **Docs among retrieved chunks ↓** (≤ 25 % with `TOP_K=4`, `DOC_TOP_K=1`), **Code file retrieved ↑**, Defining file retrieved ↑ (questions 1, 8, 9) | Doc file retrieved will drop — expected; check questions whose key facts live in docs (2, 3, 6) did not lose correctness |
| D. hybrid + split | Better than B and C alone on Defining file retrieved | If not better than C, hybrid adds little for Chinese questions |
| E. metadata | Main set question 1: Defining file retrieved (`gameConfig.ts` now has `Defines: … INVINCIBLE_MS`) | Whether cross-lingual matching (無敵 ↔ invincible) is enough for nomic-embed-text |
| F. all on | Defining file retrieved, Expected file cited with [n] ↑, **Answers with Simplified = 0**, Manual correctness ↑, Trick question refused unchanged | Does v2 make the 3B model cite locations first (read the answers)? Token count and total time (v2 prompt is longer) |
| G. threshold | **Trick question refused = 1/1**, **Refused by SCORE_THRESHOLD = 1** (question 10 only) | Any other question refused, or Expected-file recall ↓ = the threshold is too high; lower it with `calibrate_threshold.py --max-drop 0` |
| H. rerank | Defining file retrieved ↑, Expected file cited with [n] ↑, Manual correctness ↑; **Rerank time, mean** | Rerank time vs. first-token time: is the gain worth the seconds on CPU? |
| I. hybrid + split + rerank | vs. C: Defining file retrieved (main) ↑, Code file retrieved ≥ C; `-ident`: Defining file retrieved stays 3/3; **Rerank time, mean** | Rerank time vs. first-token time; whether rerank pushes the one allowed doc excerpt out (Docs among retrieved chunks should stay ≤ 25 %) |
| J. D + prompt v3 | vs. D: **Refusal rate** ↑ (main: Q10; `-oos`: ids 21–25), **False refusal rate = 0** (main, `-ident`, `-oos` ids 26–28), **Answers with Simplified = 0**; retrieval metrics unchanged (same retrieval) | Answers that refuse *and* explain something anyway; whether the fixed sentence is copied exactly; any real question now answered with 「找不到」; Manual correctness on the main set must not drop |

Record the summary rows in [`docs/metrics.md`](../metrics.md) section 4 (one row per group, with the report link). Never fill in numbers that were not measured.

## Decision rule

- Turn a switch on by default when it improves Defining file retrieved or Manual correctness and does not lower Manual correctness on any question type. Write a new ADR for the change of defaults.
- If C alone gives most of the gain, keep hybrid optional (it then mainly helps questions that name identifiers).
- Threshold (G): turn on only with the calibrated value, and only if no answerable question was refused. The value is tied to the embedding model; a new model needs a new calibration.
- Rerank (H): turn on by default only if Manual correctness improves **and** the rerank time is acceptable next to the first-token time on the target machine.
- Prompt v3 (J): make it the default only if the refusal rate rises (at least Q10 and most of 21–25), the false refusal rate stays 0 on every set, and main-set Manual correctness does not drop. A single false refusal of a real question outweighs one more refused trick question: a wrong "not found" hides code that exists. Write a new ADR for the change of default; do not edit `.env.codespaces` until then.

---

# 實驗計畫：混合檢索、分類取回、切塊 metadata、提示 v2、相似度門檻、Rerank、提示 v3

> 隱私：只索引與評估範例專案（`examples/sample-game-frontend/`）。
> 設計：[ADR 0013](../decisions/0013-hybrid-retrieval-and-split-retrieval.md)、[ADR 0014](../decisions/0014-similarity-threshold.md)（門檻）、[ADR 0015](../decisions/0015-rerank.md)（Rerank）、[ADR 0016](../decisions/0016-refuse-out-of-scope-questions-in-the-prompt.md)（提示 v3，拒答範圍外的問題）。指標：[ADR 0012](../decisions/0012-automated-evaluation-metrics.md)。

## 目標

逐一、以及全部一起量測 ADR 0013 的各個開關，和 Codespace 基準線比較，決定哪些要預設開啟。要解決的問題：「定位設定」類題目取回的片段多半是 Markdown，定義設定的程式碼檔沒有被取回。

## 固定條件

除了要測的開關，每次執行都相同：

| 項目 | 值 |
| --- | --- |
| 環境 | GitHub Codespaces，4 核心／16GB，只有 CPU（`.env.codespaces`） |
| 模型 | `qwen2.5-coder:3b`、`nomic-embed-text` |
| `TOP_K`／`LLM_NUM_CTX` | 4／8192 |
| 題目 | `questions.yaml`（10 題，中文）**以及** `questions-identifiers.yaml`（5 題，題目直接寫出識別字）；J 組另外加上 `questions-out-of-scope.yaml`（8 題：5 題陷阱題、3 題對照題） |
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

依這個順序執行：A–D 以及之後的 G、H 共用一份索引；E、F、I 共用另一份，索引只需要重建兩次。G 與 I 需要先有 A～F 的結果（門檻要從這些結果校準）。

| 組別 | 開關 | 回答的問題 |
| --- | --- | --- |
| A. 基準線 | 全部關閉 | 參考數據（目前行為） |
| B. + 混合檢索 | `HYBRID_SEARCH=true` | 關鍵字＋識別字檢索能否把定義的程式碼帶進來？ |
| C. + 分類取回 | `SPLIT_RETRIEVAL=true DOC_TOP_K=1` | 限制文件數量能否避免文件擠掉程式碼？ |
| D. + 混合 + 分類 | 兩者 | 效果能否疊加？（選用） |
| E. + metadata | `CHUNK_METADATA=true`（重新索引） | 「Defines: … INVINCIBLE_MS」標頭能否單靠向量檢索改善？（選用） |
| F. 全部開啟 | `HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 CHUNK_METADATA=true PROMPT_VARIANT=v2` | 完整組合，含繁體中文／程式碼位置優先的提示 |
| G. + 門檻 | `SCORE_THRESHOLD=<校準值>`（ADR 0014） | 陷阱題（第 10 題）能否不呼叫 LLM 就拒答？正確回答要付出多少代價？ |
| H. + Rerank | `RERANK=true RERANK_CANDIDATES=10 RERANK_TOP_N=4`（ADR 0015；映像檔以 `INSTALL_RERANK=true` 建置） | 交叉編碼器能否把定義的程式碼排進前 4 段？在 CPU 上要多花幾秒？ |
| I. 混合 + 分類 + Rerank | `HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 RERANK=true RERANK_TOP_N=4`（`RERANK_CANDIDATES` 用預設 10）。**2026-11-03 重新定義**，原因見下方 I 組說明 | 加上混合檢索與 Rerank，能否勝過目前主要題組檢索最好的 C（分類取回）？ |
| J. D + 提示 v3 | `HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 PROMPT_VARIANT=v3`（ADR 0016） | 明確的「找不到」規則能否讓 3B 模型拒答不存在的功能（第 10 題、21–25 題），同時不拒答真實問題（26–28 題、主要題組）？ |

H、I 組使用 `RERANK_TOP_N=4`（不是預設的 3），讓送進模型的片段數與其他組的 `TOP_K=4` 相同，只改變「選哪些片段」。想量測預設值時，可以再以 `RERANK_TOP_N=3` 跑一次 H 組。

各組指令與上方英文版相同（指令不需翻譯），label 依序為 `codespace-3b-k4-baseline`、`-hybrid`、`-split`、`-hybrid-split`、`-metadata`、`-all`；補充題組加上 `--questions docs/evaluation/questions-identifiers.yaml` 並在 label 後加 `-ident`。

注意事項：

- 升級後第一次執行 `index.sh` 會全量重建一次（舊版的 point 沒有 `index_config`）。
- E、F 組直接以 `CHUNK_METADATA=true ./scripts/index.sh`（F 組加上其他變數）重建容器並索引。
- E 組的索引輸出應出現 `Index settings changed, rebuilding everything`，並顯示 `chunk_metadata=off` → `on`。
- **G 組的門檻值不能自己挑**：先跑完 A～F，再用 `python3 scripts/calibrate_threshold.py --out docs/evaluation/results/<日期>-calibration.md` 從 A～F 的結果決定。腳本會依 embedding（有無 `CHUNK_METADATA`，它會改變所有向量）分組，列出每個候選值會丟掉多少正確片段、擋掉多少非預期片段，並給出建議值；資料不足時會直接說明、不給數字。G 組用 `nomic-embed-text`（無 metadata）那組的建議值；不要用通用的 0.70：實測中一個相關的 Markdown 片段用 nomic-embed-text 只有 0.60 分（ADR 0014）。腳本沒有給建議值時，略過 G、I 組，並在 `docs/metrics.md` 記錄原因。
- G 組在 A–D 的索引上執行（若 E、F 已改成 metadata 索引，先不帶變數執行 `./scripts/index.sh`），指令為 `SCORE_THRESHOLD=<值> docker compose up -d backend`，label `codespace-3b-k4-threshold`。報告中「因門檻直接拒答」應為 1（第 10 題），其他題為 0；「陷阱題正確拒答」為 1/1。
- H 組需要 rerank 的選用依賴（約 +1.5 GB，ADR 0015），先建置一次：`INSTALL_RERANK=true docker compose build backend`，再 `RERANK=true RERANK_CANDIDATES=10 RERANK_TOP_N=4 docker compose up -d backend`，label `codespace-3b-k4-rerank`。第一次查詢會把模型下載到 `reranker_models` volume 並載入；`evaluate.py` 的暖機查詢會吸收這段時間，`done` 事件也會另外以 `rerank_load_seconds` 回報。選用的 H′ 組：同樣指令加上 `RERANK_MODEL=BAAI/bge-reranker-v2-m3`（label `codespace-3b-k4-rerank-m3`），看較強的模型是否值得約三倍的 CPU 時間（ADR 0015、metrics §4b）；有跑的話在 metrics §4a 加一列。
- **G 組結果（2026-11-03）：略過。** 校準（[2026-11-03-threshold-calibration.md](results/2026-11-03-threshold-calibration.md)，使用 A、C 組的報告）沒有給出建議值：預期與非預期片段的 cosine 分布幾乎相同（中位數 0.616 與 0.604），0.45 以下的門檻什麼都擋不到，0.50 就已經丟掉 27 個正確片段中的 2 個；通用的 0.70 會丟掉 27 個中的 25 個（93%）。詳見 2026-11-03 的 devlog。
- **I 組（2026-11-03 重新定義）**：原本是「F + 門檻（metadata 版校準值）+ Rerank」，改為 `HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 RERANK=true RERANK_TOP_N=4`（`RERANK_CANDIDATES` 用預設 10），label `codespace-3b-k4-hybrid-split-rerank`。原因：
  - 沒有門檻可用：A–D 索引校準不出門檻；metadata 索引則完全無法校準，因為 F 的報告是 `vector_score` 出現前的混合檢索結果，沒有 cosine 分數（見校準輸出的「未使用的報告」）。
  - F 的檢索沒有比 C 好：主要題組定義檔命中 0/3（C 為 1/3）、程式碼檔命中 56%（C 為 67%）（`docs/metrics.md` §4a），metadata 與提示 v2 只會多加變因。
  - 混合檢索讓識別字題組的定義檔命中達到 3/3（B），分類取回讓主要題組取回程式碼（C）；在兩者之上加 Rerank，測的是交叉編碼器能否在這些候選中選得更好。
- I 組在 A–D 索引（不開 `CHUNK_METADATA`）與 H 組建好的 rerank 映像檔上執行：`HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 RERANK=true RERANK_TOP_N=4 ./scripts/index.sh`（若 F 的 metadata 索引還在，會自動重建），再分別以主要題組與識別字題組（label 加 `-ident`）執行 `evaluate.py`。
- 比較（主要與識別字題組各一份）：A → H（只有 Rerank）、A → I、**C → I**（混合檢索與 Rerank 在分類取回之上的效果），指令同英文版。D 組（混合 + 分類、不含 Rerank）沒有跑，所以 C → I 看到的是混合檢索與 Rerank 的合計效果；要分開兩者需要再跑 D 組。
- **J 組：D + 提示 v3（ADR 0016）**。第 10 題在 A～I 組都沒有拒答，門檻校準不出來（G），rerank 分數也分不開（I 組第 10 題 0.33，高於第 9 題的 0.0165）。J 組在 D 之上**只改提示**，所以以 D 為參考：同樣的檢索、同一份索引（A–D，不開 `CHUNK_METADATA`），不需要 rerank 映像檔。指令（與英文版相同）：
  1. 先補 D 組在新題組上的參考數據（D 的主要與 `-ident` 報告已經有了）：`HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 ./scripts/index.sh`，再 `python3 scripts/evaluate.py --questions docs/evaluation/questions-out-of-scope.yaml --label codespace-3b-k4-hybrid-split-oos`。
  2. `PROMPT_VARIANT` 只影響查詢，重建 backend 即可：`HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 PROMPT_VARIANT=v3 docker compose up -d backend`，確認 `/health` 顯示 `"prompt_variant": "v3"`。
  3. 三個題組各跑一次，label 為 `codespace-3b-k4-hybrid-split-v3`、`-v3-ident`（`--questions docs/evaluation/questions-identifiers.yaml`）、`-v3-oos`（`--questions docs/evaluation/questions-out-of-scope.yaml`）。
  4. 三個題組各以 `compare.py` 比較 D → J（指令見英文版）。
  5. 每一個標示 `(**falsely refused**)` 的回答與每一題陷阱題的回答都要讀過：自動拒答判定只是關鍵字篩選（編造程式碼時旁邊寫了「沒有」，要靠禁用字才抓得到）。
- 全部跑完後，執行 `docker compose up -d backend` 與 `./scripts/index.sh` 回到基準線。
- 每份 `.md` 報告都要填寫「人工判定正確性」並執行 `--apply-manual`，再用 `compare.py` 把每一組與 A 比較。

## Mac M2 上的執行（`scripts/benchmark-mac.sh`）

上方的 Codespaces 固定條件不適用於 Mac。在 Mac 上由 `scripts/benchmark-mac.sh`（ADR 0017）以 `qwen2.5-coder:14b`、`TOP_K=8` 執行 **A** 組（`baseline`）與 **D** 組（`hybrid-split`），加上 `--with-rerank` 時另跑 **I** 組（`hybrid-split-rerank`，`RERANK_CANDIDATES=20 RERANK_TOP_N=8`），兩個題組都跑。label 為 `mac-m2-14b-k8-<組別>[-ident]`。開關依[如何設定開關](#如何設定開關)的方式逐組 export，每組執行前檢查 `/health`，每次評估前卸載模型，避免各組重用彼此的提示快取。最後執行 `compare.py`（A → D、D → I），並輸出欄位與 `docs/metrics.md` 相同的摘要。

## 各組要看的指標

指標名稱與報告摘要、`compare.py` 相同。「取回」類指標與 LLM 無關，用 3B 模型時是最可靠的訊號。

| 組別 | 主要指標（預期方向） | 需要注意 |
| --- | --- | --- |
| B. 混合檢索 | `-ident` 題組：**定義檔命中 ↑**（11、13、14 題都應取回定義檔）、程式碼檔命中 ↑。主要題組：預期變化不大 | 主要題組的指標不應下降；可從 JSON 中 sources 的 `matched_by` 看是哪個通道找到的。延遲：檢索只多幾毫秒，首字延遲不應改變 |
| C. 分類取回 | **取回片段中文件比例 ↓**（`TOP_K=4`、`DOC_TOP_K=1` 時 ≤ 25%）、**程式碼檔命中 ↑**、定義檔命中 ↑（1、8、9 題） | 文件檔命中會下降，這是預期的；確認重點在文件中的題目（2、3、6）正確性沒有變差 |
| D. 混合 + 分類 | 定義檔命中優於 B、C 單獨開啟 | 若沒有優於 C，表示混合檢索對中文問題幫助有限 |
| E. metadata | 主要題組第 1 題的定義檔命中（`gameConfig.ts` 現在有 `Defines: … INVINCIBLE_MS`） | nomic-embed-text 的跨語言對應（無敵 ↔ invincible）是否足夠 |
| F. 全部開啟 | 定義檔命中、回答引用預期檔案 ↑、**混入簡體字的回答 = 0**、人工判定正確性 ↑、陷阱題拒答不變 | v2 是否讓 3B 模型先說位置（要讀回答）；token 數與總耗時（v2 提示較長） |
| G. 門檻 | **陷阱題正確拒答 = 1/1**、**因門檻直接拒答 = 1**（只有第 10 題） | 其他題被拒答，或預期檔案命中率下降 = 門檻太高；改用 `calibrate_threshold.py --max-drop 0` 的建議 |
| H. Rerank | 定義檔命中 ↑、回答引用預期檔案 ↑、人工判定正確性 ↑；**rerank 耗時平均** | rerank 耗時與首字延遲相比：在 CPU 上多花的秒數值得嗎？ |
| I. 混合 + 分類 + Rerank | 與 C 相比：定義檔命中（主要）↑、程式碼檔命中 ≥ C；識別字題組：定義檔命中維持 3/3；**rerank 耗時平均** | rerank 耗時與首字延遲相比；rerank 是否把唯一的文件名額擠掉（取回片段中文件比例應維持 ≤ 25%） |
| J. D + 提示 v3 | 與 D 相比：**拒答率** ↑（主要：第 10 題；`-oos`：21–25 題）、**誤拒率 = 0**（主要、`-ident`、`-oos` 的 26–28 題）、**混入簡體字的回答 = 0**；取回類指標不變（檢索相同） | 拒答之後又自己補充說明的回答；固定句子是否被完整照抄；有沒有真實問題變成回答「找不到」；主要題組的人工判定正確性不能下降 |

把摘要數據記到 [`docs/metrics.md`](../metrics.md) 第 4 節（每組一列，附報告連結）。沒有量測的數字不要填。

## 決策規則

- 某個開關若能提升定義檔命中或人工判定正確性，且沒有讓任何題型的人工判定正確性下降，就改為預設開啟，並新增 ADR 記錄預設值的改變。
- 若 C 單獨就帶來大部分的改善，混合檢索維持選用（主要幫助直接寫出識別字的問題）。
- 門檻（G）：只能用校準出的值開啟，且沒有任何可回答的題目被拒答。這個值綁定 embedding 模型，換模型就要重新校準。
- Rerank（H）：只有在人工判定正確性提升，**而且**在目標機器上 rerank 耗時相對首字延遲可以接受時，才預設開啟。
- 提示 v3（J）：只有在拒答率提升（至少第 10 題與 21–25 題中的大多數）、每個題組的誤拒率都維持 0，而且主要題組的人工判定正確性沒有下降時，才改為預設。誤拒一題真實問題比多拒答一題陷阱題更嚴重：錯誤的「找不到」會把存在的程式碼藏起來。改預設值時新增 ADR；在那之前不修改 `.env.codespaces`。
