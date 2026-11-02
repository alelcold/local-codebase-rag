# 0008. CI design: split jobs, and a smoke test with the smallest model

- **Status**: Accepted
- **Date**: 2026-11-02
- **Related**: [0006](0006-multi-environment-deployment.md), [0007](0007-multi-environment-testing-strategy.md), `.github/workflows/ci.yml`, `docker-compose.ci.yml`, `scripts/smoke-test.sh`

> English first; 繁體中文版本在下方.

## Context

The repo had no CI. Tests were run by hand, and the Codespaces run found problems that unit tests cannot find (ADR 0007). We want CI that:

- gives fast feedback on every push;
- catches broken compose files and Dockerfiles;
- proves, before merging into `main`, that the **real** pipeline works: containers reach Ollama on the host, documents are embedded and stored in Qdrant, and a query through the nginx proxy returns an answer with file citations.

Constraints: GitHub-hosted runners have no GPU, about 4 vCPUs and 16 GB RAM. Every model has to be downloaded or restored from cache on every run. Docker Hub can rate-limit anonymous pulls.

## Decision

One workflow (`.github/workflows/ci.yml`) with four jobs:

| Job | Runs on | What it does | Typical time |
| --- | --- | --- | --- |
| `backend-tests` | every push and PR | `pytest` with fakes (no Ollama, in-memory Qdrant) | about 1 minute, mostly installing packages |
| `compose-config` | every push and PR | `docker compose config -q` for the base file, and for the base file combined with every `docker-compose.*.yml` override | seconds |
| `docker-build` | every push and PR | Builds the `backend` and `frontend` images (matrix), using the GitHub Actions build cache | {待填} |
| `e2e-smoke` | PRs into `main` only | Installs Ollama on the runner, starts it with `OLLAMA_HOST=0.0.0.0`, pulls `qwen2.5-coder:0.5b` and `nomic-embed-text` (cached), starts compose with `docker-compose.ci.yml`, then runs `scripts/smoke-test.sh` (health → index the sample project → query through `/api` → check citations). On failure it prints `docker compose logs` for every service and the Ollama server log. | {待填} |

### Why the smoke test uses the smallest model

- The smoke test answers "does the pipeline work?", not "are the answers good?" (ADR 0007). Any model that speaks Ollama's API exercises the same code path.
- `qwen2.5-coder:0.5b` is about 0.4 GB versus 1.9 GB (3B) or 9 GB (14B). It downloads and caches quickly and answers in seconds on a CPU runner. A 14B model would not fit comfortably in the runner's memory alongside Docker, and each answer would take minutes.
- The embedding model stays `nomic-embed-text`, the production embedding model, so the real embedding dimensions, the nomic prefixes and the derived collection name are all tested.
- **What it checks**: the hard checks are deterministic. The response must have a non-empty answer and at least one source with a real file path and a valid line range. Whether the answer text itself contains `[n]` markers is only a **warning**, because a 0.5B model does not reliably follow the citation format. Failing CI on that would make the test flaky.

### Why several jobs instead of one

- **Fast feedback**: unit tests and config checks finish in about a minute and run in parallel. A typo in compose does not wait behind a model download.
- **Clear failure signal**: the failed job's name says what broke (logic, config, image or integration).
- **Cost control**: the slow job runs only where it matters (PRs into `main`), and only after `backend-tests` and `compose-config` pass (`needs`), so a broken unit test never spends runner minutes on model downloads.
- **Independent caching**: pip, Docker layers (per image) and Ollama models each have their own cache.

### Ollama on the runner, not in compose

This is the same topology as the Mac and Codespaces (ADR 0006): Ollama runs natively on the host, and containers reach it through `host.docker.internal`. The CI override adds `extra_hosts: host.docker.internal:host-gateway` to the backend. The base file already has that line, but repeating it means CI still works if the base file changes, and it documents what CI depends on. Running Ollama in compose only for CI would test a topology nobody runs.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| One big job | Simpler YAML | Slow feedback; one failure hides the others; model download on every push | Slower and noisier |
| Smoke test on every push | Catches integration bugs earlier | Several minutes and a model download per push, on every branch | Cost; PRs into `main` are the gate that matters |
| Smoke test with 3B or 14B | Closer to production | Much slower; 14B may not fit; still no GPU, so the numbers are not representative anyway | No extra signal for a pass/fail check |
| Fake Ollama server in CI (as in the 2026-10-30 sandbox) | Fast, no download | Does not test the real Ollama API, model names, embedding dimensions or nomic prefixes | Too far from reality for the final gate |
| Ollama as a compose service in CI | No runner setup | Different topology from production (ADR 0006); `host.docker.internal` would go untested | Consistency |
| Answer-quality checks (LLM-as-judge) in CI | Tracks quality automatically | Needs a strong model; noisy with tiny models | Belongs to manual evaluation for now (ADR 0007) |

## Consequences

- **Positive**: Every push gets unit, config and image checks. Every PR into `main` proves the real pipeline end to end on Linux, the platform where networking problems appear. Failures include logs from every service.
- **Negative / trade-offs**:
  - A green CI does not mean good answers.
  - The smoke test depends on ollama.com, the model registry and Docker Hub being reachable from the runner. A network problem can fail it without a code bug, so re-run it before investigating.
  - The Ollama version is not pinned (the install script installs the latest release), so a new Ollama release can change behavior. Pin it with `OLLAMA_VERSION` if this becomes a problem.
  - CI uses `TOP_K=4` and `LLM_NUM_CTX=4096` to stay fast, which differs from the production defaults.
- **Follow-ups**: Record the measured job times in `docs/metrics.md`. Consider pinning the Ollama version. Add a `docker-compose.gpu.yml` override if GPU instances ever need compose changes; `compose-config` validates any `docker-compose.*.yml` automatically.

---

# 0008. CI 設計：拆成多個 job，冒煙測試使用最小模型

- **狀態**：已接受
- **日期**：2026-11-02
- **相關**：[0006](0006-multi-environment-deployment.md)、[0007](0007-multi-environment-testing-strategy.md)、`.github/workflows/ci.yml`、`docker-compose.ci.yml`、`scripts/smoke-test.sh`

## 背景

repo 原本沒有 CI，測試都靠手動執行；而 Codespaces 的測試發現了單元測試抓不到的問題（ADR 0007）。我們希望 CI 能夠：

- 每次 push 都很快得到回饋；
- 抓出壞掉的 compose 設定與 Dockerfile；
- 在合併進 `main` 之前，證明**真實**流程可以跑通：容器連得到主機上的 Ollama、文件會被向量化並存進 Qdrant，而且透過 nginx 代理送出的查詢會回傳附有檔案引用的回答。

限制：GitHub 提供的 runner 沒有 GPU，大約 4 vCPU、16GB RAM。每次執行都要下載模型，或從快取還原。Docker Hub 可能會限制匿名拉取。

## 決策

一個 workflow（`.github/workflows/ci.yml`），分成四個 job：

| Job | 執行時機 | 內容 | 大約時間 |
| --- | --- | --- | --- |
| `backend-tests` | 每次 push 與 PR | 用假物件跑 `pytest`（不需 Ollama，Qdrant 用記憶體模式） | 約 1 分鐘，大部分是安裝套件 |
| `compose-config` | 每次 push 與 PR | 對主檔，以及主檔搭配每個 `docker-compose.*.yml` override，執行 `docker compose config -q` | 幾秒 |
| `docker-build` | 每次 push 與 PR | 以 matrix build `backend` 與 `frontend` 映像檔，使用 GitHub Actions 的 build 快取 | {待填} |
| `e2e-smoke` | 只在對 `main` 的 PR | 在 runner 上安裝 Ollama 並以 `OLLAMA_HOST=0.0.0.0` 啟動，拉取 `qwen2.5-coder:0.5b` 與 `nomic-embed-text`（有快取），搭配 `docker-compose.ci.yml` 啟動 compose，再執行 `scripts/smoke-test.sh`（健康檢查 → 索引範例專案 → 透過 `/api` 查詢 → 檢查引用）。失敗時輸出每個服務的 `docker compose logs` 與 Ollama 伺服器的 log。 | {待填} |

### 為什麼冒煙測試用最小模型

- 冒煙測試回答的是「流程能不能跑？」，不是「回答好不好？」（ADR 0007）。任何支援 Ollama API 的模型，走的都是同一條程式路徑。
- `qwen2.5-coder:0.5b` 約 0.4GB，3B 約 1.9GB，14B 約 9GB。0.5B 下載與快取都快，在 CPU runner 上幾秒內就能回答。14B 加上 Docker 很難塞進 runner 的記憶體，每次回答也要好幾分鐘。
- Embedding 模型維持正式環境使用的 `nomic-embed-text`，因此真實的向量維度、nomic 前綴與自動產生的 collection 名稱都會被測到。
- **檢查內容**：硬性檢查都是確定性的。回應必須有非空的回答，而且至少有一個來源，帶有真實的檔案路徑與合理的行號範圍。回答文字本身有沒有 `[n]` 標記只會發出**警告**，因為 0.5B 模型不一定會遵守引用格式，把它當成失敗條件會讓測試時好時壞。

### 為什麼拆成多個 job，而不是一個

- **回饋快**：單元測試與設定檢查大約一分鐘內完成，而且平行執行。compose 打錯字，不必等模型下載完才知道。
- **失敗訊號清楚**：從失敗的 job 名稱就知道是哪裡壞了（邏輯、設定、映像檔還是整合）。
- **控制成本**：慢的 job 只在真正重要的地方執行（對 `main` 的 PR），而且要等 `backend-tests` 與 `compose-config` 通過才會開始（`needs`），單元測試失敗時就不會浪費 runner 時間下載模型。
- **快取各自獨立**：pip、Docker layer（每個映像檔各一份）與 Ollama 模型各有自己的快取。

### Ollama 跑在 runner 上，不放進 compose

這和 Mac、Codespaces 的架構相同（ADR 0006）：Ollama 在主機上原生執行，容器透過 `host.docker.internal` 呼叫。CI override 為後端加上 `extra_hosts: host.docker.internal:host-gateway`。主檔其實已經有這一行，但在這裡再寫一次，主檔之後就算修改，CI 也能正常運作，同時也記錄了 CI 依賴這個設定。如果只為了 CI 把 Ollama 放進 compose，測到的會是一個沒有人實際使用的架構。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 全部放在一個 job | YAML 比較簡單 | 回饋慢；一個失敗會蓋掉其他失敗；每次 push 都要下載模型 | 比較慢、訊號比較雜 |
| 每次 push 都跑冒煙測試 | 更早抓到整合問題 | 每個分支的每次 push 都要好幾分鐘，還要下載模型 | 成本；真正要把關的是對 `main` 的 PR |
| 冒煙測試用 3B 或 14B | 比較接近正式環境 | 慢很多；14B 可能塞不進記憶體；而且仍然沒有 GPU，數字一樣沒有代表性 | 對「能不能跑」的檢查沒有額外價值 |
| CI 用假的 Ollama 伺服器（像 2026-10-30 的 sandbox） | 快，不用下載 | 測不到真實的 Ollama API、模型名稱、向量維度與 nomic 前綴 | 作為最後一道關卡，離真實情況太遠 |
| CI 裡把 Ollama 當成 compose 服務 | runner 不用額外設定 | 和正式環境架構不同（ADR 0006）；`host.docker.internal` 會測不到 | 一致性 |
| 在 CI 檢查回答品質（LLM-as-judge） | 自動追蹤品質 | 需要強的模型；用極小模型評分雜訊很大 | 目前交給手動評估（ADR 0007） |

## 後果

- **正面**：每次 push 都會跑單元測試、設定檢查與映像檔 build。每個對 `main` 的 PR，都會在 Linux（最容易出現網路問題的平台）上完整證明真實流程能跑通。失敗時會附上每個服務的 log。
- **負面／取捨**：
  - CI 通過不代表回答品質好。
  - 冒煙測試需要 runner 能連到 ollama.com、模型 registry 與 Docker Hub。就算程式沒有問題，網路狀況也可能讓它失敗；遇到時先重跑一次，再開始追查。
  - Ollama 版本沒有固定（安裝腳本會安裝最新版），新版 Ollama 可能改變行為。如果造成問題，用 `OLLAMA_VERSION` 固定版本。
  - CI 為了速度使用 `TOP_K=4`、`LLM_NUM_CTX=4096`，和正式環境的預設值不同。
- **後續工作**：把實際量到的 job 時間記到 `docs/metrics.md`。考慮固定 Ollama 版本。如果之後 GPU 機器需要修改 compose，就新增 `docker-compose.gpu.yml` override；`compose-config` 會自動驗證所有 `docker-compose.*.yml`。
