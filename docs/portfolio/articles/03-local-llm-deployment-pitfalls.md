# Article 3 (draft) — Lessons from deploying a local LLM: narrowing down failures layer by layer

> **Status**: first draft, not published.
> **Language**: this article is written in Traditional Chinese for publication on Chinese-language platforms, so it is an exception to the repo's English-first rule. A one-paragraph English summary follows; the full text is below.
> **Plan**: Article 3 in [`../article-series.md`](../article-series.md). Sources: [devlog 2026-11-01](../../devlog/2026-11-01.md), [devlog 2026-11-01 Codespaces setup](../../devlog/2026-11-01-codespace-setup.md), [devlog 2026-11-02](../../devlog/2026-11-02.md), [`metrics.md`](../../metrics.md), ADRs [0002](../../decisions/0002-ollama-outside-docker-on-mac.md), [0006](../../decisions/0006-multi-environment-deployment.md), [0007](../../decisions/0007-multi-environment-testing-strategy.md), [0008](../../decisions/0008-ci-design.md), [0009](../../decisions/0009-timeout-settings.md), [0010](../../decisions/0010-streaming-responses.md), [0011](../../decisions/0011-devcontainer-for-codespaces.md).
> **Privacy**: every path, symbol and question comes from `examples/sample-game-frontend/` or this repo.

**English summary.** I built an on-prem RAG system for asking questions about a game front-end codebase (Ollama on the host; Qdrant, FastAPI + LlamaIndex and a React UI in Docker). With no Mac available, I tested it first in GitHub Codespaces (Linux, CPU only). Three failures came up, and each was solved by narrowing the scope one layer at a time: containers could not reach Ollama (`host.docker.internal` does not exist on Linux, and Ollama listens on `127.0.0.1` by default); after restarting the codespace, indexing failed because Ollama does not restart by itself; and queries returned 504 after about 100 seconds, which `curl` tests at each hop traced to the Codespaces port forwarder rather than nginx, fixed by streaming the answer. The article ends with measured numbers, notes on working with an AI coding agent, and next steps (real Mac hardware, 14B model).

---

# 地端 LLM 部署踩坑紀錄：一層一層縮小範圍

> 草稿。`[截圖：…]` 是建議放截圖的位置，`{待填}` 是還沒量到的數據。

## TL;DR

- 我做了一套地端的 codebase RAG：Ollama 跑在主機上，Qdrant、FastAPI + LlamaIndex 後端、React 前端跑在 Docker 裡。
- 手邊沒有 Mac，所以先在 GitHub Codespaces（Linux、只有 CPU）上測。踩到三個坑，每個都不是程式邏輯的 bug，而是**環境與網路**的問題，單元測試全部通過也抓不到。
- 三個坑的除錯方法都一樣：**從呼叫端的位置、一段一段驗證**，每次只排除一層。
- CPU 上 3B 模型、`TOP_K=4`，一次查詢約 55 秒。最後的 504 是 Codespaces 的連接埠轉發在約 100 秒時切斷連線，調高我們自己的逾時沒有用，改成串流回應才解決。

---

## 1. 背景：為什麼做這個、為什麼在 Codespaces 測

### 為什麼做地端 codebase RAG

遊戲前端專案（大約 50～300 個檔案）裡，新人最常問的是「X 在哪裡設定？」「這個流程從哪裡開始？」這類問題。grep 找得到字串，但回答不了「為什麼」和「怎麼串起來」。

雲端 AI 助手可以回答，但有兩個問題讓我不想用：

1. **程式碼不能離開公司的機器。** 這是硬性限制。
2. **團隊需要的是共用工具**，而不是每個人各自付費、各自設定。

所以目標是：一台機器上跑完整套流程，用自然語言提問，回答附上 `檔案:起始行-結束行` 的引用，程式碼與問題都不離開本機（ADR 0001）。

以範例專案為例，問「玩家受傷後的無敵時間在哪裡設定？」，好的回答要指出 `src/config/gameConfig.ts` 的 `INVINCIBLE_MS = 1500`，以及 `src/entities/Player.ts` 裡使用它的地方。

[截圖：介面回答「玩家受傷後的無敵時間在哪裡設定？」，展開 gameConfig.ts 的引用]

### 為什麼在 Codespaces 測

正式環境是 Mac M2 32GB，但開發期間我**沒有 Mac 可用**。與其等，不如先在一個免費、用完即丟的 Linux 環境把整條流程跑通：

- 安裝 → 索引範例專案 → 從介面提問 → 拿到附引用的回答。
- 模型從 14B 換成 `qwen2.5-coder:3b`，因為只有 CPU 時 14B 太慢，不適合拿來驗證流程。embedding 維持 `nomic-embed-text`。

事後看，這個決定的價值不在於「先跑起來」，而是 Codespaces 剛好是一個**和 Mac 差異很大**的環境，逼出了一堆在 Mac 上不會遇到、但部署到 Linux 伺服器時一定會遇到的問題。

---

## 2. 架構與三種環境的差異

```text
瀏覽器 ──► nginx（前端容器，/api 代理）──► FastAPI + LlamaIndex（後端容器）──► Ollama（主機）
                                                     │
                                                     └──► Qdrant（容器）
```

一個關鍵決定是：**Ollama 不放進 Docker**（ADR 0002）。macOS 上的 Docker Desktop 是在 Linux VM 裡跑容器，Apple 的 Metal GPU 不會傳進 VM。把 Ollama 放進 compose，在 Mac 上就只能用 CPU。所以 Ollama 一律在主機上原生執行，容器透過 `http://host.docker.internal:11434` 呼叫它。

這個決定在 Mac 上很自然，但換到 Linux 就開始出事。三種環境的差異（ADR 0006）：

| 項目 | Mac M2 32GB | GitHub Codespaces | EC2 GPU 機器（評估中） |
| --- | --- | --- | --- |
| 用途 | 團隊正式使用 | 部署前的 Linux 預演、驗證流程 | 測試 32B 等大模型 |
| Docker | Docker Desktop（Linux VM） | Linux、Docker Engine（docker-in-docker） | Linux、Docker Engine |
| GPU | Metal（只有主機能用） | 無 | NVIDIA（例如 `g5.xlarge` 的 A10G 24GB） |
| `host.docker.internal` | Docker Desktop 自動提供 | **不存在**，要加 `extra_hosts: host-gateway` | **不存在**，同左 |
| Ollama 監聽位址 | 預設 `127.0.0.1` 即可 | 必須 `0.0.0.0` | 必須 `0.0.0.0`（systemd override） |
| Ollama 啟動方式 | App／`brew services`，開機自動啟動 | `postStartCommand` 每次啟動時執行 | systemd |
| `LLM_MODEL` | `qwen2.5-coder:14b` | `qwen2.5-coder:3b` | `qwen2.5-coder:32b` |
| 對外開放 | 前端只綁 `127.0.0.1`，要給區網用再開 | 11434 不轉發、Ports 維持 private | Security group 只開 SSH，其他走 SSH tunnel |
| 實測狀態 | {待填} | 已測（本文） | {待填} |

規則是：**所有環境共用同一個 `docker-compose.yml`**，差異只放在 `.env` 和 Ollama 的啟動方式。`extra_hosts: host.docker.internal:host-gateway` 寫在主檔裡，在 Docker Desktop 上無害，在 Linux 上是必要的。

---

## 3. 踩坑故事

### 坑 1：容器連不到 Ollama

**現象**

服務都起來了，但後端的 `/health` 回報連不到 Ollama。奇怪的是，在 codespace 的終端機裡：

```bash
curl -sS http://localhost:11434/api/version
```

是通的。

```text
{待填：/health 回傳的 ollama.error，或 docker compose logs backend 的錯誤}
```

[截圖：/health 顯示 Ollama 連線失敗]

**推測**

「我這裡連得到」和「容器連得到」是兩件事。在容器裡，`localhost` 指的是容器自己；容器要連到主機，走的是 Docker bridge 的 gateway，不是主機的 loopback。所以可疑的有兩層：

1. 名稱解析：`host.docker.internal` 在 Linux 上解析得到嗎？
2. 監聽位址：Ollama 有沒有在 bridge gateway 那張網卡上聽？

**驗證**

不要在主機上測，要**從呼叫端的位置測**。開一個用完即丟的容器，它看到的網路和後端容器一樣：

```bash
docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl -sS http://host.docker.internal:11434/api/version
```

這一行同時處理掉兩層：`--add-host=…:host-gateway` 對應 compose 裡的 `extra_hosts`，解決名稱解析；如果加了之後還是 connection refused，問題就只剩監聽位址。

接著看 Ollama 到底聽在哪：

```bash
ss -ltnp | grep 11434
```

預設是 `127.0.0.1:11434`，只接受同一個網路命名空間來的連線，從 bridge gateway 進來的連線會被拒絕。

[截圖：ss -ltnp 顯示 Ollama 監聽 127.0.0.1:11434]

順帶一提，這裡踩到一個小坑：一開始我用 `curl -s`，失敗時什麼都沒印出來，分不出是連線被拒、逾時還是回應本來就空。`-s` 除了關進度條，也會**一起**關掉錯誤訊息。之後一律用 `-sS`（`--show-error`）。

**解法**

```bash
OLLAMA_HOST=0.0.0.0 ollama serve
```

再加上 compose 裡的：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

為什麼 Mac 上不需要？因為 Docker Desktop 會自動解析 `host.docker.internal`，並把連線轉到主機的 loopback，所以 Ollama 預設的 `127.0.0.1` 就能用。同一份設定、同一個錯誤，在 Mac 上根本不會出現。

**資安提醒**：`0.0.0.0` 代表 11434 在所有網卡上開放，而 Ollama 本身沒有驗證機制。在 Codespaces 要確保 11434 是 private（後來在 `devcontainer.json` 直接設成不轉發）；在 EC2 要用 security group 擋掉。

[截圖：修正後 /health 顯示 "status": "ok"]

---

### 坑 2：重開 Codespace 後，索引全部失敗

**現象**

前一天流程已經跑通。隔天把停止的 codespace 重新開起來，執行索引，所有檔案都失敗。

```text
{待填：索引失敗時的錯誤訊息}
```

**推測**

程式碼、`.env`、模型檔都還在，跟昨天唯一的差別是「codespace 被停止又啟動過」。索引需要呼叫 Ollama 產生 embedding，所以先懷疑 Ollama。

**驗證**

用坑 1 學到的方法，由內而外一層一層確認：

```bash
curl -sS http://localhost:11434/api/version
```

連不上。再看程序：

```bash
ss -ltnp | grep 11434
```

沒有任何東西在聽 11434。Ollama 根本沒有在跑。

原因很單純：**停止的 codespace 會保留檔案，但不會保留執行中的程序**。前一天我是手動用 `nohup ollama serve &` 在背景啟動的，重開之後它就不見了。Mac 上 Ollama App 會開機自動啟動，所以這也是 Mac 上不會遇到的問題。

**解法**

把手動步驟變成 dev container 設定（ADR 0011）。關鍵是兩個 hook 的差別：

- `postCreateCommand`：**只在建立時**執行一次，適合安裝 Ollama、建立 `.env`。
- `postStartCommand`：**每次啟動**都執行，常駐的服務要放這裡。

`.devcontainer/post-start.sh` 每次啟動會依序：

1. Ollama 沒有回應時，以 `OLLAMA_HOST=0.0.0.0` 在背景啟動，用 `>>` 附加到 log（`>` 會把上一次的 log 清掉，這也是我踩過的坑）。
2. 等 Ollama 就緒，拉缺少的模型。
3. `docker compose up -d`。
4. Qdrant 沒有索引時建立索引。
5. 執行 `scripts/doctor.sh` 做健康檢查，印出網址。

`scripts/doctor.sh` 是把這兩個坑的排查步驟直接寫成腳本：Ollama 已安裝 → 程序在跑 → API 有回應 → 監聽位址 → 模型 → Docker → 容器 → **容器連得到 Ollama** → 後端 `/health` → nginx 代理 → Qdrant 有索引。每一項失敗都印出修正指令，依賴它的後續檢查會略過，直接告訴你斷在哪一層。

[截圖：scripts/doctor.sh 全部通過的輸出]

[截圖：docker compose ps 全部 healthy]

---

### 坑 3：504 逾時排查

這是三個坑裡最花時間的一個，也最能說明「一層一層縮小範圍」的意思。

一次查詢會經過這幾段連線，**每一段都有自己的逾時**：

```text
瀏覽器 → Codespaces 連接埠轉發 → nginx（/api）→ 後端（FastAPI）→ Ollama
          我們控制不了            proxy_read_timeout  LLM_REQUEST_TIMEOUT
```

一個請求能等多久，取決於**最沒耐心的那一段**。

#### 第一輪：懷疑 nginx

**現象**：從介面提問，等了一陣子後顯示 504 Gateway Timeout。

```text
{待填：介面顯示的錯誤訊息}
```

[截圖：介面顯示 504 Gateway Timeout]

**推測**：504 是代理回的，最近的代理是 nginx，而 nginx 的 `proxy_read_timeout` 預設是 60 秒。CPU 上跑 3B 模型，一次查詢超過 60 秒很合理。

**解法嘗試**：把 nginx 與後端呼叫 Ollama 的逾時都改成可以在 `.env` 設定，預設 300 秒（ADR 0009）：

| 變數 | 連線段 | 預設 |
| --- | --- | --- |
| `PROXY_READ_TIMEOUT`、`PROXY_SEND_TIMEOUT` | nginx → 後端 | 300 |
| `LLM_REQUEST_TIMEOUT` | 後端 → Ollama（生成） | 300 |
| `EMBED_REQUEST_TIMEOUT` | 後端 → Ollama（embedding，原本**完全沒有逾時**） | 300 |

nginx 透過官方映像的 template 機制（`/etc/nginx/templates/*.template` + `envsubst`）讀取設定，改 `.env` 後 `docker compose up -d` 就生效，不用重新 build。

順便處理了兩件事：後端遇到 Ollama 逾時時回傳 504，並寫出是哪個階段、要調哪個變數（以前是籠統的 502）；介面等待時顯示「生成中」與已等待秒數。

> 📝 待確認：repo 的歷史中，PR #1 的 nginx 設定已寫死 `proxy_read_timeout 900s`（ADR 0009 的「修改前」欄位）。發文前請對照測試紀錄，確認第一次遇到 504 時 nginx 實際生效的是預設 60 秒，還是 900 秒，並修正這一段的敘述。

**結果**：還是 504。而且斷線時間點**固定在約 100 秒**，跟我設的 300 秒對不上。

#### 第二輪：斷在 100 秒，代表不是我們設的任何一個值

這是整個排查的轉折點。我們這邊的三個逾時都是 300 秒，沒有任何一個是 100 秒。斷線時間和自己的設定對不上，就表示**放棄的是另一段連線**。

在 nginx 前面的只剩一段：**Codespaces 的連接埠轉發**。從瀏覽器打開的 `https://<codespace>-8080.app.github.dev` 不是直連 nginx，中間還有 GitHub 的轉發代理，它有自己的上限，我們設定不了。

#### 第三輪：用 curl 分層驗證

推測要用實驗確認。做法是**繞過可疑的那一層，看問題會不會消失**。

在 codespace 內部直接打 nginx，完全不經過連接埠轉發：

```bash
time curl -sS localhost:8080/api/query -H 'Content-Type: application/json' -d '{"question":"玩家受傷後的無敵時間在哪裡設定？"}'
```

結果：**54.7 秒成功**，拿到完整的回答與引用。

[截圖：codespace 內 curl 經 nginx 查詢成功，time 顯示 54.7 秒]

同樣的查詢從瀏覽器經轉發網址送出：**約 100 秒後 504**。

| 路徑 | 結果 |
| --- | --- |
| codespace 內 `curl` → nginx → 後端 → Ollama | 54.7 秒成功 |
| 瀏覽器 → 連接埠轉發 → nginx → 後端 → Ollama | 約 100 秒後 504 |

nginx、後端、Ollama 這三段已經被第一條路徑證明沒問題，差別只有連接埠轉發，範圍縮到只剩一層。

（瀏覽器那次為什麼比 54.7 秒久、久到撞上 100 秒——模型還沒載入、`top_k` 不同，或是排在另一個請求後面——目前還沒確認，{待填}。）

[截圖：瀏覽器 DevTools Network 面板，/api/query 約 100 秒後 504]

#### 解法：讓連線不要閒置——串流回應

原本的 `/query` 要等整個回答生成完才回傳一個 JSON，所以生成的那一分鐘裡，**連一個 byte 都不會送回瀏覽器**。只要代理會切斷沒有流量的連線、或只等第一個 byte 一段時間，這種請求不管後面怎麼設定都會被切。

我們改不了轉發的上限，但可以改請求的形狀。新增 `POST /query/stream`，用 Server-Sent Events 回傳（ADR 0010）：

| 事件 | 時機 |
| --- | --- |
| `heartbeat` | 一開始馬上送一次，之後只要 10 秒（`STREAM_HEARTBEAT_SECONDS`）沒有其他輸出就再送 |
| `sources` | 檢索完成就送（幾秒內），使用者先看到引用的檔案 |
| `token` | Ollama 每產生一段文字就送 |
| `done` | 結束，附 `first_token_seconds`、`total_seconds` 等統計 |
| `error` | 串流開始後才失敗時使用（HTTP 狀態碼已經是 200，改不了） |

nginx 要為串流另設一個 location，關掉緩衝：

```nginx
location = /api/query/stream {
    proxy_pass http://backend:8000/query/stream;
    proxy_buffering off;
    proxy_cache off;
    gzip off;
    # ...
}
```

這裡又踩到一個小坑。我寫了冒煙測試來確認「代理有緩衝時測試會失敗」，結果只開 `proxy_buffering on`，事件仍然一個一個到達，測試永遠不會失敗。真正把串流卡住的是 **gzip**：對 `text/event-stream` 開 `gzip on` 後，一個 4 秒回答的 13 個 token 全部在最後同一瞬間到達。測試用的 `curl` 沒有送 `Accept-Encoding: gzip`，nginx 就不壓縮，問題被藏起來了；而瀏覽器一定會送這個標頭。修正方式是 location 裡加 `gzip off`，冒煙測試改用 `curl --compressed`，並檢查事件是否分散在不同時間到達。

前端用 `fetch` + 串流讀取器 + 一個小型 SSE 解析器（`EventSource` 只支援沒有 body 的 GET，問題放網址裡不適合），先顯示引用，再逐字顯示回答，最後顯示首字延遲與總耗時。

[截圖：串流中的介面，引用已出現、回答逐字顯示中]

**結果**：從瀏覽器經轉發網址的串流查詢 {待填：是否不再於約 100 秒中斷、首字延遲與總耗時}。

**還沒解決的風險**：如果轉發限制的是請求的**總時間**而不是閒置時間，太長的回答仍會被切。那時的下一步是非同步查詢工作 + 輪詢，讓每個 HTTP 請求都很短。

---

## 4. 數據

所有數字都來自 [`docs/metrics.md`](../../metrics.md) 與開發日誌，環境標在旁邊。Codespaces 與 CI 都是 **CPU 數據，不代表 Mac 正式環境的效能**。

### Codespaces（CPU、`qwen2.5-coder:3b`、`nomic-embed-text`）

| 指標 | 數值 | 備註 |
| --- | --- | --- |
| 機型 | {待填} | `devcontainer.json` 要求 4 核心／16GB |
| 範例專案完整索引 | 20 個檔案 → 67 個片段，**35 秒** | CPU 產生 embedding |
| Prompt eval 速度 | **25.3 tokens/s** | {待填：量測方式，`ollama run --verbose` 或 API 回傳} |
| 生成（eval）速度 | **12.4 tokens/s** | 同上 |
| 一次查詢（非串流 `/query`，`curl` 經 nginx） | **約 55 秒**（實測 54.7 秒） | `TOP_K=4` |
| 瀏覽器經連接埠轉發（非串流） | 約 100 秒後 504 | |
| 串流查詢：首字延遲／總耗時 | {待填}／{待填} | |
| 建立 codespace 到介面可以回答 | {待填} | 第一次啟動 |

怎麼讀 prompt eval 和 eval 這兩個數字：在 CPU 上，一次 RAG 查詢的時間大致是

```text
總時間 ≈ 檢索 + 提示詞 token 數 ÷ prompt eval 速度 + 回答 token 數 ÷ eval 速度
```

RAG 的提示詞裡塞了 `TOP_K` 段程式碼，通常比回答長得多，所以**首字延遲主要由 prompt eval 決定**，這也是把 `TOP_K` 從 8 降到 4 的原因。這次查詢的提示詞與回答 token 數：{待填}。

### CI（GitHub Actions runner，CPU，第一次執行、沒有快取）

| Job | 時間 |
| --- | --- |
| 後端單元測試 | 40 秒 |
| compose 設定檢查 | 5 秒 |
| 映像檔 build（backend／frontend） | 76 秒／45 秒 |
| 端到端冒煙測試（含安裝 Ollama、拉模型） | 2 分 41 秒 |
| 冒煙測試中的完整索引（20 檔／67 片段） | 21.54 秒 |
| 冒煙測試中的單次查詢（`qwen2.5-coder:0.5b`、`TOP_K=4`） | 8 秒 |

冒煙測試刻意用 0.5B 模型：它回答的是「流程能不能跑」，不是「回答好不好」，而 0.5B 約 0.4GB，下載和推論都快（ADR 0008）。embedding 維持正式環境的 `nomic-embed-text`，確保向量維度與前綴都被測到。

### 工程品質

| 項目 | 數值 |
| --- | --- |
| 後端單元測試 | 70 個通過，約 2 秒，不需網路 |
| Codespaces 上發現、單元測試抓不到的問題 | 本文三個坑（測試紀錄完整清單 {待填}） |

### Mac M2（尚未實測）

| 指標 | 數值 |
| --- | --- |
| 14B 生成速度（Metal） | {待填} tokens/s |
| 14B 平均查詢時間 | {待填} 秒 |
| 同一台 Mac，Docker 內 CPU vs 原生 Metal | {待填} |

---

## 5. 用 AI coding agent 開發的心得

這個專案的程式碼大部分是用 Claude Code 的雲端工作階段寫的。

### 雲端工作階段做了什麼

- **初版建置**：後端、tree-sitter 切塊、增量索引、API、React 介面、Dockerfile、compose、腳本、README 與範例專案，加上用假物件的單元測試。它還在 sandbox 裡用真實 Qdrant 搭配假的 Ollama server 跑了一次端到端測試，抓到一個單元測試抓不到的 bug（`text-dense` 向量名稱，見 devlog 2026-10-30）。
- **把我的測試紀錄變成修正**：我把 Codespaces 的測試紀錄交給它，它產出可設定的逾時、清楚的 504 訊息、GitHub Actions CI（含真實 Ollama 的冒煙測試）、串流回應、dev container 與 `doctor.sh`，每個決策都寫成 ADR。
- **自我驗證**：例如串流的緩衝問題，它是先故意用有問題的 nginx 設定讓測試失敗，確認測試真的抓得到，才把修正交出來。

### 我自己做了什麼

- **定架構限制**：Ollama 不放進 Docker、程式碼不離開本機、一個 compose 檔跑所有環境。這些是需求，不是 agent 能替我決定的。
- **在真實環境上跑**：雲端 sandbox 沒有 GPU、沒有真實模型，也不是 Codespaces。三個坑都是我在 Codespaces 上親手撞到、親手用 `curl` 一層一層查出來，再寫成測試紀錄交回去的。**agent 修得很快，但它看不到它沒跑過的環境。**
- **判斷推測對不對**：504 在 100 秒斷，而不是 300 秒，這個「數字對不上」的觀察是轉折點。
- **審查每個 PR**，並決定哪些數字可以寫進文件。沒量過的一律留 `{待填}`。

### 成本

Claude Code 的花費到目前約 **17 美元**（各工作階段拆分 {待填}；第一個建出初版的工作階段約 7 美元）。Codespaces 核心時數 {待填}，GitHub Actions 是公開 repo，使用 GitHub 提供的 runner。

心得一句話：**AI agent 把「寫程式」的成本壓得很低，但「在真實環境驗證」的成本沒有變。** 真正省時間的做法，是把驗證結果寫成具體的紀錄（現象、指令、錯誤訊息、數字），再交給 agent。

---

## 6. 結語與下一步

回頭看三個坑，共通點是：

1. **都不是程式邏輯的 bug。** 70 個單元測試全過，CI 也綠的，問題都出在網路拓撲、程序生命週期、代理逾時。
2. **都在 Mac 上不會發生。** Docker Desktop 幫你處理了 `host.docker.internal` 和 loopback 轉發，App 幫你自動啟動 Ollama，本機沒有連接埠轉發。換到 Linux 才全部浮上來。
3. **都靠同一個方法解決：從呼叫端的位置、一次只驗證一層。** 用 `curlimages/curl` 容器模擬後端容器的網路；用 `ss` 確認程序和監聽位址；在 codespace 內 `curl` 繞過轉發。每一步都排除一層，直到只剩一個可疑對象。

排查到最後，這些步驟都變成了 `scripts/doctor.sh` 與 CI 裡的檢查，下一次遇到同樣的問題，不用再靠記憶。

下一步：

- [ ] **Mac M2 實機測試**：量 14B 在 Metal 上的生成速度與查詢時間，並在同一台機器上比較 Docker 內 CPU 與原生 Metal，用數字支持 ADR 0002。
- [ ] **14B 模型對比**：用 `docs/evaluation/questions.md` 的 10 題，比較 3B 與 14B 的正確性、引用正確率，以及陷阱題（線上多人同步，範例專案根本沒有這個功能）會不會產生幻覺。
- [ ] 在 Codespaces 從瀏覽器實測串流查詢，確認不再於約 100 秒中斷，補上首字延遲。

原始碼、ADR 與開發日誌都在 repo 裡：{待填：repo 網址}

---

## 附錄 A：發文標題選項

1. 地端 LLM 部署踩坑紀錄：容器連不到 Ollama、504 卡在 100 秒，我怎麼一層一層找出來
2. 單元測試全過，Codespaces 上卻壞了三次：地端 RAG 部署除錯實錄
3. 不是 nginx 的錯：從 504 逾時追到 Codespaces 連接埠轉發的除錯過程

## 附錄 B：LinkedIn 摘要（約 150 字）

沒有 Mac，我先在 Codespaces 的 CPU 環境測試自己做的地端 RAG。單元測試全過，部署後卻壞了三次：容器連不到 Ollama、重開後 Ollama 沒啟動、查詢固定在約 100 秒回 504。我用 curl 一層一層繞過可疑的連線段，追到 Codespaces 連接埠轉發，改成串流解決。這篇記錄除錯過程，以及用 AI agent 開發時人該負責的事。

## 發布前檢查

- [ ] 所有路徑、符號與截圖都來自 `examples/sample-game-frontend/` 或本 repo。
- [ ] 所有數字都對照過 `docs/metrics.md`，並註明環境；35 秒索引、25.3／12.4 tokens/s、約 17 美元同步補進 `metrics.md`。
- [ ] 確認「第一輪：懷疑 nginx」中 60 秒／900 秒的敘述（見文中待確認）。
- [ ] 補上所有 `[截圖：…]` 與 `{待填}`。
- [ ] 轉貼後把連結補回 `article-series.md`。
