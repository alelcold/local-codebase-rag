# Devlog 2026-11-01 — Codespaces setup: pitfalls and timeouts

> English first; 繁體中文版本在下方.
> Privacy: only the sample project (`examples/sample-game-frontend/`) was indexed and queried.
> This entry adds the detailed test log for the Codespaces run. The first problem of that day (containers could not reach Ollama) is in [2026-11-01.md](2026-11-01.md).
> {待補：測試紀錄中其餘的踩坑項目（本篇只收錄已整理的部分；編號沿用測試紀錄，#8 為查詢逾時）}

## What I did

- Set up the stack in **GitHub Codespaces** (Linux, CPU only): Ollama installed natively and started with `OLLAMA_HOST=0.0.0.0`, models `qwen2.5-coder:3b` + `nomic-embed-text`, then Qdrant, backend and frontend with Docker Compose.
- Indexed the sample project and queried it from the UI.
- Debugged the startup and networking steps by hand with `curl`, background processes and log files, then a query timeout (504).
- Follow-up in the same PR: configurable timeouts (ADR [0009](../decisions/0009-timeout-settings.md)), GitHub Actions CI with an end-to-end smoke test (ADR [0008](../decisions/0008-ci-design.md)), and a testing strategy across environments (ADR [0007](../decisions/0007-multi-environment-testing-strategy.md)).

## Problems

### Problem 1: The terminal looked frozen after starting a server

- **Problem**: After starting a long-running server (`ollama serve`) the terminal printed nothing more and did not return to the prompt. It looked like the command had hung.
- **Error message**: none. The server was running normally.
- **Cause**: A server runs until it is stopped. Run in the foreground, it keeps the terminal busy. The command was missing `&`.
- **Fix**: Run it in the background and send the output to a log file:

  ```bash
  OLLAMA_HOST=0.0.0.0 nohup ollama serve > ollama.log 2>&1 &
  ```

  Rule of thumb: anything that keeps running (servers, watchers) goes in the background with its output in a log.

### Problem 2: The second run overwrote the log, and the `Listening` line was gone

- **Problem**: After starting the server a second time, `grep Listening ollama.log` found nothing, although the first start had worked.
- **Error message**: {待補：第二次啟動時 log 裡的內容}
- **Cause**: `>` truncates the file. The second start replaced the log of the first, successful start. {待補：第二次啟動是否因為連接埠已被第一個程序佔用而失敗}
- **Fix**: Check whether the server is already running before starting it again, and keep old logs:

  ```bash
  ss -ltnp | grep 11434
  ```

  ```bash
  OLLAMA_HOST=0.0.0.0 nohup ollama serve >> ollama.log 2>&1 &
  ```

### Problem 3: `curl -s` hid the error

- **Problem**: A `curl -s` health check printed nothing, so it was impossible to tell whether the connection was refused, timed out, or the response was empty.
- **Error message**: none. That was the problem.
- **Cause**: `-s` (silent) hides the progress bar **and** error messages.
- **Fix**: Use `-sS` (`--show-error`): quiet, but errors are still printed. Add `-w '%{http_code}\n'` to see the status code.

  ```bash
  curl -sS http://localhost:11434/api/version
  ```

  `scripts/smoke-test.sh` and the CI workflow use `-sS` everywhere.

### Problem 4: Checking the network from the container's point of view

- **Problem**: `curl localhost:11434` worked in the codespace terminal, but that says nothing about whether a **container** can reach Ollama. See Problem 1 in [2026-11-01.md](2026-11-01.md).
- **Cause**: Inside a container, `localhost` is the container itself. The path a container takes (bridge gateway → host) is different from the host's loopback.
- **Fix**: Test from a throw-away container. This is the most direct way to check container networking:

  ```bash
  docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl -sS http://host.docker.internal:11434/api/version
  ```

  The same check runs in CI, from inside the backend container (`docker compose exec backend python -c ...`).

### Problem 5 (#8 in the test log): Queries returned 504 on CPU

- **Problem**: Queries from the UI failed with **504** in Codespaces (CPU, `qwen2.5-coder:3b`). A single query was estimated to take **1.5–2 minutes**.
- **Error message**:

  ```text
  {待補：介面顯示的錯誤，例如「查詢失敗：504 Gateway Timeout」}
  ```

- **Cause**: Several hops each have their own timeout: browser → Codespaces port forwarding → nginx → backend → Ollama. When the fix was written, nginx in `main` was already set to 900 s and the backend's LLM timeout to 600 s, so a 504 after about 1.5–2 minutes most likely came from the Codespaces port forwarder in front of nginx. {待補：確認來源，例如在 codespace 內直接 `curl -sS localhost:8000/query` 是否成功}. The investigation also found two gaps: the embedding call had **no timeout at all**, and the UI gave no sign of progress during a long wait.
- **Fix** (ADR [0009](../decisions/0009-timeout-settings.md)):
  - nginx `proxy_read_timeout` / `proxy_send_timeout` come from `PROXY_READ_TIMEOUT` / `PROXY_SEND_TIMEOUT` (default 300 s).
  - The backend's Ollama timeouts are `LLM_REQUEST_TIMEOUT` and the new `EMBED_REQUEST_TIMEOUT` (default 300 s). A timeout now returns **504** with the stage and the setting name, instead of a generic 502.
  - The UI shows "生成中" with the seconds elapsed. On failure it explains whether the backend, a proxy, or the connection gave up, and lists likely causes.
  - If the port forwarder has a fixed limit, only short requests avoid it: an asynchronous query job (or streaming) is a follow-up in ADR 0009.

## Concepts learned

- **A request is only as patient as its least patient hop.** Each proxy has its own timeout. Raising one value does nothing if a hop in front of it gives up first. See [knowledge checklist §11](../learning/knowledge-checklist.md#11-timeouts-across-a-proxy-chain).
- **Foreground vs. background processes, and `>` vs. `>>`.** See [§12](../learning/knowledge-checklist.md#12-debugging-long-running-services-from-the-shell).
- **`curl -sS`** is the right default for scripts: quiet, but errors still show.
- **Test from where the caller is.** A throw-away `curlimages/curl` container sees the network the way the backend container does.
- **Small models for pipeline checks, large models for quality.** This is now the CI design: the smoke test uses `qwen2.5-coder:0.5b` (ADR 0008). See [§13](../learning/knowledge-checklist.md#13-cicd-and-github-actions).
- {待補：測試紀錄「學到的概念」中的其他項目}

## Data

| Metric | Value | Environment / notes |
| --- | --- | --- |
| Codespaces machine type | {待填} | |
| Query time (3B, top_k=8) | ≈ 1.5–2 min (estimated) | Codespaces, CPU only. Estimated from the test run, not measured over 10 queries |
| Full index of sample project (20 files, 67 chunks) | {待填} s | CPU-only embeddings |
| Model pull time | {待填} | |
| Backend unit tests after the timeout fix | 56 passed | Python 3.13, Ollama/Qdrant faked |

Copied into `docs/metrics.md`.

## Screenshots

- {待補} The UI showing "生成中" with the elapsed time on Codespaces.
- {待補} The timeout message after a 504.

## Next

- [ ] Confirm where the 504 came from (direct `curl` to the backend inside the codespace).
- [ ] Measure the query time over 10 queries with the new UI timer and record it in `docs/metrics.md`.
- [ ] If the port forwarder is the limit, implement the asynchronous query job (ADR 0009).
- [ ] Record the CI job durations after the first run.

---

# 開發日誌 2026-11-01 — Codespaces 環境建置：踩坑與逾時

> 隱私：只索引並查詢範例專案（`examples/sample-game-frontend/`）。
> 本篇補上 Codespaces 測試的詳細紀錄。當天第一個問題（容器連不到 Ollama）記錄在 [2026-11-01.md](2026-11-01.md)。
> {待補：測試紀錄中其餘的踩坑項目（本篇只收錄已整理的部分；編號沿用測試紀錄，#8 為查詢逾時）}

## 做了什麼

- 在 **GitHub Codespaces**（Linux、只有 CPU）建置環境：Ollama 原生安裝並以 `OLLAMA_HOST=0.0.0.0` 啟動，模型使用 `qwen2.5-coder:3b` + `nomic-embed-text`，再用 Docker Compose 啟動 Qdrant、後端與前端。
- 索引範例專案，並從介面提問。
- 用 `curl`、背景程序與 log 檔手動排查啟動與網路問題，之後又處理了查詢逾時（504）。
- 在同一個 PR 中接著完成：可設定的逾時（ADR [0009](../decisions/0009-timeout-settings.md)）、含端到端冒煙測試的 GitHub Actions CI（ADR [0008](../decisions/0008-ci-design.md)），以及跨環境的測試策略（ADR [0007](../decisions/0007-multi-environment-testing-strategy.md)）。

## 遇到的問題

### 問題 1：啟動伺服器後，終端機看起來卡住

- **問題**：啟動常駐的伺服器（`ollama serve`）之後，終端機不再輸出任何東西，也沒有回到提示字元，看起來像是指令卡住了。
- **錯誤訊息**：沒有。伺服器其實正常在跑。
- **原因**：伺服器會一直執行到被停止為止。在前景執行時，它會一直佔住終端機。指令少了 `&`。
- **解法**：放到背景執行，並把輸出導到 log 檔：

  ```bash
  OLLAMA_HOST=0.0.0.0 nohup ollama serve > ollama.log 2>&1 &
  ```

  原則：會一直執行的東西（伺服器、watcher）都放背景，輸出寫進 log。

### 問題 2：第二次執行把 log 蓋掉，找不到 `Listening` 紀錄

- **問題**：第二次啟動伺服器後，`grep Listening ollama.log` 什麼都找不到，但第一次啟動明明是成功的。
- **錯誤訊息**：{待補：第二次啟動時 log 裡的內容}
- **原因**：`>` 會先清空檔案。第二次啟動把第一次成功啟動的 log 蓋掉了。{待補：第二次啟動是否因為連接埠已被第一個程序佔用而失敗}
- **解法**：重新啟動前，先確認伺服器是不是已經在跑，並保留舊的 log：

  ```bash
  ss -ltnp | grep 11434
  ```

  ```bash
  OLLAMA_HOST=0.0.0.0 nohup ollama serve >> ollama.log 2>&1 &
  ```

### 問題 3：`curl -s` 把錯誤訊息藏起來了

- **問題**：用 `curl -s` 做健康檢查時什麼都沒印出來，無法判斷是連線被拒絕、逾時，還是回應本來就是空的。
- **錯誤訊息**：沒有，問題就出在這裡。
- **原因**：`-s`（silent）除了關掉進度條，也會**一起**關掉錯誤訊息。
- **解法**：改用 `-sS`（`--show-error`）：保持安靜，但錯誤照樣會印出來。需要看狀態碼時，再加上 `-w '%{http_code}\n'`。

  ```bash
  curl -sS http://localhost:11434/api/version
  ```

  `scripts/smoke-test.sh` 與 CI workflow 一律使用 `-sS`。

### 問題 4：從容器的角度檢查網路

- **問題**：在 codespace 的終端機裡 `curl localhost:11434` 是通的，但這不代表**容器**連得到 Ollama。見 [2026-11-01.md](2026-11-01.md) 的問題 1。
- **原因**：在容器裡，`localhost` 指的是容器自己。容器連到主機走的路徑（bridge gateway → 主機），和主機自己的 loopback 不一樣。
- **解法**：開一個用完即丟的容器來測試，這是驗證容器網路最直接的方法：

  ```bash
  docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl -sS http://host.docker.internal:11434/api/version
  ```

  CI 裡也有同樣的檢查，是從後端容器內部執行的（`docker compose exec backend python -c ...`）。

### 問題 5（測試紀錄 #8）：只有 CPU 時查詢回傳 504

- **問題**：在 Codespaces（CPU、`qwen2.5-coder:3b`）從介面查詢時出現 **504**。推算單次查詢需要 **1.5～2 分鐘**。
- **錯誤訊息**：

  ```text
  {待補：介面顯示的錯誤，例如「查詢失敗：504 Gateway Timeout」}
  ```

- **原因**：一次查詢會經過好幾段連線，每一段都有自己的逾時：瀏覽器 → Codespaces 連接埠轉發 → nginx → 後端 → Ollama。修正時，`main` 上的 nginx 已經設成 900 秒、後端的 LLM 逾時是 600 秒，所以約 1.5～2 分鐘就出現的 504，最可能來自 nginx 前面的 Codespaces 連接埠轉發。{待補：確認來源，例如在 codespace 內直接 `curl -sS localhost:8000/query` 是否成功}。追查時還發現兩個缺口：embedding 呼叫**完全沒有逾時**，而且等待很久時介面沒有任何進度提示。
- **解法**（ADR [0009](../decisions/0009-timeout-settings.md)）：
  - nginx 的 `proxy_read_timeout`／`proxy_send_timeout` 改由 `PROXY_READ_TIMEOUT`／`PROXY_SEND_TIMEOUT` 設定（預設 300 秒）。
  - 後端呼叫 Ollama 的逾時改為 `LLM_REQUEST_TIMEOUT` 與新增的 `EMBED_REQUEST_TIMEOUT`（預設 300 秒）。逾時時回傳 **504**，並寫出是哪個階段、要調整哪個設定，不再是籠統的 502。
  - 介面顯示「生成中」與已等待秒數。失敗時會說明是後端、代理還是連線先放棄，並列出可能原因。
  - 如果連接埠轉發有固定的時間上限，只有把請求變短才能避開：非同步查詢工作（或串流）列為 ADR 0009 的後續工作。

## 學到的概念

- **一個請求能等多久，取決於最沒耐心的那一段連線**。每個代理都有自己的逾時；如果前面的連線段先放棄，調高後面的值也沒用。見[知識檢核清單 §11](../learning/knowledge-checklist.md#11-timeouts-across-a-proxy-chain)。
- **前景與背景程序、`>` 與 `>>` 的差別**。見 [§12](../learning/knowledge-checklist.md#12-debugging-long-running-services-from-the-shell)。
- **`curl -sS`** 是寫腳本時的正確預設：安靜，但錯誤照樣顯示。
- **從呼叫端的位置測試**：用完即丟的 `curlimages/curl` 容器看到的網路，和後端容器看到的一樣。
- **用小模型驗證流程，用大模型評估品質**：這成了 CI 的設計，冒煙測試使用 `qwen2.5-coder:0.5b`（ADR 0008）。見 [§13](../learning/knowledge-checklist.md#13-cicd-and-github-actions)。
- {待補：測試紀錄「學到的概念」中的其他項目}

## 數據

| 指標 | 數值 | 環境／備註 |
| --- | --- | --- |
| Codespaces 機型 | {待填} | |
| 查詢時間（3B，top_k=8） | 約 1.5～2 分鐘（推算） | Codespaces，只有 CPU。由測試過程推算，不是 10 次查詢的平均 |
| 範例專案完整索引（20 個檔案、67 個片段） | {待填} 秒 | 以 CPU 產生 embedding |
| 模型下載時間 | {待填} | |
| 修正逾時後的後端單元測試 | 56 個通過 | Python 3.13，Ollama／Qdrant 以假物件取代 |

已同步到 `docs/metrics.md`。

## 截圖

- {待補} Codespaces 上顯示「生成中」與已等待秒數的介面。
- {待補} 504 之後顯示的逾時說明。

## 下一步

- [ ] 確認 504 的來源（在 codespace 內直接 `curl` 後端）。
- [ ] 用新的介面計時器量 10 次查詢時間，記錄到 `docs/metrics.md`。
- [ ] 如果是連接埠轉發的限制，實作非同步查詢工作（ADR 0009）。
- [ ] 第一次 CI 跑完後，記錄各 job 的耗時。
