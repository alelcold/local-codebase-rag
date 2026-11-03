# 0016. One-command benchmark on the Mac M2

- **Status**: Accepted
- **Date**: 2026-11-03
- **Related**: [0005](0005-model-selection-and-hardware.md), [0007](0007-multi-environment-testing-strategy.md), [0012](0012-automated-evaluation-metrics.md), [0013](0013-hybrid-retrieval-and-split-retrieval.md), [0015](0015-rerank.md), [experiment plan](../evaluation/experiment-plan-retrieval.md), [metrics](../metrics.md), `scripts/benchmark-mac.sh`, `scripts/benchmark_summary.py`

> English first; 繁體中文版本在下方. Privacy: only the sample project is indexed and evaluated.

## Context

Every Mac M2 32 GB value in `docs/metrics.md` (§2 indexing, §3 latency, §4 evaluation, §4a retrieval switches, §5 model comparison) and in the resume draft is still `{待填}`. Codespaces numbers do not stand in for them (ADR 0007: CPU only, 3B model, `TOP_K=4`).

Measuring by hand takes about twenty commands spread over `docs/metrics.md` "How to measure", the experiment plan and the evaluation README: `ollama run --verbose`, `ollama ps`, two index runs, four `evaluate.py` runs with different switches, `compare.py`. The Codespaces runs showed where this goes wrong:

- a switch left in `.env` or in the shell silently changes a group;
- Ollama's prompt cache makes a later group look faster when it retrieves the same excerpts (devlog 2026-11-03, Problem 1);
- "first query after model load" is only meaningful if the model really was unloaded;
- `ollama ps` with the default context of `ollama run` reports less memory than the backend uses with `LLM_NUM_CTX=16384`.

Time on the target machine is limited, so the run has to be right the first time.

## Decision

Add **`scripts/benchmark-mac.sh`** (bash 3.2, like `setup.sh` and `doctor.sh`) and **`scripts/benchmark_summary.py`** (standard library only). One command runs everything and writes a summary:

1. **Preconditions**: Apple Silicon, `.env` `PROJECT_PATH` is the sample project (otherwise stop: the questions only fit the sample, results are committed, and indexing would replace the collection's project), Docker running, PyYAML (a private venv under `.logs/` if missing).
2. **Ollama**: installed natively (warn if an Ollama container is running), started if needed, `qwen2.5-coder:14b` and the embedding model pulled (`--skip-pull` only checks).
3. **Speed and Metal**: unload the model, `ollama run --verbose` once cold (the short prompt from metrics "How to measure") and once warm with the sample project's `Player.ts` in the prompt (so prompt eval rate is measured on a realistic prompt). `ollama ps` must show `100% GPU`; a CPU-only result stops the run, a CPU/GPU split is a warning.
4. **Indexing**: build, start, `index.sh --full`, then `index.sh` with no changes. Both the indexer's own duration (what metrics §2 records) and the wall-clock time are kept.
5. **Evaluation**, fixed `TOP_K=8`, `LLM_MODEL=qwen2.5-coder:14b`, both question sets, labels `mac-m2-14b-k8-<group>`:
   - `baseline` — plan group A, all switches off;
   - `hybrid-split` — plan group D, `HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1`;
   - `hybrid-split-rerank` — plan group I, only with `--with-rerank`: `RERANK_CANDIDATES=20 RERANK_TOP_N=8`. The image is built with `INSTALL_RERANK=true` and checked before indexing, so a missing dependency fails early.

   Every switch the plan varies is **exported explicitly per group in a subshell** (never written to `.env`), and `/health` must report exactly those settings before a group runs. The model is unloaded before each `evaluate.py` run, so no group reuses another group's cached prompt; the warm-up query reloads it, and the first group's warm-up is recorded as "first query after model load". `ollama ps` and `memory_pressure` are recorded after the first main set, i.e. with the backend's `LLM_NUM_CTX`.
6. **Summary**: `compare.py` for A → D (and D → I), then a Markdown file whose tables have the **same columns as metrics §2, §3, §4, §4a and §5**, English rows and Chinese rows, plus the raw `ollama run` numbers. Manual correctness stays `{待填}`.
7. The backend is put back to the `.env` settings at the end, also when the script stops early.

`--quick` runs 3 questions per set (`1,4,10` and `11,12,13`) and writes everything under `.logs/` so partial numbers never land in `docs/`.

Why D and I, not all plan groups: A–I already ran on Codespaces; on the Mac the question is how the default (A) and the cheapest improvement (D: milliseconds at retrieval, docs share 95% → 25% from split) behave with a 14B model. Rerank (I) is optional because it adds about 1.5 GB to the image and runs on the CPU inside Docker's VM, where torch cannot use Metal either.

Why `20 → 8` for rerank: `RERANK_TOP_N` equals `TOP_K`, so the model gets as many excerpts as in the other groups (as H and I did with 4), and 20 candidates keep the 2.5× ratio of the Codespaces runs (10 → 4).

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Keep the manual steps in metrics.md and the plan | Nothing new to maintain | About twenty commands; the mistakes listed above are easy to make; results not comparable between people | The reason for this change |
| Add a `--suite` mode to `evaluate.py` | One Python entry point | `evaluate.py` only talks HTTP to the backend; it would have to drive Docker and the Ollama CLI too, and its unit tests would grow mocks for both | Mixes concerns |
| Python orchestrator instead of bash | Easier parsing and tests | Still shells out to `ollama`, `docker compose`, `index.sh` for every step; the other operational scripts are bash 3.2 | Same work, less consistent |
| Switch groups by editing `.env` (allowed by the plan) | `.env` shows the state | A failed run leaves `.env` changed; the user's own `.env` gets rewritten | Shell variables are reversible and visible per command |
| Run every plan group (A–I) on the Mac | Complete comparison with Codespaces | E/F need two re-indexes, G has no threshold, H was already shown not to help; about 3× the time | Not worth it for the questions asked |

## Consequences

- **Positive**: The Mac numbers come from one command with the same labels, the same checks and the same table columns as `docs/metrics.md`. Each group's settings are verified, so a leaked switch cannot go unnoticed. Partial (`--quick`) runs cannot be committed by mistake.
- **Negative / trade-offs**:
  - Written without access to a Mac: it was run end to end only against stand-ins for `ollama`, `docker`, `sysctl` and the backend (a fake SSE server). The first real run may still find a difference in `ollama` output.
  - Reading `ollama run --verbose` and `ollama ps` depends on their text format; unknown fields are left `{待填}` instead of failing the run.
  - Unloading the model before each run adds a model load to every warm-up (not scored, but it adds minutes in total). Run time on the Mac: {待填}.
  - The indexer timing includes `docker compose up` checks in the wall-clock column only; the indexer's own duration is what is compared.
- **Follow-ups**: Run it on the Mac M2, paste the tables into `docs/metrics.md`, judge manual correctness, and update the resume draft. If D or I is chosen as a default afterwards, record that in a new ADR.

---

# 0016. Mac M2 一鍵實機測試

- **狀態**：已接受
- **日期**：2026-11-03
- **相關**：[0005](0005-model-selection-and-hardware.md)、[0007](0007-multi-environment-testing-strategy.md)、[0012](0012-automated-evaluation-metrics.md)、[0013](0013-hybrid-retrieval-and-split-retrieval.md)、[0015](0015-rerank.md)、[實驗計畫](../evaluation/experiment-plan-retrieval.md)、[數據紀錄](../metrics.md)、`scripts/benchmark-mac.sh`、`scripts/benchmark_summary.py`

## 背景

`docs/metrics.md` 中所有 Mac M2 32GB 的數值（§2 索引、§3 查詢時間、§4 評估、§4a 檢索開關、§5 模型比較）以及履歷草稿都還是 `{待填}`。Codespaces 的數據不能代替（ADR 0007：只有 CPU、3B 模型、`TOP_K=4`）。

手動量測大約要二十個指令，分散在 `docs/metrics.md` 的「How to measure」、實驗計畫與評估 README：`ollama run --verbose`、`ollama ps`、兩次索引、四次不同開關的 `evaluate.py`、`compare.py`。Codespaces 的實驗已經顯示容易出錯的地方：

- `.env` 或 shell 裡殘留的開關會默默改變某一組；
- 取回相同片段時，Ollama 的提示快取會讓後面的組別看起來比較快（devlog 2026-11-03 問題 1）；
- 「模型載入後的第一次查詢」只有在模型真的被卸載時才有意義；
- `ollama run` 用預設上下文，`ollama ps` 顯示的記憶體會比後端用 `LLM_NUM_CTX=16384` 時少。

能用目標機器的時間有限，所以要第一次就跑對。

## 決策

新增 **`scripts/benchmark-mac.sh`**（bash 3.2，與 `setup.sh`、`doctor.sh` 相同）與 **`scripts/benchmark_summary.py`**（只用標準函式庫）。一個指令跑完全部並輸出摘要：

1. **前置檢查**：Apple Silicon；`.env` 的 `PROJECT_PATH` 是範例專案（否則停止：題目只適用範例專案、結果會提交到 repo，而且索引會取代 collection 中的專案）；Docker 在執行；PyYAML（缺少時在 `.logs/` 下建立專用 venv）。
2. **Ollama**：確認是 macOS 原生安裝（有 Ollama 容器在執行時警告），必要時啟動，拉取 `qwen2.5-coder:14b` 與 embedding 模型（`--skip-pull` 只檢查）。
3. **速度與 Metal**：先卸載模型，`ollama run --verbose` 冷啟動一次（metrics「How to measure」的短提示），暖機後再一次，提示中放入範例專案的 `Player.ts`（讓 prompt eval rate 在接近實際的提示上量測）。`ollama ps` 必須顯示 `100% GPU`；只有 CPU 時停止，CPU/GPU 混合時警告。
4. **索引**：build、啟動，`index.sh --full`，再執行一次沒有變更的 `index.sh`。同時保留索引器自己回報的時間（metrics §2 記錄的值）與牆鐘時間。
5. **評估**：固定 `TOP_K=8`、`LLM_MODEL=qwen2.5-coder:14b`，兩個題組，label 為 `mac-m2-14b-k8-<組別>`：
   - `baseline`：實驗計畫 A 組，全部關閉；
   - `hybrid-split`：實驗計畫 D 組，`HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1`；
   - `hybrid-split-rerank`：實驗計畫 I 組，只在 `--with-rerank` 時執行：`RERANK_CANDIDATES=20 RERANK_TOP_N=8`。映像檔以 `INSTALL_RERANK=true` 建置，並在索引前確認，缺少套件時會提早失敗。

   實驗計畫會變動的每個開關都**在子 shell 中逐組明確 export**（不寫入 `.env`），而且執行前 `/health` 必須回報完全相同的設定。每次執行 `evaluate.py` 前都先卸載模型，讓各組不會重用其他組的提示快取；暖機題會重新載入模型，第一組的暖機題記為「模型載入後的第一次查詢」。`ollama ps` 與 `memory_pressure` 在第一組主要題組之後記錄，也就是後端的 `LLM_NUM_CTX` 下的狀態。
6. **摘要**：`compare.py` 比較 A → D（以及 D → I），再輸出一份 Markdown，表格欄位與 **metrics §2、§3、§4、§4a、§5 相同**，英文列與中文列各一份，另附 `ollama run` 的原始數值。人工判定正確性維持 `{待填}`。
7. 結束時（包含中途停止）把 backend 恢復成 `.env` 的設定。

`--quick` 每個題組只跑 3 題（`1,4,10` 與 `11,12,13`），所有輸出寫到 `.logs/`，不完整的數據不會進入 `docs/`。

為什麼只跑 D、I，而不是全部組別：A～I 已經在 Codespaces 跑過；在 Mac 上要回答的是預設值（A）與成本最低的改善（D：檢索只多幾毫秒，分類取回讓文件比例 95% → 25%）在 14B 模型下的表現。Rerank（I）是選用，因為映像檔多約 1.5 GB，而且是在 Docker VM 的 CPU 上執行，torch 一樣用不到 Metal。

為什麼 rerank 用 `20 → 8`：`RERANK_TOP_N` 等於 `TOP_K`，模型拿到的片段數與其他組相同（H、I 組用 4 也是同樣的考量）；20 個候選維持 Codespaces 實驗的 2.5 倍比例（10 → 4）。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 維持 metrics.md 與實驗計畫中的手動步驟 | 不用維護新東西 | 約二十個指令；上述錯誤很容易發生；不同人跑的結果無法比較 | 這就是要解決的問題 |
| 在 `evaluate.py` 加入 `--suite` 模式 | 單一 Python 入口 | `evaluate.py` 只透過 HTTP 呼叫後端；要它控制 Docker 與 Ollama CLI，單元測試也得 mock 這兩者 | 職責混在一起 |
| 用 Python 而不是 bash 串流程 | 解析與測試較容易 | 每一步仍要呼叫 `ollama`、`docker compose`、`index.sh`；其他維運腳本都是 bash 3.2 | 工作量相同，一致性較差 |
| 以修改 `.env` 切換組別（實驗計畫允許） | `.env` 直接顯示狀態 | 中途失敗會留下改過的 `.env`；會改寫使用者自己的 `.env` | shell 變數可回復，而且每個指令都看得到 |
| 在 Mac 上跑所有組別（A～I） | 可以完整對照 Codespaces | E/F 要重建索引兩次、G 沒有門檻、H 已證實沒有幫助；時間約三倍 | 對要回答的問題不划算 |

## 後果

- **正面**：Mac 的數據由一個指令產生，label、檢查與表格欄位都和 `docs/metrics.md` 一致。每組的設定都經過驗證，殘留的開關不會被忽略。不完整的（`--quick`）結果不會被誤提交。
- **負面／取捨**：
  - 撰寫時沒有 Mac 可用：只用替身（假的 `ollama`、`docker`、`sysctl` 與假 SSE 後端）完整跑過一次。第一次實際執行仍可能遇到 `ollama` 輸出格式的差異。
  - 讀取 `ollama run --verbose` 與 `ollama ps` 依賴它們的文字格式；讀不到的欄位留 `{待填}`，不會讓整個流程失敗。
  - 每次評估前卸載模型，每次暖機都要重新載入模型（不計分，但總時間會多幾分鐘）。Mac 上的總執行時間：{待填}。
  - 牆鐘時間包含 `docker compose up` 的檢查；比較時使用索引器自己回報的時間。
- **後續工作**：在 Mac M2 上執行，把表格貼到 `docs/metrics.md`，完成人工評分，更新履歷草稿。之後若把 D 或 I 設為預設值，另寫一份 ADR。
