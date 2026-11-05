# 0018. Default retrieval settings for Codespaces: split retrieval only

- **Status**: Accepted (changes `.env.codespaces` only; the backend's built-in defaults and `.env.example` for the Mac are unchanged)
- **Date**: 2026-11-05
- **Related**: ADR [0012](0012-automated-evaluation-metrics.md) (metrics), [0013](0013-hybrid-retrieval-and-split-retrieval.md) (hybrid / split retrieval, prompt v2), [0014](0014-similarity-threshold.md) (threshold), [0015](0015-rerank.md) (rerank), [0016](0016-refuse-out-of-scope-questions-in-the-prompt.md) (prompt v3), [0017](0017-one-command-mac-benchmark.md) (Mac benchmark), [experiment plan](../evaluation/experiment-plan-retrieval.md), [devlog 2026-11-03](../devlog/2026-11-03.md), [`metrics.md`](../metrics.md) §4a / §4c, PR #20 (correctness scores)

> English first; 繁體中文版本在下方. Privacy: illustrate only with the sample project.

## Context

ADR 0013–0016 added switches to the backend, all **off** by default, and the [experiment plan](../evaluation/experiment-plan-retrieval.md) measured them on GitHub Codespaces (4 cores, CPU only, `qwen2.5-coder:3b`, `TOP_K=4`) against the baseline. The plan's rule is that no default changes until correctness has been judged. That is now done for groups A–J (PR #20): every answer was judged 0 / 1 / 2 against the sample project's source, blind and side by side; the judging is by AI (Claude), and a person has checked the 5 least certain scores without changing the conclusion. The other scores are still AI-judged.

Evidence, `TOP_K=4`, one run per group. "Main" = `questions.yaml` (10, Chinese, mostly no identifier), "ident." = `questions-identifiers.yaml` (5). Correctness is the AI-judged score (main /20, ident. /10).

| Group | Switches | Defining file retrieved, main / ident. | Code file retrieved, main | Docs among retrieved, main | Keyword hit, main / ident. | First token, main / ident. (s) | Correctness, main / ident. |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | baseline | 0/3 / 1/3 | 1/9 | 95% | 32% / 57% | 13.0 / 21.2 | 5 / 6 |
| B | hybrid | 0/3 / 3/3 | 3/9 | 88% | 38% / 77% | 6.7 / 10.7 ¹ | 9 / 7 ² |
| **C** | **split (`DOC_TOP_K=1`)** | 1/3 / 3/3 | 6/9 | 25% | 28% / 83% | 15.9 / 17.8 | **7 / 10** |
| D | hybrid + split | 0/3 / 3/3 | 6/9 | 25% | 28% / 83% | 17.2 / 19.9 | 7 / 9 |
| F | all on (+ metadata, prompt v2) | 0/3 / 3/3 | 5/9 | 25% | 31% / 88% | 19.6 / 23.8 | 6 / 10 |
| G | threshold | not run: calibration found no usable value | | | | | |
| H | rerank | 0/3 / 2/3 | 2/9 | 85% | 22% / 73% | 21.2 / 27.4 | 6 / 8 |
| I | hybrid + split + rerank | 3/3 / 3/3 | 7/9 | 23% | 45% / 77% | 26.8 / 26.3 | 8 / 9 |
| J | D + prompt v3 | 0/3 / 3/3 | 6/9 | 25% | 18% / 48% | 20.3 / 26.3 | 3 / 5 |

¹ Ollama's prompt cache, not hybrid search (devlog 2026-11-03, Problem 1). ² B's lead on the main set rests on three answers scored 1 that could be 0 (Q1, Q4, Q10); with 0 there B is 6/20, below C.

Totals over both sets (/30): **C 17 = I 17** > B 16 = D 16 = F 16 > H 14 > A 11 > J 8. Out-of-scope set (/16): D 4, J 10 (J refuses all 5 trick questions but also all 3 control questions).

What the evidence shows:

1. **Split retrieval is the switch that moves the numbers**: code files retrieved 1/9 → 6/9, docs 95% → 25%, ident. defining file 1/3 → 3/3, correctness 11 → 17 of 30, and it costs milliseconds of retrieval time.
2. **C did not hurt the doc-heavy questions 2, 3, 6**: A 0 / 2 / 2 → C 0 / 2 / 2. Q2 is 0 in all 8 groups because no group retrieves `ScoreSystem.ts`, a retrieval gap no switch closes.
3. **I (hybrid + split + rerank) has the best retrieval but not the best answers**: defining file 3/3 on the main set, code 7/9, and the same total as C (17). It gains Q1 and Q9 but loses Q3 and Q8, and scores 1 less than C on ident. It costs +4.8 s of rerank, about +10 s of first token against D (26.8 vs 17.2 s), and a 2.15 GB image instead of 616 MB. Better retrieval did not mean better answers: in C and D, Q7 and Q9 stay 0 although an expected code file was retrieved, because the 3B model answers from the wrong file.
4. **The ranking agrees with the automatic metrics where they overlap**: the split family leads, J is last. It disagrees on B (first on main by correctness, weak on retrieval) and on I (best retrieval, no better answers).

## Decision

In `.env.codespaces` (the template copied to `.env` when a codespace has none):

- `SPLIT_RETRIEVAL=true`, `DOC_TOP_K=1` (group C).
- Every other switch stays off: `HYBRID_SEARCH`, `CHUNK_METADATA`, `RERANK`, `SCORE_THRESHOLD`; `PROMPT_VARIANT=v1` (written explicitly).

Not changed:

- **`.env.example` (Mac M2, `qwen2.5-coder:14b`, `TOP_K=8`)** keeps split retrieval off. Nothing was measured there: `DOC_TOP_K=1` with `TOP_K=8` is untested, and the 14B model may use docs differently. It waits for `./scripts/benchmark-mac.sh` (ADR 0017: groups A and D, and I with `--with-rerank`).
- **The backend's built-in defaults** (`SPLIT_RETRIEVAL=false` in `docker-compose.yml` and `config.py`) stay, so a run without a `.env` template is still the baseline and old reports remain comparable.
- **Existing codespaces** keep their `.env` (`post-create.sh` never overwrites it). To apply the setting, add the two lines and run `docker compose up -d backend`; no re-index is needed.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Keep everything off (baseline) | Nothing to explain; old reports stay comparable | Code retrieved 1/9, correctness 11/30; the problem that started the experiments stays | Split retrieval gives the largest gain for no measurable cost, and the check on Q2 / Q3 / Q6 found no loss |
| `HYBRID_SEARCH` (B, or D = B + split) | Ident. defining file 3/3; milliseconds of cost | C alone is already 3/3 on ident.; on the main set it pushed `InputManager.ts` out (D 0/3 vs C 1/3); D scores 16 vs C 17; B's main-set lead is soft (²) | Adds nothing on top of split in this data. Worth re-testing on a larger project where questions contain identifiers (the BM25 channel only indexes ASCII words) |
| `RERANK` (H, or I = D + rerank) | Best retrieval (I: defining 3/3 on both sets, code 7/9) | Same total as C (17), −1 on ident.; +4.8 s rerank, about +10 s first token; 2.15 GB image; gains rest on rerank scores of 0.003–0.07; H alone still leaves the main-set defining file at 0/3 | Cost without a correctness gain. Split + rerank without hybrid (C + rerank) was not measured |
| `CHUNK_METADATA` (in F) | None measured | F: main 6 vs C 7, lost C's hit on Q8; E (metadata alone) was not run, so F also carries prompt v2 | No gain; the switch also forces a full re-index on every change |
| `PROMPT_VARIANT=v2` (in F) | Answers cite `[n] path:lines` (cited 0/9 → 4/9) | 241 vs 89 tokens per answer; Simplified characters still appear (2); no correctness gain | Longer, slower answers without being more correct |
| `PROMPT_VARIANT=v3` (J) | Refuses all 5 trick questions | Refuses 8 of 9 answerable main questions and all 3 control questions; correctness 3/20 | Fails the rule that false refusals stay at 0 (ADR 0016) |
| `SCORE_THRESHOLD` (G) | Would refuse without calling the LLM | Cosine of expected excerpts (median 0.616) and other excerpts (0.604) overlap; 0.70 would drop 25 of 27 correct excerpts | No calibrated value exists; group not run (ADR 0014) |

## Consequences

- **Positive**: a fresh Codespace gets the best measured setting at no extra memory, image size or index time. No re-index is needed to turn it on or off.
- **Negative / trade-offs**: first token on the main set is longer (13.0 → 15.9 s) because code chunks are longer than doc sections; Simplified characters appeared in 3 main answers instead of 1; with only one doc chunk allowed, a question whose answer lives in several doc sections is limited to one.
- **Limits of the evidence** (read the decision with these in mind):
  - **Tiny project**: the sample project has 20 files and 67 chunks (3 of them Markdown). A cap of one doc chunk and "which switch helps" may look different on a project of 50–300 files, which is what this system is for.
  - **One run per group**: the 3B model answers differently every time (C and D have different answer text on all 10 main questions and the same total). A difference of one point is inside that noise, so the rankings among B, C, D, F, I are not settled. The main conclusion (split ≫ baseline, v3 worst) is larger than that noise.
  - **AI-judged correctness**: scores come from Claude, not a person. A person re-checked the 5 least certain scores (conclusion unchanged); the other scores are unconfirmed. Judging was lenient where the main mechanism was right and a secondary key fact missing.
  - **Narrow setup**: Codespaces 4-core CPU, `qwen2.5-coder:3b`, `TOP_K=4`, Chinese questions (10 + 5 + 8). Nothing here transfers automatically to the Mac, 14B or `TOP_K=8`. Latency is affected by Ollama's prompt cache (group B).
- **Follow-ups**:
  - Run `./scripts/benchmark-mac.sh` (ADR 0017) and decide the Mac default separately.
  - Measure split + rerank without hybrid (C + rerank) before ruling rerank out for good.
  - Q2 (combo multiplier) is 0 in every group: the Chinese question contains no identifier, so none of `ScoreSystem.ts`, `gameConfig.ts` or the 計分 doc section is retrieved. Try a Chinese → identifier glossary for the keyword channel.
  - Re-run the groups once more, in alternating order, to estimate run-to-run noise.

---

# 0018. Codespaces 的預設檢索設定：只開分類取回

- **狀態**：已接受（只改 `.env.codespaces`；後端內建預設值與 Mac 用的 `.env.example` 都不變）
- **日期**：2026-11-05
- **相關**：ADR [0012](0012-automated-evaluation-metrics.md)（評估指標）、[0013](0013-hybrid-retrieval-and-split-retrieval.md)（混合檢索／分類取回、提示 v2）、[0014](0014-similarity-threshold.md)（門檻）、[0015](0015-rerank.md)（rerank）、[0016](0016-refuse-out-of-scope-questions-in-the-prompt.md)（提示 v3）、[0017](0017-one-command-mac-benchmark.md)（Mac 實測）、[實驗計畫](../evaluation/experiment-plan-retrieval.md)、[devlog 2026-11-03](../devlog/2026-11-03.md)、[`metrics.md`](../metrics.md) §4a／§4c、PR #20（正確性評分）

## 背景

ADR 0013～0016 在後端加了幾個開關，預設全部**關閉**；[實驗計畫](../evaluation/experiment-plan-retrieval.md)在 GitHub Codespaces（4 核心、只有 CPU、`qwen2.5-coder:3b`、`TOP_K=4`）上與基準線逐項比較。計畫的規則是：評過正確性之前不改預設值。A～J 組現在都評過了（PR #20）：每個回答都對照範例專案原始碼評 0／1／2，盲評並排比較；評分者是 AI（Claude），最不確定的 5 題已由人確認，結論沒有改變。其餘分數仍是 AI 判讀。

證據：`TOP_K=4`，每組跑一次。「主要」= `questions.yaml`（10 題，中文，多半沒有識別字），「識別字」= `questions-identifiers.yaml`（5 題）。正確性是 AI 判讀的分數（主要 /20、識別字 /10）。

| 組別 | 開關 | 定義檔命中，主要／識別字 | 程式碼檔命中，主要 | 取回片段中文件比例，主要 | 關鍵字命中，主要／識別字 | 首字延遲，主要／識別字（秒） | 正確性，主要／識別字 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | 基準線 | 0/3 / 1/3 | 1/9 | 95% | 32% / 57% | 13.0 / 21.2 | 5 / 6 |
| B | 混合檢索 | 0/3 / 3/3 | 3/9 | 88% | 38% / 77% | 6.7 / 10.7 ¹ | 9 / 7 ² |
| **C** | **分類取回（`DOC_TOP_K=1`）** | 1/3 / 3/3 | 6/9 | 25% | 28% / 83% | 15.9 / 17.8 | **7 / 10** |
| D | 混合 + 分類 | 0/3 / 3/3 | 6/9 | 25% | 28% / 83% | 17.2 / 19.9 | 7 / 9 |
| F | 全部開啟（+ metadata、提示 v2） | 0/3 / 3/3 | 5/9 | 25% | 31% / 88% | 19.6 / 23.8 | 6 / 10 |
| G | 門檻 | 未執行：校準找不到可用的值 | | | | | |
| H | rerank | 0/3 / 2/3 | 2/9 | 85% | 22% / 73% | 21.2 / 27.4 | 6 / 8 |
| I | 混合 + 分類 + rerank | 3/3 / 3/3 | 7/9 | 23% | 45% / 77% | 26.8 / 26.3 | 8 / 9 |
| J | D + 提示 v3 | 0/3 / 3/3 | 6/9 | 25% | 18% / 48% | 20.3 / 26.3 | 3 / 5 |

¹ 是 Ollama 的提示詞快取，不是混合檢索（devlog 2026-11-03，問題 1）。² B 在主要題組的領先建立在三題給 1 分、也可能是 0 分的回答（第 1、4、10 題）；這三題改成 0 分，B 只有 6/20，低於 C。

兩個題組合計（/30）：**C 17 = I 17** > B 16 = D 16 = F 16 > H 14 > A 11 > J 8。範圍外題組（/16）：D 4、J 10（J 5 題陷阱題都拒答，但 3 題對照題也全部拒答）。

證據顯示：

1. **真正讓數字動起來的是分類取回**：程式碼檔命中 1/9 → 6/9，文件比例 95% → 25%，識別字題組定義檔 1/3 → 3/3，正確性 11 → 17（/30），而且只多花毫秒級的檢索時間。
2. **C 沒有讓重點在文件的第 2、3、6 題變差**：A 0／2／2 → C 0／2／2。第 2 題 8 組都是 0 分，因為沒有任何一組取回 `ScoreSystem.ts`，這是沒有開關能補上的檢索缺口。
3. **I（混合 + 分類 + rerank）檢索最好，但回答不是最好**：主要題組定義檔 3/3、程式碼 7/9，總分卻和 C 一樣（17）。它多拿第 1、9 題，卻少了第 3、8 題，識別字題組比 C 少 1 分。代價是 rerank 多 4.8 秒、對 D 的首字延遲多約 10 秒（26.8 對 17.2 秒），映像檔 2.15 GB 對 616 MB。檢索變好不等於答得更好：C、D 的第 7、9 題即使取回了預期的程式碼檔仍是 0 分，因為 3B 模型從錯的檔案作答。
4. **排名在能對照的地方與自動指標一致**：分類取回這一族領先，J 墊底。不一致的是 B（正確性在主要題組第一，檢索卻弱）與 I（檢索最好，回答沒有更好）。

## 決策

在 `.env.codespaces`（codespace 沒有 `.env` 時複製成 `.env` 的範本）：

- `SPLIT_RETRIEVAL=true`、`DOC_TOP_K=1`（C 組）。
- 其他開關維持關閉：`HYBRID_SEARCH`、`CHUNK_METADATA`、`RERANK`、`SCORE_THRESHOLD`；`PROMPT_VARIANT=v1`（明確寫出）。

不變的部分：

- **`.env.example`（Mac M2、`qwen2.5-coder:14b`、`TOP_K=8`）** 維持分類取回關閉。那邊還沒有任何量測：`DOC_TOP_K=1` 搭配 `TOP_K=8` 沒有測過，14B 模型使用文件的方式也可能不同。要等 `./scripts/benchmark-mac.sh`（ADR 0017：A、D 組，加上 `--with-rerank` 的 I 組）實測。
- **後端內建預設值**（`docker-compose.yml` 與 `config.py` 的 `SPLIT_RETRIEVAL=false`）不變，所以沒有範本的環境仍是基準線，舊報告仍可比較。
- **既有的 codespace** 保留原本的 `.env`（`post-create.sh` 不會覆蓋）。要套用請自行加入這兩行並執行 `docker compose up -d backend`，不需要重新索引。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 全部維持關閉（基準線） | 不用解釋；舊報告仍可比較 | 程式碼命中 1/9、正確性 11/30；開始做實驗的問題沒有解決 | 分類取回以幾乎零成本帶來最大的改善，第 2、3、6 題的檢查也沒有發現退步 |
| `HYBRID_SEARCH`（B，或 D = B + 分類） | 識別字題組定義檔 3/3；只花毫秒 | 光是 C 在識別字題組就已經 3/3；在主要題組把 `InputManager.ts` 擠掉（D 0/3 對 C 1/3）；D 16 分對 C 17 分；B 在主要題組的領先偏軟（²） | 在分類取回之上沒有帶來任何東西。問題含有識別字的較大專案值得再測（BM25 管道只索引 ASCII 單字） |
| `RERANK`（H，或 I = D + rerank） | 檢索最好（I：兩個題組定義檔 3/3、程式碼 7/9） | 總分和 C 相同（17），識別字題組少 1 分；rerank 多 4.8 秒、首字多約 10 秒；映像檔 2.15 GB；改善建立在 0.003～0.07 的 rerank 分數上；H 單獨使用時，主要題組定義檔仍是 0/3 | 成本高，正確性沒有更好。沒有混合檢索的「分類取回 + rerank」（C + rerank）還沒測 |
| `CHUNK_METADATA`（在 F 組） | 沒有量到好處 | F：主要 6 對 C 7，丟了 C 在第 8 題的命中；E（只開 metadata）沒有執行，所以 F 還帶著提示 v2 | 沒有改善，而且每次切換都會強制全量重建索引 |
| `PROMPT_VARIANT=v2`（在 F 組） | 回答會引用 `[n] 路徑:行號`（引用 0/9 → 4/9） | 每個回答 241 對 89 個 token；仍出現簡體字（2）；正確性沒有提高 | 回答更長更慢，卻沒有更正確 |
| `PROMPT_VARIANT=v3`（J） | 5 題陷阱題全部拒答 | 9 題可回答的主要題目拒答了 8 題，3 題對照題全部拒答；正確性 3/20 | 沒達到誤拒率必須維持 0 的規則（ADR 0016） |
| `SCORE_THRESHOLD`（G） | 不必呼叫 LLM 就能拒答 | 預期片段（中位數 0.616）與其他片段（0.604）的 cosine 分布重疊；0.70 會丟掉 27 段正確片段中的 25 段 | 沒有可校準的值，未執行此組（ADR 0014） |

## 後果

- **正面**：新的 Codespace 直接拿到量測到最好的設定，不增加記憶體、映像檔大小或索引時間；開關切換不需要重新索引。
- **負面／取捨**：主要題組的首字延遲變長（13.0 → 15.9 秒），因為程式碼片段比文件段落長；簡體字出現在 3 個主要題組的回答，基準線是 1 個；文件只允許 1 段，答案分散在好幾個文件段落的問題會被限制。
- **證據的限制**（解讀這個決策時請一併考慮）：
  - **範例專案很小**：只有 20 個檔案、67 個片段（其中 3 個是 Markdown）。「文件只留 1 段」和「哪個開關有效」，在 50～300 個檔案的專案（這個系統的使用情境）上可能不一樣。
  - **每組只跑一次**：3B 模型每次的回答都不同（C 與 D 在 10 題主要題組的回答文字全都不同，總分卻相同）。差 1 分落在這個雜訊範圍內，所以 B、C、D、F、I 之間的名次沒有定論。主要結論（分類取回遠勝基準線、v3 最差）大於這個雜訊。
  - **正確性由 AI 判讀**：分數來自 Claude，不是人。最不確定的 5 題由人複核過（結論沒有改變），其餘分數沒有人確認。主要機制正確、只漏次要關鍵事實時，判得偏寬。
  - **範圍很窄**：Codespaces 4 核心 CPU、`qwen2.5-coder:3b`、`TOP_K=4`、中文問題（10 + 5 + 8 題）。結果不會自動適用於 Mac、14B 或 `TOP_K=8`。延遲受 Ollama 提示詞快取影響（B 組）。
- **後續工作**：
  - 執行 `./scripts/benchmark-mac.sh`（ADR 0017），Mac 的預設值另行決定。
  - 在徹底排除 rerank 之前，先量「分類取回 + rerank」、不含混合檢索（C + rerank）。
  - 第 2 題（連擊倍率）在每一組都是 0 分：中文問題沒有識別字，所以 `ScoreSystem.ts`、`gameConfig.ts`、文件的計分段落都沒被取回。可以試試給關鍵字管道的中文 → 識別字詞彙表。
  - 各組再以交替順序重跑一次，估計每次執行之間的雜訊。
