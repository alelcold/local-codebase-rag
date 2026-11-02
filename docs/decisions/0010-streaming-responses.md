# 0010. Streaming answers with Server-Sent Events

- **Status**: Accepted
- **Date**: 2026-11-02
- **Related**: [0009](0009-timeout-settings.md) (follow-up listed there), [devlog 2026-11-02](../devlog/2026-11-02.md), [devlog 2026-11-01 Codespaces setup](../devlog/2026-11-01-codespace-setup.md), `backend/app/main.py` (`/query/stream`), `backend/app/rag.py` (`RagService.stream`), `frontend/nginx.conf.template`, `frontend/src/api.ts`

> English first; 繁體中文版本在下方. Privacy: illustrated only with the sample project.

## Context

On Codespaces (CPU only, `qwen2.5-coder:3b`) one query took **54.7 s** when sent with `curl` inside the codespace through nginx, and it succeeded. The same query from the browser, through the Codespaces port forwarder, was cut off after **about 100 s** with **504** (test log pitfall #9).

So the forwarder in front of nginx has its own limit, and the 300 s timeouts we own (`PROXY_READ_TIMEOUT`, `LLM_REQUEST_TIMEOUT`, ADR 0009) cannot change it. `/query` returns one JSON body at the end, so for the whole minute (or more) of generation **not one byte** goes back to the browser. A proxy that drops connections without traffic, or that waits a limited time for the first byte of the response, will cut such a request off whatever we configure behind it.

There is also a user-experience problem: during that minute the UI can only show a spinner.

## Decision

Add **`POST /query/stream`**, which returns the same answer as `/query` as **Server-Sent Events** (`text/event-stream`), and make the UI use it. `/query` stays unchanged for CI, scripts and other clients.

1. **Event order**:

   | Event | When | Data |
   | --- | --- | --- |
   | `heartbeat` | Immediately, then whenever nothing else was sent for `STREAM_HEARTBEAT_SECONDS` (default 10) | `{"elapsed_seconds": 12.0}` |
   | `sources` | As soon as retrieval finishes (seconds) | The same source objects as `/query` (`file_path`, lines, score, text…) |
   | `token` | For every chunk Ollama generates | `{"text": "…"}` |
   | `done` | At the end | `retrieval_seconds`, `first_token_seconds`, `total_seconds`, `tokens`, `answer_chars` |
   | `error` | Instead of the rest, if something fails after the stream started | `{"kind": "timeout" \| "error", "stage"?, "detail"}` (same messages as `/query`'s 504 / 502) |

2. **Sources first.** Retrieval takes seconds; generation takes a minute on CPU. Sending the sources first gives the user something useful right away (which files the answer will be based on, readable in full) and proves the pipeline works before the slow part. It also costs nothing: the prompt needs the sources anyway, so they are known before the first token.

3. **Heartbeats.** Before the first token, Ollama is silent for a long time (embedding the question, then prompt processing of about 4k tokens on CPU). The backend sends a `heartbeat` right away, so headers and the first bytes reach the browser before any slow work, and then again after every `STREAM_HEARTBEAT_SECONDS` without other output. Proxies see data flowing for the whole request. The UI ignores them, apart from keeping its timer.

4. **nginx**: an exact `location = /api/query/stream` with `proxy_buffering off`, `proxy_cache off` and `gzip off`. The backend also sends `X-Accel-Buffering: no` and `Cache-Control: no-cache`. `proxy_read_timeout` now counts time **between** two reads, and heartbeats reset it.

5. **Implementation**: the RAG pipeline stays synchronous (LlamaIndex `stream_complete`). It runs in a worker thread that hands events to the async response through an `asyncio.Queue`. The response waits on the queue with a timeout, and the timeout produces the heartbeat. If the client disconnects, a flag stops the worker at the next token and closes the Ollama stream.

6. **Frontend**: `fetch` with a stream reader and a small SSE parser (not `EventSource`, which only supports `GET` without a body). The UI shows the cited files first, then the answer token by token with a cursor, then **time to first token** and **total time**, both measured in the browser from the moment "送出" is clicked. If the connection drops mid-answer, everything already received stays on screen and the error card says that the answer is incomplete and why. A "停止" button aborts the request.

7. **CI**: `scripts/smoke-test.sh` also runs a streaming query through nginx and checks: `text/event-stream`, `sources` is the first non-heartbeat event, at least one `token`, ends with `done`, no `error`. It stamps every line with its arrival time and, with `STREAM_STRICT=1` (set in CI), fails if all events arrived in one burst although the backend streamed for more than a second. It sends `Accept-Encoding: gzip` like a browser. A local test showed that this check is what catches buffering: with `proxy_buffering on` alone, nginx 1.29 still passed events through to a fast client, but with gzip on, the whole answer arrived in one burst at the end.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| **SSE over `fetch`** (chosen) | Plain HTTP response: works through nginx and port forwarders with no upgrade. One-way, which is all we need. Easy to test with `curl -N`. Errors after the start can be sent as an event | Needs `proxy_buffering off`. Not `EventSource` (POST with a body), so a small parser of our own. No automatic reconnect | — |
| WebSocket | Two-way, low overhead per message | Needs an `Upgrade` through every proxy (extra nginx config). Our traffic is one request → one stream, so two-way adds nothing. Harder to test with `curl`. More code on both sides (connection life cycle, ping/pong) | More moving parts for no gain |
| `EventSource` with `GET /query/stream?question=…` | Built-in browser API, automatic reconnect | The question (possibly long) goes in the URL and in access logs. Reconnecting would start the whole generation again | Questions do not belong in URLs; reconnect is harmful here |
| Asynchronous job + polling (like `/index/status`) | Every request is short, so **no** proxy limit of any kind can cut it. Survives a page reload | New job state and storage, cleanup, polling delay. Tokens still arrive in batches | Bigger change. Streaming fixes the forwarder problem seen so far. Kept as the fallback if a proxy turns out to limit total request time |
| Only raise timeouts | No code change | Does not affect hops we do not control (ADR 0009) | Does not fix pitfall #9 |
| Replace `/query` with streaming | One endpoint | Breaks CI, `curl` examples and scripts that expect one JSON | Both are kept; they share the same `RagService` |

## Consequences

- **Positive**: Bytes reach the browser within milliseconds and then at least every 10 s, so an idle limit on a proxy is no longer hit. Users see the cited files after seconds and the answer as it is written. Time to first token becomes visible and measurable. `/query` still works.
- **Negative / trade-offs**:
  - Errors that happen after the stream started cannot change the HTTP status (it is already 200). They arrive as an `error` event, so clients must read the events, not just the status code.
  - The answer is not stripped as a whole: the first token's leading whitespace is removed, the rest is passed on as is.
  - A total-duration limit on a proxy (as opposed to an idle or first-byte limit) still cuts long answers. Then the async job is the next step. {待填：在 Codespaces 透過轉發網址實測串流查詢，確認不再於約 100 秒時被中斷}
  - A disconnected client stops the worker only at the next token; prompt processing already running in Ollama finishes first.
  - The UI no longer calls `/query`; the 504 handling there remains for other clients.
- **Follow-ups**: Measure time to first token on Codespaces and the Mac (`docs/metrics.md`). If a proxy limits total time, implement the async query job.

---

# 0010. 以 Server-Sent Events 串流回答

- **狀態**：已接受
- **日期**：2026-11-02
- **相關**：[0009](0009-timeout-settings.md)（其中列出的後續工作）、[devlog 2026-11-02](../devlog/2026-11-02.md)、[devlog 2026-11-01 Codespaces 環境建置](../devlog/2026-11-01-codespace-setup.md)、`backend/app/main.py`（`/query/stream`）、`backend/app/rag.py`（`RagService.stream`）、`frontend/nginx.conf.template`、`frontend/src/api.ts`

## 背景

在 Codespaces（只有 CPU、`qwen2.5-coder:3b`）上，在 codespace 內用 `curl` 經過 nginx 查詢，一次花了 **54.7 秒**，而且成功。同樣的查詢從瀏覽器經過 Codespaces 連接埠轉發，卻在**約 100 秒**時被中斷，回傳 **504**（測試紀錄踩坑 #9）。

也就是說，nginx 前面的轉發有自己的上限，我們能控制的 300 秒逾時（`PROXY_READ_TIMEOUT`、`LLM_REQUEST_TIMEOUT`，ADR 0009）改變不了它。`/query` 要等到最後才回傳一整個 JSON，所以在生成的那一分鐘（或更久）裡，**連一個 byte** 都不會回到瀏覽器。只要代理會切斷沒有流量的連線，或只願意等回應的第一個 byte 一段時間，不論後面怎麼設定，這種請求都會被切斷。

另外還有使用體驗的問題：那一分鐘裡，介面只能顯示轉圈圈。

## 決策

新增 **`POST /query/stream`**，以 **Server-Sent Events**（`text/event-stream`）回傳和 `/query` 相同的回答，並讓介面改用它。`/query` 維持不變，供 CI、腳本與其他用戶端使用。

1. **事件順序**：

   | 事件 | 時機 | 資料 |
   | --- | --- | --- |
   | `heartbeat` | 一開始馬上送一次，之後只要 `STREAM_HEARTBEAT_SECONDS`（預設 10）秒內沒有送出其他事件就再送 | `{"elapsed_seconds": 12.0}` |
   | `sources` | 檢索一完成就送（幾秒內） | 和 `/query` 相同的來源物件（`file_path`、行號、分數、內容…） |
   | `token` | Ollama 每產生一段文字就送 | `{"text": "…"}` |
   | `done` | 結束時 | `retrieval_seconds`、`first_token_seconds`、`total_seconds`、`tokens`、`answer_chars` |
   | `error` | 串流開始後才失敗時，取代後續事件 | `{"kind": "timeout" \| "error", "stage"?, "detail"}`（訊息與 `/query` 的 504／502 相同） |

2. **先送引用片段**：檢索只要幾秒，生成在 CPU 上要一分鐘。先送來源，使用者馬上就有有用的資訊（回答會根據哪些檔案，而且可以展開閱讀），也證明慢的步驟之前的流程都正常。而且沒有額外成本：組提示詞本來就需要這些來源，第一個 token 出現前就已經知道了。

3. **Heartbeat**：第一個 token 出現前，Ollama 會沉默很久（先把問題轉成向量，再在 CPU 上處理約 4k tokens 的提示詞）。後端一開始就先送一次 `heartbeat`，讓回應標頭與第一批 byte 在任何慢的工作開始前就送到瀏覽器；之後每 `STREAM_HEARTBEAT_SECONDS` 秒沒有其他輸出就再送一次。代理在整個請求期間都看得到資料流動。介面除了維持計時，不處理 heartbeat。

4. **nginx**：用精確比對的 `location = /api/query/stream`，設定 `proxy_buffering off`、`proxy_cache off`、`gzip off`。後端也會送出 `X-Accel-Buffering: no` 與 `Cache-Control: no-cache`。`proxy_read_timeout` 變成計算**兩次讀取之間**的時間，heartbeat 會讓它重新計時。

5. **實作**：RAG 流程維持同步（LlamaIndex 的 `stream_complete`），在背景執行緒中執行，透過 `asyncio.Queue` 把事件交給非同步的回應。回應等待佇列時設有逾時，逾時就送出 heartbeat。用戶端中斷連線時，會設定一個旗標，背景執行緒在下一個 token 時停止，並關閉對 Ollama 的串流。

6. **前端**：用 `fetch` 加上串流讀取器與一個小型 SSE 解析器（不用 `EventSource`，因為它只支援沒有 body 的 `GET`）。介面先顯示引用的檔案，再逐字顯示回答（附游標），最後顯示**首字延遲**與**總耗時**，兩者都是在瀏覽器端從按下「送出」開始計算。回答到一半連線中斷時，已收到的內容都會保留在畫面上，錯誤卡片會說明回答不完整以及可能原因。「停止」按鈕可以中止請求。

7. **CI**：`scripts/smoke-test.sh` 也會透過 nginx 執行一次串流查詢，並檢查：`text/event-stream`、第一個非 heartbeat 事件是 `sources`、至少一個 `token`、以 `done` 結束、沒有 `error`。它會為每一行記下收到的時間；設定 `STREAM_STRICT=1`（CI 有設定）時，如果後端串流超過 1 秒、所有事件卻在同一瞬間到達，就判定失敗。它和瀏覽器一樣送出 `Accept-Encoding: gzip`。本機測試發現，這一點正是抓到緩衝的關鍵：只開 `proxy_buffering on` 時，nginx 1.29 對速度快的用戶端仍會逐一轉送事件；但加上 gzip 後，整個回答會在最後一次全部到達。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| **以 `fetch` 讀取 SSE**（採用） | 就是一般的 HTTP 回應，不需要協定升級，nginx 與連接埠轉發都能通過。單向傳輸，正好符合需求。可以用 `curl -N` 測試。開始後的錯誤可以用事件送出 | 需要 `proxy_buffering off`。不能用 `EventSource`（要 POST 帶 body），所以要自己寫小型解析器。沒有自動重連 | — |
| WebSocket | 雙向、每則訊息的額外負擔小 | 每一層代理都要支援 `Upgrade`（nginx 要額外設定）。我們的流量是一個請求對一個串流，雙向沒有好處。難以用 `curl` 測試。兩端都要多寫程式（連線生命週期、ping/pong） | 多了很多零件，卻沒有好處 |
| `EventSource` 搭配 `GET /query/stream?question=…` | 瀏覽器內建 API、會自動重連 | 問題（可能很長）會出現在網址與存取紀錄裡。重連會從頭重新生成 | 問題不該放在網址裡；在這裡自動重連有害 |
| 非同步工作 + 輪詢（像 `/index/status`） | 每個請求都很短，**任何**代理限制都切不斷。重新整理頁面也不會遺失 | 要新增工作狀態與儲存、清理機制，有輪詢延遲。token 仍是一批一批出現 | 改動較大。串流已能解決目前遇到的轉發問題。若發現代理限制的是請求總時間，再改用這個方案 |
| 只調高逾時 | 不用改程式 | 管不到我們無法控制的連線段（ADR 0009） | 解決不了踩坑 #9 |
| 用串流取代 `/query` | 只有一個端點 | CI、`curl` 範例與期待一整個 JSON 的腳本都會壞掉 | 兩者並存，共用同一個 `RagService` |

## 後果

- **正面**：幾毫秒內就有資料送到瀏覽器，之後至少每 10 秒一次，不會再觸發代理的閒置上限。使用者幾秒後就看到引用的檔案，並看著回答逐字出現。首字延遲變得看得到、量得到。`/query` 照常可用。
- **負面／取捨**：
  - 串流開始後才發生的錯誤，無法再改變 HTTP 狀態碼（已經是 200），只能用 `error` 事件傳送，所以用戶端必須讀事件，不能只看狀態碼。
  - 回答不會整段 strip：只移除第一個 token 開頭的空白，其餘原樣轉送。
  - 如果代理限制的是請求的**總時間**（而不是閒置時間或等待第一個 byte 的時間），太長的回答仍會被切斷，這時非同步工作就是下一步。{待填：在 Codespaces 透過轉發網址實測串流查詢，確認不再於約 100 秒時被中斷}
  - 用戶端中斷後，背景執行緒要到下一個 token 才會停止；Ollama 中已經開始的提示詞處理會先跑完。
  - 介面不再呼叫 `/query`；那裡的 504 處理仍保留給其他用戶端。
- **後續工作**：量測 Codespaces 與 Mac 的首字延遲（`docs/metrics.md`）。若代理限制總時間，實作非同步查詢工作。
