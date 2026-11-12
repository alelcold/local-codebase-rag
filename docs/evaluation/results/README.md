# Evaluation results

> English first; 繁體中文版本在下方.

Raw output of `scripts/evaluate.py` (`.json` + `.md` per run) and of `scripts/compare.py` (`<A>-vs-<B>.md`). Every run here is on the sample project, in GitHub Codespaces (4 CPU cores), with `qwen2.5-coder:3b`. The summary tables and the reasoning are in [`docs/metrics.md` §4](../../metrics.md) and [ADR 0018](../../decisions/0018-codespaces-default-retrieval-settings.md); this page only maps files to experiments.

## Where to start

| If you want… | Read |
| --- | --- |
| The decision that came out of the experiments | [ADR 0018](../../decisions/0018-codespaces-default-retrieval-settings.md) |
| The adopted change against the baseline | [`2026-11-03-baseline-vs-split.md`](2026-11-03-baseline-vs-split.md) |
| Why no similarity threshold | [`2026-11-03-threshold-calibration.md`](2026-11-03-threshold-calibration.md) |
| Why rerank stays off | [`2026-11-03-hybrid-split-vs-hybrid-split-rerank.md`](2026-11-03-hybrid-split-vs-hybrid-split-rerank.md) |
| Why prompt v3 was rejected | [`2026-11-03-hybrid-split-vs-hybrid-split-v3-oos.md`](2026-11-03-hybrid-split-vs-hybrid-split-v3-oos.md) |

## File naming

`2026-11-03-codespace-3b-k4-<group>[-<set>].{json,md}`

| `<set>` suffix | Question set |
| --- | --- |
| (none) | Main set, 10 questions ([`questions.yaml`](../questions.yaml)) |
| `-ident` | 5 questions that name an identifier ([`questions-identifiers.yaml`](../questions-identifiers.yaml)) |
| `-oos` | 8 out-of-scope questions ([`questions-out-of-scope.yaml`](../questions-out-of-scope.yaml)) |

| `<group>` | Experiment group ([plan](../experiment-plan-retrieval.md)) | Adopted? |
| --- | --- | --- |
| `baseline` | A. all switches off | Reference |
| `hybrid` | B. `HYBRID_SEARCH` | No |
| `split` | C. `SPLIT_RETRIEVAL`, `DOC_TOP_K=1` | **Yes** (`.env.codespaces`) |
| `hybrid-split` | D. B + C | No |
| `all` | F. D + `CHUNK_METADATA` + prompt v2 | No |
| `rerank` | H. `RERANK` | No |
| `hybrid-split-rerank` | I. D + `RERANK` | No |
| `hybrid-split-v3` | J. D + prompt v3 | No |

Group G (similarity threshold) was not run: calibration found no safe value. Group K (`QUERY_GLOSSARY`) has not been run yet. The two `2026-11-02-codespace-3b-k{4,8}` runs are the first warm-up evaluation, comparing `TOP_K=4` and `TOP_K=8` before the retrieval switches existed.

---

# 評估結果

`scripts/evaluate.py` 的原始輸出（每次執行一份 `.json` 與 `.md`），以及 `scripts/compare.py` 的比較報告（`<A>-vs-<B>.md`）。這裡的每一次執行都是在 GitHub Codespaces（4 核心 CPU）上，用 `qwen2.5-coder:3b` 評估範例專案。整理過的數據表與判斷理由在 [`docs/metrics.md` §4](../../metrics.md) 與 [ADR 0018](../../decisions/0018-codespaces-default-retrieval-settings.md)；本頁只說明檔案對應哪個實驗。

## 從哪裡開始看

| 想知道… | 請看 |
| --- | --- |
| 實驗得出的決定 | [ADR 0018](../../decisions/0018-codespaces-default-retrieval-settings.md) |
| 採用的改動與基準線的比較 | [`2026-11-03-baseline-vs-split.md`](2026-11-03-baseline-vs-split.md) |
| 為什麼不設相似度門檻 | [`2026-11-03-threshold-calibration.md`](2026-11-03-threshold-calibration.md) |
| 為什麼不開 Rerank | [`2026-11-03-hybrid-split-vs-hybrid-split-rerank.md`](2026-11-03-hybrid-split-vs-hybrid-split-rerank.md) |
| 為什麼不採用提示 v3 | [`2026-11-03-hybrid-split-vs-hybrid-split-v3-oos.md`](2026-11-03-hybrid-split-vs-hybrid-split-v3-oos.md) |

## 檔名規則

`2026-11-03-codespace-3b-k4-<組別>[-<題組>].{json,md}`

| `<題組>` 後綴 | 題組 |
| --- | --- |
| （無） | 主要題組，10 題（[`questions.yaml`](../questions.yaml)） |
| `-ident` | 5 題含識別字的題目（[`questions-identifiers.yaml`](../questions-identifiers.yaml)） |
| `-oos` | 8 題範圍外題目（[`questions-out-of-scope.yaml`](../questions-out-of-scope.yaml)） |

| `<組別>` | 實驗組（[實驗計畫](../experiment-plan-retrieval.md)） | 是否採用 |
| --- | --- | --- |
| `baseline` | A. 所有開關關閉 | 基準 |
| `hybrid` | B. `HYBRID_SEARCH` | 否 |
| `split` | C. `SPLIT_RETRIEVAL`、`DOC_TOP_K=1` | **是**（`.env.codespaces`） |
| `hybrid-split` | D. B + C | 否 |
| `all` | F. D + `CHUNK_METADATA` + 提示 v2 | 否 |
| `rerank` | H. `RERANK` | 否 |
| `hybrid-split-rerank` | I. D + `RERANK` | 否 |
| `hybrid-split-v3` | J. D + 提示 v3 | 否 |

G 組（相似度門檻）沒有執行：校準後找不到安全的值。K 組（`QUERY_GLOSSARY`）尚未執行。兩份 `2026-11-02-codespace-3b-k{4,8}` 是第一次的暖機評估，在檢索開關出現之前比較 `TOP_K=4` 與 `TOP_K=8`。
