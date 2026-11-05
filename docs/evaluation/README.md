# Evaluation

> English first; 繁體中文版本在下方.
> Privacy: only the sample project (`examples/sample-game-frontend/`) may be evaluated into this folder.

| File | Contents |
| --- | --- |
| [`questions.md`](questions.md) | The 10 questions for people: expected answers, citations, manual score sheet |
| [`questions.yaml`](questions.yaml) | The same questions for the script: type, keywords, expected files, defining files |
| [`questions-identifiers.yaml`](questions-identifiers.yaml) | 5 supplementary questions (ids 11–15) that name a code identifier, for hybrid retrieval (ADR 0013) |
| [`questions-out-of-scope.yaml`](questions-out-of-scope.yaml) | 8 supplementary questions (ids 21–28): 5 trick questions about features the sample project does not have, and 3 control questions about features that exist but are easy to mistake for missing (ADR 0016) |
| [`experiment-plan-retrieval.md`](experiment-plan-retrieval.md) | Runs, commands and expected metrics for the retrieval switches of ADR 0013–0015 (groups A–I) |
| [`../../scripts/calibrate_threshold.py`](../../scripts/calibrate_threshold.py) | Suggests `SCORE_THRESHOLD` from the results in `results/` (ADR 0014) |
| `results/` | Output of `scripts/evaluate.py`: `<date>-<label>.json` and `.md` |

Design and limits of the metrics: [ADR 0012](../decisions/0012-automated-evaluation-metrics.md). **A keyword hit is not a correct answer**; every report has a 「人工判定正確性」 column for a person to fill in.

## Run

The stack must be running with the sample project indexed (`./scripts/doctor.sh` passes). In a codespace PyYAML is already installed; elsewhere:

```bash
pip install -r scripts/requirements-eval.txt
```

```bash
python3 scripts/evaluate.py --label codespace-3b-k4
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--base-url` | `http://localhost:8080/api` | The frontend's `/api` (same path as the browser) or the backend directly, `http://localhost:8000` |
| `--top-k` | server's `TOP_K` | Excerpts per question |
| `--label` | (required) | Run name in the file name, e.g. `codespace-3b`, `mac-14b` |
| `--only` | all | Question ids, e.g. `1,9` or `2-4` |
| `--lang` | `zh` | `en` asks the English wording |
| `--no-warmup` | warm-up on | Without the unscored warm-up query, question 1 includes model load |
| `--out-dir` | `docs/evaluation/results` | Use a folder outside the repo for anything but the sample project |
| `--timeout` | `900` | Seconds per question |
| `--project` | the question file's `project:` | The indexed project, for checking files and symbols named in answers (疑似編造) |

On CPU with 3B, 10 questions take about 5–10 minutes (estimate from the single queries measured so far).

## Judge, then compare

1. Open the `.md` report, read each answer and fill in 「人工判定正確性」 (0 = wrong or invented, 1 = partly right, 2 = all key facts right), using the key facts listed under each answer.
2. Copy the scores into the JSON:

   ```bash
   python3 scripts/evaluate.py --apply-manual docs/evaluation/results/2026-11-03-codespace-3b-k4.md
   ```

3. Compare two runs (Δ = B − A):

   ```bash
   python3 scripts/compare.py docs/evaluation/results/2026-11-03-codespace-3b-k4.json docs/evaluation/results/2026-11-03-codespace-3b-k8.json
   ```

4. Copy the summary numbers into [`../metrics.md`](../metrics.md), sections 3–4, with a link to the report.

When the scoring rules change, re-score existing reports instead of re-running the model. This recomputes the automatic metrics from the stored answers and sources, keeps timing, manual scores, the Notes column and any note above the generated header, and prints what changed in each summary. Then re-run `compare.py` for the affected comparisons:

```bash
python3 scripts/evaluate.py --rescore docs/evaluation/results/*.json
```

## Reading the numbers

- **Code / Doc / Def.**: expected code files, documentation files, and (for 定位設定) the file that defines the setting, found among the **retrieved** sources. Low code hits with high doc share means docs crowd out code.
- **Keywords**: key identifiers and values found in the answer. Screening only.
- **Simplified**: Simplified-only characters in the answer (e.g. 体, 来, 说).
- **Refused** / **Refusal rate** (trick questions, e.g. question 10): the answer says it cannot find the feature (a refusal keyword, in Traditional **or Simplified** form) and shows no sign of invented code: none of the forbidden words (`WebSocket` etc.) and no file or symbol that is missing from the project (see *Suspected fabrication*). A refusal that names a forbidden word or a missing file is shown as "not refused: refusal phrase, but suspected fabrication"; read it.
- **Traditional / Simplified refusal phrases** (`REFUSAL_TRAD_SIMP` in `evaluate.py`, 繁簡對照清單): every Chinese refusal phrase with its Simplified forms, e.g. 無法 → 无法, 沒有找到 → 没有找到 (不存在 is the same in both). Matching always tries both. When you add a Chinese refusal keyword to a question file, add it to this list too; a unit test fails otherwise (ADR 0019).
- **Suspected fabrication** / 疑似編造 (every answer): the answer names a file (`src/game/Player.ts`) or a code-shaped symbol (`checkCollisions()`, `invincibilityTime`, `PLANET_SPAWN_RATE`) that exists nowhere in the indexed project (the question file's `project:`, or `--project`), or a forbidden word. A screen for a person to confirm, not a verdict: it misses invented behaviour built from real names (e.g. "`syncUi` syncs saves to the cloud"), and a real getter called by another name (`getMultiplier` for `get multiplier()`) is flagged.
- **Falsely refused** / **False refusal rate** (every answerable question): the answer contains a "not found" phrase (`REFUSAL_PHRASES` in `evaluate.py`, e.g. 找不到, 不存在, not found) **and** hits none of the question's keywords. A bare 沒有 does not count: it is common in correct answers. Read the flagged answers; it is a screen, like the keywords (ADR 0016).
- Do not repeat the same question right after itself to measure latency: Ollama's prompt cache makes the second time look much faster.

---

# 評估

> 隱私：只有範例專案（`examples/sample-game-frontend/`）的評估結果可以放在這個資料夾。

| 檔案 | 內容 |
| --- | --- |
| [`questions.md`](questions.md) | 給人看的 10 題：預期答案、引用、人工計分表 |
| [`questions.yaml`](questions.yaml) | 給腳本用的同一組題目：題型、關鍵字、預期檔案、定義檔 |
| [`questions-identifiers.yaml`](questions-identifiers.yaml) | 5 題補充題組（11–15 題），題目直接寫出程式碼識別字，用來評估混合檢索（ADR 0013） |
| [`questions-out-of-scope.yaml`](questions-out-of-scope.yaml) | 8 題補充題組（21–28 題）：5 題範例專案中不存在的功能（陷阱題），3 題存在但容易被誤判為不存在的功能（對照題）（ADR 0016） |
| [`experiment-plan-retrieval.md`](experiment-plan-retrieval.md) | ADR 0013–0015 檢索開關的實驗組合、指令與預期指標（A～I 組） |
| [`../../scripts/calibrate_threshold.py`](../../scripts/calibrate_threshold.py) | 從 `results/` 的結果建議 `SCORE_THRESHOLD`（ADR 0014） |
| `results/` | `scripts/evaluate.py` 的輸出：`<日期>-<label>.json` 與 `.md` |

指標的設計與限制見 [ADR 0012](../decisions/0012-automated-evaluation-metrics.md)。**關鍵字命中不等於回答正確**；每份報告都有「人工判定正確性」欄位，要由人填寫。

## 執行

服務必須已啟動，並已為範例專案建立索引（`./scripts/doctor.sh` 全部通過）。codespace 裡已經裝好 PyYAML；其他環境請先安裝：

```bash
pip install -r scripts/requirements-eval.txt
```

```bash
python3 scripts/evaluate.py --label codespace-3b-k4
```

| 參數 | 預設值 | 說明 |
| --- | --- | --- |
| `--base-url` | `http://localhost:8080/api` | 前端的 `/api`（和瀏覽器相同的路徑），或直接連後端 `http://localhost:8000` |
| `--top-k` | 伺服器的 `TOP_K` | 每題取回的片段數 |
| `--label` | （必填） | 檔名中的執行名稱，例如 `codespace-3b`、`mac-14b` |
| `--only` | 全部 | 題號，例如 `1,9` 或 `2-4` |
| `--lang` | `zh` | `en` 改用英文題目 |
| `--no-warmup` | 預設會暖機 | 不送不計分的暖機問題時，第 1 題會包含載入模型的時間 |
| `--out-dir` | `docs/evaluation/results` | 範例專案以外的結果，請寫到 repo 以外的資料夾 |
| `--timeout` | `900` | 每題的秒數上限 |
| `--project` | 題目檔的 `project:` | 索引的專案，用來檢查回答中提到的檔案與符號（疑似編造） |

在 CPU 上用 3B 模型，10 題大約需要 5～10 分鐘（依目前量到的單次查詢推估）。

## 先判定，再比較

1. 打開 `.md` 報告，讀每題的回答，對照下方列出的關鍵事實，填寫「人工判定正確性」（0 = 錯誤或編造、1 = 部分正確、2 = 關鍵事實全對）。
2. 把分數寫回 JSON：

   ```bash
   python3 scripts/evaluate.py --apply-manual docs/evaluation/results/2026-11-03-codespace-3b-k4.md
   ```

3. 比較兩次結果（Δ = B − A）：

   ```bash
   python3 scripts/compare.py docs/evaluation/results/2026-11-03-codespace-3b-k4.json docs/evaluation/results/2026-11-03-codespace-3b-k8.json
   ```

4. 把摘要數字抄到 [`../metrics.md`](../metrics.md) 第 3～4 節，並附上報告連結。

計分規則改變時，不必重跑模型，重新計分既有報告即可。它會用報告中保存的回答與來源重新計算自動指標，保留延遲、人工分數、Notes 欄與產生的標頭上方的說明，並印出每份摘要的變化。之後再對受影響的比較重跑 `compare.py`：

```bash
python3 scripts/evaluate.py --rescore docs/evaluation/results/*.json
```

## 怎麼解讀

- **Code／Doc／Def.**：在**取回**的來源中，找到的預期程式碼檔、文件檔，以及（定位設定題）定義該設定的檔案。程式碼命中低、文件比例高，代表文件把程式碼擠掉了。
- **Keywords**：回答中出現的關鍵識別字與數值，只用來初步篩選。
- **Simplified**：回答中只存在於簡體的字。
- **Refused**／**拒答率**（陷阱題，例如第 10 題）：回答說找不到該功能（命中拒答關鍵字，繁體**或簡體**皆可），而且沒有編造的跡象：沒有任何禁用字（`WebSocket` 等），也沒有提到專案中不存在的檔案或符號（見「疑似編造」）。拒答卻提到禁用字或不存在的檔案時，會顯示「not refused: refusal phrase, but suspected fabrication」，請人工讀過。
- **繁簡對照清單**（`evaluate.py` 的 `REFUSAL_TRAD_SIMP`）：每個中文拒答字句與它的簡體寫法，例如無法 → 无法、沒有找到 → 没有找到（不存在繁簡相同）。比對時兩種都會試。在題目檔新增中文拒答關鍵字時，也要加進這份清單，否則單元測試會失敗（ADR 0019）。
- **Suspected fabrication**／**疑似編造**（所有回答）：回答提到索引的專案（題目檔的 `project:`，或 `--project`）中完全不存在的檔案（`src/game/Player.ts`）或程式碼形式的符號（`checkCollisions()`、`invincibilityTime`、`PLANET_SPAWN_RATE`），或提到禁用字。這是給人確認的篩選，不是判決：用真實名稱編出不存在的行為（例如「`syncUi` 會把存檔同步到雲端」）抓不到；真實的 getter 換個名字（`get multiplier()` 寫成 `getMultiplier`）會被標記。
- **Falsely refused**／**誤拒率**（所有可回答的題目）：回答含有「找不到」類的字句（`evaluate.py` 的 `REFUSAL_PHRASES`，例如找不到、不存在、not found），**而且**沒有命中任何關鍵字。單獨的「沒有」不算：正確的回答也常出現。被標記的回答要人工讀過；它和關鍵字一樣只是初步篩選（ADR 0016）。
- 量延遲時，不要緊接著重複問同一題：Ollama 的提示詞快取會讓第二次看起來快很多。
