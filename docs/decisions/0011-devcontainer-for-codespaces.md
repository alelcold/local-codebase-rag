# 0011. Dev container that starts the whole stack in Codespaces

- **Status**: Accepted
- **Date**: 2026-11-02
- **Related**: [0006](0006-multi-environment-deployment.md), [0007](0007-multi-environment-testing-strategy.md), [devlog 2026-11-01 Codespaces setup](../devlog/2026-11-01-codespace-setup.md), [devlog 2026-11-02](../devlog/2026-11-02.md), `.devcontainer/`, `docker-compose.codespaces.yml`, `.env.codespaces`, `scripts/doctor.sh`

> English first; 繁體中文版本在下方.

## Context

Testing on Codespaces needed about ten manual steps (test log sections 3.2–3.5): install Ollama, start it in the background on `0.0.0.0`, wait, pull models, edit `.env`, write a `docker-compose.override.yml` with `host-gateway`, start Compose, index. Most of the pitfalls in the test log (#1–#7) came from these steps: a server in the foreground, a log overwritten with `>`, `curl -s` hiding errors, Ollama on `127.0.0.1`, testing from the wrong side of the Docker bridge, and **Ollama gone after the codespace was stopped and started again** (#7), because a stopped codespace keeps files but not processes.

## Decision

1. **`.devcontainer/devcontainer.json`**: Ubuntu base image, `docker-in-docker`, Python 3.12 and Node 22 features; `hostRequirements` 4 CPUs / 16 GB / 32 GB; port 8080 forwarded and labelled as the frontend; 11434 (Ollama) and 6333 (Qdrant) set to `ignore`, so they are never forwarded.
2. **`postCreateCommand`** (once): install Ollama, `jq`, `zstd`; create `.env` from the new **`.env.codespaces`** if there is no `.env` (`qwen2.5-coder:3b`, `TOP_K=4`, `LLM_NUM_CTX=8192`, the sample project, nginx timeout a little above the backend's).
3. **`postStartCommand`** (**every** start, which fixes #7): start Ollama with `OLLAMA_HOST=0.0.0.0` in the background with `>>` to `.logs/ollama.log` unless it already answers, wait until it is ready, pull missing models, `docker compose up -d --build`, index if Qdrant is empty, run `scripts/doctor.sh`, print the URL.
4. **`docker-compose.codespaces.yml`** replaces the hand-written override. It is applied through **`COMPOSE_FILE`**, set in `containerEnv` with absolute paths, so every `docker compose` command in the codespace uses it, from any directory. Mac and EC2 never set `COMPOSE_FILE`, so their flow is unchanged. The CI `compose-config` job already validates every `docker-compose.*.yml` on top of the base file.
5. **`OLLAMA_MODELS`** points inside the workspace folder (`.ollama/`, git-ignored), so a container rebuild does not download the models again.
6. **`scripts/doctor.sh`** checks, in order: Ollama installed → process running → API answers → listening address → models → Docker → containers → container can reach Ollama → backend `/health` → frontend and nginx proxy → Qdrant has an index. Each failure prints the command that fixes it; checks that depend on a failed one are skipped. It also works on the Mac (bash 3.2, `lsof` instead of `ss`, `python3` instead of `jq`, and `127.0.0.1` is accepted on macOS).

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Keep the README steps | Nothing new to maintain | Ten manual steps, the same pitfalls every time, and steps to repeat after every restart | The reason for this change |
| Ollama as a Compose service in Codespaces | One `docker compose up` | A different topology from the Mac and CI (ADR 0002, 0006): Codespaces would no longer test the `host.docker.internal` path that production uses | Codespaces exists to test the production topology |
| Docker Compose–based dev container (`dockerComposeFile`) | Services described in one place | The dev container itself becomes a Compose service; Ollama still has to run somewhere; more complex for the same result | More complex for no gain |
| Override by renaming to `docker-compose.override.yml` (loaded automatically) | No environment variable | That file name is git-ignored for machine-specific use; committing it would also apply on Mac and EC2 | Would affect the other environments |
| Start Ollama with `nohup` in `postCreateCommand` only | Simpler | Processes do not survive a stop/start (#7) | Exactly the bug to fix |

## Consequences

- **Positive**: Opening a codespace gives a working UI on port 8080 without typing a command. Restarts work. `doctor.sh` turns the debugging steps from the test log into one command that also helps on the Mac.
- **Negative / trade-offs**:
  - The first start takes several minutes (Ollama install, about 2 GB of models, image builds). {待填：第一次建立 codespace 到可以查詢的時間}
  - `postStartCommand` runs `docker compose up -d --build` on every start; it is quick when nothing changed but not free.
  - 4-core machines use more Codespaces core-hours than 2-core ones.
  - The Ollama install script is downloaded at creation time, so its version is not pinned.
  - `COMPOSE_FILE` with absolute paths ties every `docker compose` call in the codespace to this project.
- **Follow-ups**: Measure creation and restart times. Consider a prebuild to make creation faster.

---

# 0011. 在 Codespaces 自動啟動整套服務的 dev container

- **狀態**：已接受
- **日期**：2026-11-02
- **相關**：[0006](0006-multi-environment-deployment.md)、[0007](0007-multi-environment-testing-strategy.md)、[devlog 2026-11-01 Codespaces 環境建置](../devlog/2026-11-01-codespace-setup.md)、[devlog 2026-11-02](../devlog/2026-11-02.md)、`.devcontainer/`、`docker-compose.codespaces.yml`、`.env.codespaces`、`scripts/doctor.sh`

## 背景

在 Codespaces 測試需要大約十個手動步驟（測試紀錄 3.2～3.5）：安裝 Ollama、以 `0.0.0.0` 在背景啟動、等待、拉模型、修改 `.env`、手寫含 `host-gateway` 的 `docker-compose.override.yml`、啟動 Compose、建立索引。測試紀錄中大部分的踩坑（#1～#7）都來自這些步驟：伺服器在前景執行、log 被 `>` 蓋掉、`curl -s` 把錯誤藏起來、Ollama 只聽 `127.0.0.1`、在 Docker bridge 錯的那一側測試，以及**停止後再開啟 codespace，Ollama 就不見了**（#7）：停止的 codespace 會保留檔案，但不會保留執行中的程序。

## 決策

1. **`.devcontainer/devcontainer.json`**：Ubuntu 基底映像，`docker-in-docker`、Python 3.12 與 Node 22 feature；`hostRequirements` 4 核心／16GB／32GB；自動轉發 8080 並標示為前端；11434（Ollama）與 6333（Qdrant）設為 `ignore`，永遠不會被轉發。
2. **`postCreateCommand`**（只執行一次）：安裝 Ollama、`jq`、`zstd`；沒有 `.env` 時，從新的 **`.env.codespaces`** 建立（`qwen2.5-coder:3b`、`TOP_K=4`、`LLM_NUM_CTX=8192`、範例專案，nginx 逾時比後端稍長）。
3. **`postStartCommand`**（**每次**啟動都會執行，解決 #7）：Ollama 還沒回應時，以 `OLLAMA_HOST=0.0.0.0` 在背景啟動，用 `>>` 寫入 `.logs/ollama.log`；等待就緒、拉取缺少的模型、`docker compose up -d --build`、Qdrant 沒有索引時建立索引、執行 `scripts/doctor.sh`，最後印出網址。
4. **`docker-compose.codespaces.yml`** 取代手寫的 override，透過 **`COMPOSE_FILE`** 套用：在 `containerEnv` 中以絕對路徑設定，codespace 裡任何目錄下的 `docker compose` 都會用到它。Mac 與 EC2 不會設定 `COMPOSE_FILE`，流程不變。CI 的 `compose-config` job 本來就會把每個 `docker-compose.*.yml` 疊在主檔上驗證。
5. **`OLLAMA_MODELS`** 指向工作區資料夾內（`.ollama/`，已加入 git ignore），重建容器時不用重新下載模型。
6. **`scripts/doctor.sh`** 依序檢查：Ollama 已安裝 → 程序在執行 → API 有回應 → 監聽位址 → 模型 → Docker → 容器 → 容器連得到 Ollama → 後端 `/health` → 前端與 nginx 代理 → Qdrant 已有索引。每個失敗項目都會印出修正指令；依賴失敗項目的檢查會略過。在 Mac 上也能用（bash 3.2，用 `lsof` 取代 `ss`、`python3` 取代 `jq`，macOS 上接受 `127.0.0.1`）。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 維持 README 的手動步驟 | 不用維護新東西 | 十個手動步驟、每次都踩一樣的坑，每次重開都要重做 | 正是這次要解決的問題 |
| 在 Codespaces 把 Ollama 放進 Compose | 一個 `docker compose up` 就好 | 拓撲和 Mac、CI 不同（ADR 0002、0006）：Codespaces 就測不到正式環境使用的 `host.docker.internal` 路徑 | Codespaces 的目的就是測試正式環境的拓撲 |
| 以 Docker Compose 為基礎的 dev container（`dockerComposeFile`） | 服務都描述在同一處 | dev container 本身變成一個 Compose 服務；Ollama 仍要找地方跑；同樣的結果卻更複雜 | 更複雜卻沒有好處 |
| 改名成 `docker-compose.override.yml`（會自動載入） | 不需要環境變數 | 這個檔名已被 git ignore，保留給各機器自己的設定；提交上去會連 Mac 與 EC2 一起套用 | 會影響其他環境 |
| 只在 `postCreateCommand` 用 `nohup` 啟動 Ollama | 比較簡單 | 停止／啟動後程序就不見了（#7） | 正是要修的問題 |

## 後果

- **正面**：開啟 codespace 後，不用輸入任何指令，8080 埠就有可用的介面。重開也能正常運作。`doctor.sh` 把測試紀錄的排查步驟變成一個指令，在 Mac 上也有幫助。
- **負面／取捨**：
  - 第一次啟動需要好幾分鐘（安裝 Ollama、約 2GB 的模型、build 映像檔）。{待填：第一次建立 codespace 到可以查詢的時間}
  - `postStartCommand` 每次啟動都會執行 `docker compose up -d --build`；沒有變更時很快，但不是零成本。
  - 4 核心機型消耗的 Codespaces 核心時數比 2 核心多。
  - Ollama 安裝腳本在建立時才下載，版本沒有固定。
  - `COMPOSE_FILE` 使用絕對路徑，codespace 裡所有 `docker compose` 指令都會指向這個專案。
- **後續工作**：量測建立與重開所需時間。考慮使用 prebuild 加快建立。
