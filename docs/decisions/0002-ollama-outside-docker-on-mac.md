# 0002. Run Ollama natively on the Mac, not in Docker

- **Status**: Accepted
- **Date**: 2026-10-30
- **Related**: [0006](0006-multi-environment-deployment.md), README section "為什麼 Ollama 不放在 Docker 裡"

> English first; 繁體中文版本在下方.

## Context

Everything else in the stack (Qdrant, backend, frontend) runs in Docker Compose, so putting Ollama in the same compose file would be the most uniform setup. But:

- Docker on macOS runs containers inside a **Linux virtual machine**. Apple's Metal GPU is not passed through to that VM, so a containerized Ollama on a Mac can only use the CPU.
- LLM generation is memory-bandwidth and compute bound. Running a 14B model on CPU only is several times slower than with Metal acceleration. That turns a query that should take seconds into one that takes minutes.
- Apple Silicon has **unified memory**. Memory given to the Docker VM is reserved for the VM, while a native process can use memory as it needs it.

## Decision

Install Ollama directly on macOS, either the app or `brew install ollama`. Compose does **not** include an Ollama service. The backend container calls `http://host.docker.internal:11434`, which Docker Desktop resolves to the host. The URL is configurable via `OLLAMA_BASE_URL`. `scripts/setup.sh` checks that Ollama is installed and running, and pulls the models on the host.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Ollama container in Compose | One `docker compose up`; same on every OS | CPU-only on Mac; the 14B model becomes unusably slow; models stored inside a Docker volume | The GPU is the whole point |
| Ollama container with GPU passthrough | Works on Linux + NVIDIA (Container Toolkit) | Not available for Metal on macOS | Not possible on the target hardware |
| llama.cpp server natively | Fine-grained control | More manual model management; Ollama already wraps it | Ollama is simpler for the team |
| LM Studio / MLX server natively | Also uses Metal | Less scriptable or headless setup; different API | Ollama's CLI and API fit `setup.sh` best |

## Consequences

- **Positive**: Metal acceleration. Models (~9 GB) live in `~/.ollama`, survive `docker compose down -v`, and are shared with other tools.
- **Negative / trade-offs**:
  - Setup has two parts: a host install plus Compose. `setup.sh` hides most of this.
  - Behavior differs per platform. On Linux, `host.docker.internal` needs `host-gateway` and Ollama must listen on `0.0.0.0` (ADR 0006).
  - Compose cannot health-gate on Ollama. The backend's `/health` reports it instead.
- **Follow-ups**: Record measured CPU vs. Metal speed in `docs/metrics.md` when available. That gives an actual number to back this ADR.

---

# 0002. Ollama 直接裝在 Mac 上，不放進 Docker

- **狀態**：已接受
- **日期**：2026-10-30

## 背景

系統其他部分（Qdrant、後端、前端）都用 Docker Compose 執行，所以把 Ollama 也放進同一個 compose 檔是最一致的做法。但是：

- macOS 上的 Docker 是在 **Linux 虛擬機**裡執行容器，Apple 的 Metal GPU 不會傳進這台 VM。所以在 Mac 上，容器裡的 Ollama 只能用 CPU。
- LLM 生成受限於記憶體頻寬與運算量。14B 模型只用 CPU 跑，會比用 Metal 加速慢好幾倍，原本幾秒的查詢會變成好幾分鐘。
- Apple Silicon 是**統一記憶體**。分給 Docker VM 的記憶體會被 VM 固定占用，原生行程則可以依需要使用。

## 決策

Ollama 直接安裝在 macOS 上（App 或 `brew install ollama`），Compose **不包含** Ollama 服務。後端容器透過 `http://host.docker.internal:11434` 呼叫，Docker Desktop 會把這個名稱解析到主機；位址可以用 `OLLAMA_BASE_URL` 修改。`scripts/setup.sh` 會檢查 Ollama 是否已安裝並在執行，並在主機上拉取模型。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 在 Compose 裡放 Ollama 容器 | 一個 `docker compose up` 搞定；各作業系統一致 | Mac 上只能用 CPU，14B 慢到無法使用；模型存在 Docker volume 裡 | 用 GPU 才是重點 |
| Ollama 容器＋GPU 直通 | Linux＋NVIDIA（Container Toolkit）可行 | macOS 的 Metal 不支援 | 目標硬體上做不到 |
| 原生執行 llama.cpp server | 可以細部控制 | 模型管理要手動處理較多；Ollama 本身就是包裝它 | Ollama 對團隊來說比較簡單 |
| 原生執行 LM Studio／MLX server | 同樣能用 Metal | 較難寫成腳本或無介面執行；API 不同 | Ollama 的 CLI 與 API 最適合 `setup.sh` |

## 後果

- **正面**：有 Metal 加速。模型（約 9GB）存在 `~/.ollama`，`docker compose down -v` 也不會刪掉，而且其他工具可以共用。
- **負面／取捨**：
  - 安裝分成兩部分：主機安裝＋Compose。`setup.sh` 幫忙處理掉大部分。
  - 不同平台的行為不同：Linux 上的 `host.docker.internal` 需要 `host-gateway`，Ollama 也要監聽 `0.0.0.0`（ADR 0006）。
  - Compose 無法用 Ollama 的狀態來控制啟動順序，改由後端的 `/health` 回報。
- **後續工作**：有實測數據後，把 CPU 和 Metal 的速度比較記錄到 `docs/metrics.md`，用實際數字支持這份 ADR。
