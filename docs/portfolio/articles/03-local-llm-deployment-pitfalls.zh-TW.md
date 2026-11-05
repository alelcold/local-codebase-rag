# 地端 LLM 部署踩坑紀錄：一層一層縮小範圍

> **狀態**：草稿，尚未發布。`[截圖：…]` 是建議放截圖的位置，`{待填}` 是還沒量到的數據。
> **語言**：繁體中文版。英文版見 [`03-local-llm-deployment-pitfalls.en.md`](03-local-llm-deployment-pitfalls.en.md)，兩篇內容對應，修改時請一起更新。
> **規劃**：[`../article-series.md`](../article-series.md) 第 3 篇。依據：[devlog 2026-11-01](../../devlog/2026-11-01.md)、[devlog 2026-11-01 Codespaces 環境建置](../../devlog/2026-11-01-codespace-setup.md)、[devlog 2026-11-02](../../devlog/2026-11-02.md)、[devlog 2026-11-03](../../devlog/2026-11-03.md)、[`metrics.md`](../../metrics.md)、ADR [0002](../../decisions/0002-ollama-outside-docker-on-mac.md)、[0006](../../decisions/0006-multi-environment-deployment.md)、[0007](../../decisions/0007-multi-environment-testing-strategy.md)、[0008](../../decisions/0008-ci-design.md)、[0009](../../decisions/0009-timeout-settings.md)、[0010](../../decisions/0010-streaming-responses.md)、[0011](../../decisions/0011-devcontainer-for-codespaces.md)。
> **隱私**：所有路徑、符號與問題都來自 `examples/sample-game-frontend/` 或本 repo。

## TL;DR

- 我做了一套地端的 codebase RAG：Ollama 跑在主機上，Qdrant、FastAPI + LlamaIndex 後端、React 前端跑在 Docker 裡。
- 手邊沒有 Mac，所以先在 GitHub Codespaces（Linux、只有 CPU）上測。踩到三個坑，每個都不是程式邏輯的 bug，而是**環境與網路**的問題，單元測試全部通過也抓不到。
- 三個坑的除錯方法都一樣：**從呼叫端的位置、一段一段驗證**，每次只排除一層。
- CPU 上跑 3B 模型，在 codespace 內用 `curl` 經 nginx 的單次非串流查詢是 54.7 秒（`top_k` 為 4）。最後的 504 是 Codespaces 的連接埠轉發在約 100 秒時切斷連線，調高我們自己的逾時沒有用；改成串流回應後，同一類查詢從瀏覽器經轉發網址完成了（首字延遲 30.4 秒、總耗時 43.8 秒、129 個 token）。這一次只有 43.8 秒，**還沒有驗證超過 100 秒的查詢**。
- 番外：第四個問題不在服務裡，而是 `git push` 被 Git LFS 的 hook 擋下（見「番外」）。

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

`devcontainer.json` 也把網路面的決定寫死：`hostRequirements` 要求 4 核心／16GB／32GB；只自動轉發 8080（前端），11434（Ollama）與 6333（Qdrant）設為 `ignore`，永遠不會被轉發，坑 1 的資安提醒因此不用靠人記得。`postCreateCommand` 用 `.env.codespaces` 建立 `.env`（`qwen2.5-coder:3b`、`TOP_K=4`、`LLM_NUM_CTX=8192`）。

結果：重建（或重新建立）codespace 之後，`scripts/doctor.sh` 11 項全部通過，從瀏覽器問得了第一批問題，不需要輸入任何指令（devlog 2026-11-02）。從建立 codespace 到介面可以回答的時間：{待填}。**停止再啟動後 Ollama 會不會自己回來，也還沒實測**（devlog 2026-11-02 的待辦），所以「坑 2 已解決」目前只有設計上的依據。

`scripts/doctor.sh` 是把這兩個坑的排查步驟直接寫成腳本：Ollama 已安裝 → 程序在跑 → API 有回應 → 監聽位址 → 模型 → Docker → 容器 → **容器連得到 Ollama** → 後端 `/health` → nginx 代理 → Qdrant 有索引（第 12 項是後來加的 Git LFS 檢查，見「番外」）。每一項失敗都印出修正指令，依賴它的後續檢查會略過，直接告訴你斷在哪一層。

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

#### 第一輪：先檢查我們自己控制的每一段

**現象**：從介面提問，等了一陣子後顯示 504 Gateway Timeout。

```text
{待填：介面顯示的錯誤訊息}
```

[截圖：介面顯示 504 Gateway Timeout]

**推測**：504 是代理回的，最近的代理是 nginx，所以先懷疑我們自己設的逾時太短。CPU 上跑 3B 模型，一次查詢推算要 1.5～2 分鐘（`top_k=8`，推算值，不是 10 次查詢的實測平均），超過任何偏短的預設值都很合理。

**驗證**：先把每一段的實際設定列出來（ADR 0009）：

| 連線段 | 修改前的設定 | 問題 |
| --- | --- | --- |
| nginx `proxy_read_timeout`／`proxy_send_timeout` | 寫死 900 秒 | 不重新 build 映像檔就改不了 |
| 後端 → Ollama 生成（`LLM_REQUEST_TIMEOUT`） | 600 秒 | 逾時時回傳籠統的 502 與原始例外名稱 |
| 後端 → Ollama embedding | **沒有逾時**（ollama client 預設永遠等） | 卡住時請求會掛著，直到別的連線段放棄 |
| 介面 | 一句固定的「可能需要 30 秒以上」 | 看不到等了多久，失敗時只顯示 `504 Gateway Timeout` |

nginx 是 900 秒、LLM 是 600 秒，而 504 在約 1.5～2 分鐘就出現，這兩段都不可能是放棄的那一個。這個推測在驗證時就被推翻了，剩下的嫌疑是 nginx **前面**的東西。

**仍然做的修正**：這張表本身有三個缺口（寫死、沒逾時、訊息不清楚），所以還是把逾時都改成可在 `.env` 設定，預設 300 秒（ADR 0009）：

| 變數 | 連線段 | 預設 |
| --- | --- | --- |
| `PROXY_READ_TIMEOUT`、`PROXY_SEND_TIMEOUT` | nginx → 後端 | 300 |
| `LLM_REQUEST_TIMEOUT` | 後端 → Ollama（生成） | 300 |
| `EMBED_REQUEST_TIMEOUT` | 後端 → Ollama（embedding，原本**完全沒有逾時**） | 300 |

300 秒大約是推算查詢時間（1.5～2 分鐘）的 2～3 倍。nginx 透過官方映像的 template 機制（`/etc/nginx/templates/*.template` + `envsubst`）讀取設定，改 `.env` 後 `docker compose up -d` 就生效，不用重新 build。

順便處理了兩件事：後端遇到 Ollama 逾時時回傳 504，並寫出是哪個階段、要調哪個變數（以前是籠統的 502）；介面等待時顯示「生成中」與已等待秒數。

**結果**：這一輪的修正本身沒有讓 504 消失。斷線時間點在**約 100 秒**，跟 300、600、900 秒都對不上。

#### 第二輪：斷在 100 秒，代表不是我們設的任何一個值

這是整個排查的轉折點。我們這邊的逾時是 300 秒（修改前是 900 與 600 秒），沒有任何一個是 100 秒。斷線時間和自己的設定對不上，就表示**放棄的是另一段連線**。

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

（瀏覽器那次為什麼比 54.7 秒久、久到撞上 100 秒——模型還沒載入、`top_k` 不同（`curl` 那次是 4，瀏覽器那次的值沒有記錄），或是排在另一個請求後面——目前還沒確認，{待填}。）

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

**結果**：在 Codespaces 從瀏覽器經轉發網址問「玩家受傷後的無敵時間在哪裡設定？」（`qwen2.5-coder:3b`、`TOP_K=4`、模型載入後的第一次查詢），串流正常完成：**首字延遲 30.4 秒、總耗時 43.8 秒、129 個 token**，沒有 504。

| 次數 | 首字延遲 | 總耗時 | 備註 |
| --- | --- | --- | --- |
| 第一次（模型載入後第一次查詢） | 30.4 秒 | 43.8 秒（129 個 token） | 首字前的 30.4 秒是模型載入加提示詞處理 |
| 同一題再問一次 | 0.8 秒 | 14.3 秒（134 個 token） | Ollama 重用了快取的提示詞，**不是**一般延遲；兩次的生成速度都約 10 tokens/s |

這個結果要小心解讀：43.8 秒**低於**非串流版本被切斷的約 100 秒，所以它證明的是「串流查詢在這個轉發網址上走得通」，**不是**「轉發不再限制長查詢」。第二次的 0.8 秒是快取造成的，也不能當成延遲數字。更長的查詢（超過 100 秒）還沒有測，devlog 2026-11-02 的待辦清單裡仍是未勾選。

**還沒解決的風險**：如果轉發限制的是請求的**總時間**而不是閒置時間，太長的回答仍會被切。那時的下一步是非同步查詢工作 + 輪詢，讓每個 HTTP 請求都很短。

---

### 番外：`git push` 被 Git LFS 的 hook 擋下

這個問題和服務無關，但同樣是「Mac 上不會遇到」的環境差異，而且是在 dev container 自動化之後才浮現。

**現象**：在 codespace 裡 `git push`，什麼都還沒送出就被拒絕，但這個 repo 根本沒用 Git LFS（沒有 `.gitattributes`、沒有 LFS 檔案）。

```text
This repository is configured for Git LFS but 'git-lfs' was not found on your path. If you no longer wish to use Git LFS, remove this hook by deleting the 'pre-push' file in the hooks directory (set by 'core.hookspath'; usually '.git/hooks').
```

**推測**：訊息說 hook 在、`git-lfs` 執行檔不在。hook 是誰放的、為什麼放，從訊息看不出來。

**驗證**：clone 的 `.git/hooks/` 裡有 Git LFS 的 hook（`pre-push` 等，會呼叫 `git lfs …`），但 dev container 的基底映像（`mcr.microsoft.com/devcontainers/base:ubuntu-24.04`）沒有 `git-lfs`，`post-create.sh` 也沒有安裝。hook 在缺少 `git-lfs` 時會以錯誤結束，而 `pre-push` hook 失敗就會中止 push。

**解法**：
- `.devcontainer/post-create.sh` 把 `git-lfs` 跟 `jq`、`zstd`、`iproute2` 一起安裝，再執行 `git lfs install --skip-repo`。不加 `--skip-repo` 的 `git lfs install` 在 hook 已存在時會以 2 結束（`Hook already exists: pre-push … run git lfs update --manual`），在 `set -e` 的腳本裡會讓整個 `postCreateCommand` 中斷；`--skip-repo` 只設定全域的 filter。
- `scripts/doctor.sh` 新增第 12 項檢查：有 LFS hook 但沒有 `git-lfs` 時失敗，並印出安裝指令（因為這個 repo 沒有 LFS 檔案，也列出直接刪除 hook 的替代做法）。這一項與服務無關，所以排在最後。
- 已經存在的 codespace：`sudo apt-get update && sudo apt-get install -y git-lfs`，或重建容器。

教訓和前三個坑一樣：自動化環境的清單（這裡是 `apt-get install` 的套件）只會包含你踩過的坑，每換一種動作（這次是 push）就可能冒出新的缺口。

---

## 4. 數據

所有數字都來自 [`docs/metrics.md`](../../metrics.md) 與開發日誌，環境標在旁邊。Codespaces 與 CI 都是 **CPU 數據，不代表 Mac 正式環境的效能**。

### Codespaces（CPU、`qwen2.5-coder:3b`、`nomic-embed-text`）

| 指標 | 數值 | 備註 |
| --- | --- | --- |
| 機型 | 4 核心（devlog 2026-11-03） | `devcontainer.json` 的 `hostRequirements` 要求 4 核心／16GB；實際機型名稱 {待填} |
| 範例專案完整索引 | 20 個檔案 → 67 個片段，**41.9 秒**（升級後第一次全量重建）；18.8～20.7 秒（切換 `CHUNK_METADATA` 後的全量重建） | CPU 產生 embedding；2026-11-01 第一次索引的耗時沒有記錄，{待填} |
| Prompt eval 速度 | **25.3 tokens/s** | `ollama run --verbose`，單次，Codespaces 4 核心（CPU），`qwen2.5-coder:3b`。同一次：生成（eval）12.4 tokens/s，模型載入約 3.5 秒（metrics §3） |
| 生成（eval）速度 | **約 10 tokens/s** | 兩次手動串流查詢（metrics §3），不是獨立量測 |
| 一次查詢（非串流 `/query`，`curl` 經 nginx） | **54.7 秒** | 單次查詢，`top_k` 為 4 |
| 瀏覽器經連接埠轉發（非串流） | 約 100 秒後 504 | |
| 串流查詢（瀏覽器經轉發網址）：首字延遲／總耗時 | **30.4 秒／43.8 秒**（129 個 token） | `TOP_K=4`，模型載入後第一次查詢；同一題再問：0.8 秒／14.3 秒，是提示詞快取 |
| `scripts/evaluate.py` 的 10 題平均（`TOP_K=4`） | 首字延遲 13.0 秒、總耗時 20.9 秒（基準線 A 組） | 10 個不同問題、先暖機，主要題組；見 metrics §4a 與第 6 篇 |
| 建立 codespace 到介面可以回答 | {待填} | 第一次啟動 |

怎麼讀 prompt eval 和 eval 這兩個數字：在 CPU 上，一次 RAG 查詢的時間大致是

```text
總時間 ≈ 檢索 + 提示詞 token 數 ÷ prompt eval 速度 + 回答 token 數 ÷ eval 速度
```

RAG 的提示詞裡塞了 `TOP_K` 段程式碼，通常比回答長得多，所以**首字延遲主要由 prompt eval 決定**，這也是把 `TOP_K` 從 8 降到 4 的原因。串流那次查詢的回答是 129 個 token：以約 10 tokens/s 計，生成約 13 秒，與總耗時 43.8 秒減首字延遲 30.4 秒 = 13.4 秒吻合（Ollama 自己的計數後來量到生成速度是 12.4 tokens/s，所以實際速度稍快一點）。其餘 30.4 秒是模型載入加提示詞處理；在 `ollama run --verbose` 那次，載入只花約 3.5 秒，所以大部分是以 25.3 tokens/s 處理提示詞。提示詞的 token 數：{待填}。

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
| 後端單元測試 | 加入逾時處理後 56 個、加入串流後 70 個（約 2 秒，不需網路）；本文定稿時 main 上是 170 個（約 7 秒，metrics §6） |
| Codespaces 上發現、單元測試抓不到的問題 | 本文三個坑加上 Git LFS 番外（測試紀錄完整清單 {待填}） |

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

Claude Code 的花費：第一個建出初版的工作階段約 **7 美元**（metrics §1）；PR #3 的工作階段約 **10 美元**，所有工作階段合計約 **100 美元**，額度就此用完（metrics §1；其餘約 83 美元沒有逐項列出）。Codespaces 核心時數 {待填}，GitHub Actions 是公開 repo，使用 GitHub 提供的 runner。

心得一句話：**AI agent 把「寫程式」的成本壓得很低，但「在真實環境驗證」的成本沒有變。** 真正省時間的做法，是把驗證結果寫成具體的紀錄（現象、指令、錯誤訊息、數字），再交給 agent。

---

## 6. 結語與下一步

回頭看三個坑，共通點是：

1. **都不是程式邏輯的 bug。** 單元測試全過（當時 70 個），CI 也是綠的，問題都出在網路拓撲、程序生命週期、代理逾時。
2. **都在 Mac 上不會發生。** Docker Desktop 幫你處理了 `host.docker.internal` 和 loopback 轉發，App 幫你自動啟動 Ollama，本機沒有連接埠轉發。換到 Linux 才全部浮上來。
3. **都靠同一個方法解決：從呼叫端的位置、一次只驗證一層。** 用 `curlimages/curl` 容器模擬後端容器的網路；用 `ss` 確認程序和監聽位址；在 codespace 內 `curl` 繞過轉發。每一步都排除一層，直到只剩一個可疑對象。

排查到最後，這些步驟都變成了 `scripts/doctor.sh` 與 CI 裡的檢查，下一次遇到同樣的問題，不用再靠記憶。

下一步：

- [ ] **Mac M2 實機測試**：量 14B 在 Metal 上的生成速度與查詢時間，並在同一台機器上比較 Docker 內 CPU 與原生 Metal，用數字支持 ADR 0002。
- [ ] **14B 模型對比**：用 `docs/evaluation/questions.md` 的 10 題，比較 3B 與 14B 的正確性、引用正確率，以及陷阱題（線上多人同步，範例專案根本沒有這個功能）會不會產生幻覺。
- [ ] 在 Codespaces 從瀏覽器實測**超過 100 秒**的串流查詢，確認不會被轉發切斷（43.8 秒的那次不足以證明）。
- [ ] 停止再啟動 codespace，確認 Ollama 與服務自己回來（`./scripts/doctor.sh`），並記錄從建立到可回答的時間。

原始碼、ADR 與開發日誌都在 repo 裡：{待填：repo 網址}

---

## 附錄 A：發文標題選項

1. 地端 LLM 部署踩坑紀錄：容器連不到 Ollama、504 卡在 100 秒，我怎麼一層一層找出來
2. 單元測試全過，Codespaces 上卻壞了三次：地端 RAG 部署除錯實錄
3. 不是 nginx 的錯：從 504 逾時追到 Codespaces 連接埠轉發的除錯過程

## 附錄 B：LinkedIn 摘要（150 字內）

沒有 Mac，我先在 Codespaces 的 CPU 環境測試我的地端 RAG。單元測試全過，部署後卻壞了三次：容器連不到 Ollama、重開後 Ollama 沒啟動、查詢在約 100 秒回 504。我用 curl 逐層排除，追到連接埠轉發，改串流後查詢得以完成。附 AI 協作心得。

## 發布前檢查

- [ ] 所有路徑、符號與截圖都來自 `examples/sample-game-frontend/` 或本 repo。
- [ ] 所有數字都對照過 `docs/metrics.md`、devlog 或評估報告，並註明環境。
- [ ] 每一次 Claude Code 工作階段的花費與總計補進 `metrics.md` §1。
- [ ] 補上所有 `[截圖：…]` 與 `{待填}`。
- [ ] 內容有修改時，同步更新英文版。
- [ ] 轉貼後把連結補回 `article-series.md`。
