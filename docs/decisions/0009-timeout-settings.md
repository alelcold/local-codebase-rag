# 0009. Timeout settings for slow (CPU-only) inference

- **Status**: Accepted
- **Date**: 2026-11-02
- **Related**: [0006](0006-multi-environment-deployment.md), [0007](0007-multi-environment-testing-strategy.md), [devlog 2026-11-01 Codespaces setup](../devlog/2026-11-01-codespace-setup.md), `frontend/nginx.conf.template`, `backend/app/config.py`

> English first; 繁體中文版本在下方.

## Context

On Codespaces (CPU only, `qwen2.5-coder:3b`) the UI showed **504** for queries. A single query was estimated to take 1.5–2 minutes.

A query passes through several hops, and **each hop has its own timeout**:

```text
browser → [port forwarder, e.g. Codespaces] → nginx (/api) → backend (FastAPI) → Ollama
                 timeout we do not control      proxy_read_timeout   LLM_REQUEST_TIMEOUT
```

What we found:

| Hop | Before this change | Problem |
| --- | --- | --- |
| nginx `proxy_read_timeout` / `proxy_send_timeout` | Hard-coded 900 s | Could not be changed without rebuilding the image |
| Backend → Ollama LLM (`LLM_REQUEST_TIMEOUT`) | 600 s | Configurable, but a timeout was returned as a generic **502** with a raw exception name |
| Backend → Ollama embeddings | **No timeout** (the ollama client default is to wait forever) | A stuck embedding call hung the request until some other hop gave up |
| UI | One static message: "may take 30 s or more" | No feedback on how long it had been waiting; on failure it showed only `504 Gateway Timeout` |

nginx was already set to 900 s, so the 504 seen on Codespaces after about 1.5–2 minutes most likely came from a hop **in front of** nginx (the Codespaces port forwarder), not from nginx itself. {待補：確認 504 的實際來源，例如直接 `curl localhost:8000/query` 是否成功}. Whatever the source, the stack needs three things: timeouts we can configure, timeouts that fail with a clear message, and a UI that shows it is still working.

## Decision

1. **Every timeout we own is configurable in `.env`, with a 300 s default**:

   | Variable | Hop | Default |
   | --- | --- | --- |
   | `PROXY_READ_TIMEOUT`, `PROXY_SEND_TIMEOUT` | nginx → backend (`/api`) | 300 |
   | `LLM_REQUEST_TIMEOUT` | backend → Ollama, generation | 300 |
   | `EMBED_REQUEST_TIMEOUT` | backend → Ollama, embeddings (new) | 300 |

   nginx reads its values through the official image's template mechanism (`/etc/nginx/templates/*.template` plus `envsubst`, limited to `^PROXY_` variables), so changing them only needs `docker compose up -d`, not a rebuild.

2. **300 s as the default.** It is about 2–3 times the estimated CPU-only query time (1.5–2 minutes with 3B on Codespaces). The Mac with a GPU is expected to be faster, but that has not been measured yet ({待填} in `docs/metrics.md`). Slower setups raise the values in `.env`.

3. **Timeouts fail clearly**: the backend turns an Ollama timeout into **504** with a message that names the stage and the setting to raise, for example `Ollama 生成回答逾時：超過 300 秒仍未回應（LLM_REQUEST_TIMEOUT）`. Other failures stay **502**.

4. **The UI shows progress and explains failures**: while waiting it shows "生成中" and the seconds elapsed. On failure it tells apart (a) a backend timeout (504 with a JSON message), (b) a proxy timeout (504 without the backend's JSON, from nginx or a port forwarder) and (c) a dropped connection. For each case it lists likely causes and fixes.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Keep long hard-coded values (nginx 900 s, LLM 600 s) | No change | Cannot be tuned per environment; did not prevent the Codespaces 504; embeddings still had no timeout | Does not solve the problem |
| Very high or unlimited timeouts | Never time out on our side | A hung Ollama call keeps a worker busy forever; users get no answer and no error | Failing clearly is better than hanging |
| Different defaults per hop (for example nginx 330 s > LLM 300 s) | The backend's clearer 504 message always arrives before nginx gives up | Two numbers to explain; the user asked for one simple default | Documented as a tuning tip instead (see Consequences) |
| Streaming the answer (Server-Sent Events) | Text appears as it is generated; keeps the connection busy, which avoids proxy idle timeouts | Bigger change to the backend, nginx (buffering) and UI; does not help if a proxy limits total request time | Larger change; follow-up |
| Asynchronous query job + polling (like `/index/status`) | Every HTTP request is short, so **no** proxy timeout can cut it | New endpoints and state; more moving parts | Best long-term fix for port forwarders; follow-up |
| Client-side timeout in the browser | The UI decides when to stop | Duplicates server timeouts; can cancel a request that was about to succeed | Not needed once the UI shows elapsed time |

## Consequences

- **Positive**: The same images work on a Mac with a GPU and on a CPU-only Codespace by changing only `.env`. A timeout now says which setting to raise. Embeddings can no longer hang forever. Users see that the system is working.
- **Negative / trade-offs**:
  - The defaults are **lower** than before (nginx 900 → 300 s, LLM 600 → 300 s). A very slow setup that used to finish in 5–15 minutes now needs larger values in `.env`.
  - With equal values, nginx can give up just before the backend's own timeout fires, so the user sees the generic proxy message instead of the backend's specific one. **Tip**: set `PROXY_READ_TIMEOUT` a little higher than `LLM_REQUEST_TIMEOUT`, for example 330 and 300.
  - Timeouts on hops we do not control (Codespaces port forwarding, corporate proxies) still apply. Raising our values cannot get around them.
  - nginx refuses to start if `PROXY_*_TIMEOUT` is not a valid number.
- **Follow-ups**: Confirm where the Codespaces 504 came from. If it is the port forwarder, implement the async query job (or streaming) so no single HTTP request lasts minutes. Record CPU and Mac query times in `docs/metrics.md`.

---

# 0009. 推論很慢（只有 CPU）時的逾時設定

- **狀態**：已接受
- **日期**：2026-11-02
- **相關**：[0006](0006-multi-environment-deployment.md)、[0007](0007-multi-environment-testing-strategy.md)、[devlog 2026-11-01 Codespaces 環境建置](../devlog/2026-11-01-codespace-setup.md)、`frontend/nginx.conf.template`、`backend/app/config.py`

## 背景

在 Codespaces（只有 CPU、`qwen2.5-coder:3b`）上查詢時，介面顯示 **504**。推算單次查詢需要 1.5～2 分鐘。

一次查詢會經過好幾段連線，**每一段都有自己的逾時設定**：

```text
瀏覽器 → [連接埠轉發，例如 Codespaces] → nginx（/api） → 後端（FastAPI） → Ollama
              我們無法控制的逾時              proxy_read_timeout   LLM_REQUEST_TIMEOUT
```

檢查後發現：

| 連線段 | 修改前 | 問題 |
| --- | --- | --- |
| nginx `proxy_read_timeout`／`proxy_send_timeout` | 寫死 900 秒 | 不重新 build 映像檔就無法修改 |
| 後端 → Ollama LLM（`LLM_REQUEST_TIMEOUT`） | 600 秒 | 可以設定，但逾時會被包成一般的 **502**，只顯示原始例外名稱 |
| 後端 → Ollama embedding | **沒有逾時**（ollama client 預設會一直等下去） | embedding 卡住時，請求會一直掛著，直到其他連線段先放棄 |
| 介面 | 只有一句固定文字：「可能要 30 秒以上」 | 看不出已經等了多久；失敗時只顯示 `504 Gateway Timeout` |

nginx 原本就設成 900 秒，所以在 Codespaces 上約 1.5～2 分鐘就出現的 504，很可能來自 nginx **前面**的連線段（Codespaces 的連接埠轉發），而不是 nginx 本身。{待補：確認 504 的實際來源，例如直接 `curl localhost:8000/query` 是否成功}。不論來源是哪一段，系統都需要三件事：可以設定的逾時、逾時時有清楚的錯誤訊息，以及讓使用者知道系統還在運作的介面。

## 決策

1. **我們能控制的逾時，全部可在 `.env` 設定，預設 300 秒**：

   | 變數 | 連線段 | 預設值 |
   | --- | --- | --- |
   | `PROXY_READ_TIMEOUT`、`PROXY_SEND_TIMEOUT` | nginx → 後端（`/api`） | 300 |
   | `LLM_REQUEST_TIMEOUT` | 後端 → Ollama，生成回答 | 300 |
   | `EMBED_REQUEST_TIMEOUT` | 後端 → Ollama，embedding（新增） | 300 |

   nginx 透過官方映像檔的 template 機制讀取設定（`/etc/nginx/templates/*.template` 搭配 `envsubst`，只代換 `^PROXY_` 開頭的變數），所以修改後只要 `docker compose up -d`，不必重新 build。

2. **預設 300 秒**：大約是只有 CPU 時推算查詢時間（Codespaces 上 3B 約 1.5～2 分鐘）的 2～3 倍。有 GPU 的 Mac 預期會更快，但還沒有實際量測（`docs/metrics.md` 目前為 {待填}）。更慢的環境就在 `.env` 調高。

3. **逾時時清楚報錯**：後端把 Ollama 逾時轉成 **504**，訊息會寫出是哪個階段、要調整哪個設定，例如 `Ollama 生成回答逾時：超過 300 秒仍未回應（LLM_REQUEST_TIMEOUT）`。其他錯誤維持 **502**。

4. **介面顯示進度並解釋失敗原因**：等待時顯示「生成中」與已等待秒數。失敗時區分三種情況：(a) 後端逾時（504，帶 JSON 訊息）、(b) 代理逾時（504，但沒有後端的 JSON，來自 nginx 或連接埠轉發）、(c) 連線中斷。每種情況都列出可能原因與處理方式。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 維持寫死的長逾時（nginx 900 秒、LLM 600 秒） | 不用改 | 無法依環境調整；沒有避免 Codespaces 的 504；embedding 仍然沒有逾時 | 沒有解決問題 |
| 設成非常長或不設逾時 | 我們這邊永遠不會逾時 | Ollama 卡住時會一直佔著 worker；使用者既拿不到回答，也看不到錯誤 | 清楚失敗比一直掛著好 |
| 每段設不同預設值（例如 nginx 330 秒 > LLM 300 秒） | 後端比較清楚的 504 訊息一定會比 nginx 先出現 | 要解釋兩個數字；需求是一個簡單的預設值 | 改成寫在調整建議裡（見「後果」） |
| 串流回答（Server-Sent Events） | 邊生成邊顯示；連線一直有資料，可以避開代理的閒置逾時 | 後端、nginx（緩衝設定）與介面都要大改；如果代理限制的是整個請求的總時間，串流也沒用 | 改動較大；列為後續工作 |
| 非同步查詢工作 + 輪詢（類似 `/index/status`） | 每個 HTTP 請求都很短，**任何**代理的逾時都切不斷 | 需要新的 API 與狀態管理，元件變多 | 對連接埠轉發來說是長期最好的解法；列為後續工作 |
| 在瀏覽器端設逾時 | 由介面決定何時停止 | 和伺服器端的逾時重複；可能取消一個快要成功的請求 | 介面已經顯示等待秒數，不需要 |

## 後果

- **正面**：同一份映像檔，只要改 `.env`，就能在有 GPU 的 Mac 與只有 CPU 的 Codespace 上使用。逾時時會說明要調整哪個設定。embedding 不會再無限期卡住。使用者看得到系統還在運作。
- **負面／取捨**：
  - 預設值比以前**低**（nginx 900 → 300 秒，LLM 600 → 300 秒）。以前要跑 5～15 分鐘才完成的極慢環境，現在需要在 `.env` 設更大的值。
  - 兩個值相同時，nginx 可能比後端自己的逾時早一點放棄，使用者會看到一般的代理逾時訊息，而不是後端比較具體的訊息。**建議**：把 `PROXY_READ_TIMEOUT` 設得比 `LLM_REQUEST_TIMEOUT` 稍大，例如 330 與 300。
  - 我們無法控制的連線段（Codespaces 連接埠轉發、公司的代理伺服器）仍然有自己的逾時，調高我們的設定也繞不過去。
  - `PROXY_*_TIMEOUT` 如果不是合法的數字，nginx 會無法啟動。
- **後續工作**：確認 Codespaces 的 504 從哪裡來。如果是連接埠轉發，就實作非同步查詢工作（或串流），讓單一 HTTP 請求不會持續好幾分鐘。把 CPU 與 Mac 的查詢時間記錄到 `docs/metrics.md`。
