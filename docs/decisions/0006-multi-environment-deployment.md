# 0006. Handling differences across environments (Mac / EC2 GPU / Codespaces)

- **Status**: Accepted
- **Date**: 2026-11-01
- **Related**: [0002](0002-ollama-outside-docker-on-mac.md), [0005](0005-model-selection-and-hardware.md), [devlog 2026-11-01](../devlog/2026-11-01.md), `docker-compose.yml`

> English first; 繁體中文版本在下方.

## Context

The same repo must run in three kinds of environment:

| Environment | Purpose | OS / Docker | GPU |
| --- | --- | --- | --- |
| Mac M2 32 GB | Production for the team | macOS, Docker Desktop (Linux VM) | Metal (host only) |
| GitHub Codespaces | Validate the pipeline quickly | Linux container, Docker Engine | None |
| GPU cloud instance (evaluated: AWS EC2 `g5.xlarge`, RunPod, Lambda) | Benchmark larger models (32B) | Linux, Docker Engine | NVIDIA (e.g. A10G 24 GB on `g5.xlarge`) |

The key difference is **how a container reaches Ollama on the host**:

- **Docker Desktop (Mac)** resolves `host.docker.internal` automatically and forwards to the host's loopback. Ollama's default `127.0.0.1:11434` works.
- **Docker Engine on Linux** does not define `host.docker.internal`. With `extra_hosts: host.docker.internal:host-gateway`, the name maps to the bridge gateway IP. The connection then arrives on that interface, so Ollama must listen on it: `OLLAMA_HOST=0.0.0.0`.

## Decision

- Keep **one** `docker-compose.yml` for all environments. It always includes `extra_hosts: ["host.docker.internal:host-gateway"]`. That entry is harmless on Docker Desktop and required on Linux.
- Always run Ollama **on the host**, outside Compose, in every environment, so the topology stays the same as on the Mac.
- Per-environment differences live only in `.env` and in how Ollama is started:

| Setting | Mac M2 | Codespaces (CPU) | GPU instance |
| --- | --- | --- | --- |
| Ollama start | App / `brew services` (default bind is fine) | `OLLAMA_HOST=0.0.0.0 ollama serve` | `OLLAMA_HOST=0.0.0.0 ollama serve` (systemd override) + NVIDIA driver |
| `LLM_MODEL` | `qwen2.5-coder:14b` | `qwen2.5-coder:3b` | `qwen2.5-coder:32b` (benchmark) |
| `FRONTEND_BIND` | `127.0.0.1`, or `0.0.0.0` for team LAN | `127.0.0.1` (use port forwarding) | `127.0.0.1` + SSH tunnel |
| Exposure rule | — | Keep port 11434 private | Security group: **no** inbound 11434/8000/6333; SSH only |

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Separate compose files or profiles per environment | Each file is explicit | Drift between files; more to maintain | One file plus env vars is enough |
| Ollama in Compose on Linux, native on Mac | GPU passthrough is possible on Linux NVIDIA | Two topologies, which means different bugs on different machines | Consistency matters more |
| `network_mode: host` for the backend | No `host.docker.internal` needed on Linux | Not supported the same way on Docker Desktop; breaks service-name DNS (`qdrant`) | Not portable |
| Hard-code the bridge IP (`172.17.0.1`) | Works on default Linux setups | Fragile; differs per machine | `host-gateway` is the supported way |

### GPU environment comparison (for 32B benchmarks)

| Option | Notes | Cost |
| --- | --- | --- |
| AWS EC2 `g5.xlarge` | 1× NVIDIA A10G (24 GB), 4 vCPU, 16 GiB RAM; full VM, Docker works normally; needs a quota request for GPU instances | {待填} USD/h |
| RunPod | GPU pods billed per second/hour; usually a container-based environment, so check whether running Docker Compose inside is supported | {待填} USD/h |
| Lambda | GPU cloud VMs with drivers preinstalled; availability varies | {待填} USD/h |

Prices and availability change often. Record the actual hourly price and total spend in `docs/metrics.md` when you run a benchmark.

## Consequences

- **Positive**: There is one compose file, so the same commands work everywhere. Codespaces gives a free, disposable way to test changes before touching the Mac.
- **Negative / trade-offs**:
  - On Linux, Ollama listens on all interfaces. Protect it with private ports, security groups or a host firewall. Ollama has no authentication.
  - CPU-only Codespaces results (speed, and quality with 3B) do not represent production. Only use them for pass/fail checks of the pipeline.
- **Follow-ups**: Benchmark 32B on one GPU option, and record the cost and results in `docs/metrics.md`. Consider a `scripts/setup-linux.sh` if the Linux steps grow.

---

# 0006. 多環境部署（Mac／EC2 GPU／Codespaces）的差異處理

- **狀態**：已接受
- **日期**：2026-11-01

## 背景

同一個 repo 要能在三類環境執行：

| 環境 | 用途 | 作業系統／Docker | GPU |
| --- | --- | --- | --- |
| Mac M2 32GB | 團隊正式使用 | macOS、Docker Desktop（Linux VM） | Metal（只有主機能用） |
| GitHub Codespaces | 快速驗證流程 | Linux 容器、Docker Engine | 無 |
| GPU 雲端機器（評估過：AWS EC2 `g5.xlarge`、RunPod、Lambda） | 測試較大的模型（32B） | Linux、Docker Engine | NVIDIA（例如 `g5.xlarge` 的 A10G 24GB） |

關鍵差異在於**容器如何連到主機上的 Ollama**：

- **Docker Desktop（Mac）** 會自動解析 `host.docker.internal`，並轉到主機的 loopback，所以 Ollama 預設的 `127.0.0.1:11434` 就能用。
- **Linux 上的 Docker Engine** 不會定義 `host.docker.internal`。設定 `extra_hosts: host.docker.internal:host-gateway` 後，這個名稱會對應到 bridge gateway IP，連線也會從那張網卡進來，所以 Ollama 必須監聽它：`OLLAMA_HOST=0.0.0.0`。

## 決策

- 所有環境共用**同一個** `docker-compose.yml`，並且一律包含 `extra_hosts: ["host.docker.internal:host-gateway"]`。這一行在 Docker Desktop 上無害，在 Linux 上則是必要的。
- 每個環境的 Ollama 都在**主機上**執行，不放進 Compose，讓架構和 Mac 一致。
- 環境間的差異只放在 `.env` 和 Ollama 的啟動方式：

| 設定 | Mac M2 | Codespaces（CPU） | GPU 機器 |
| --- | --- | --- | --- |
| 啟動 Ollama | App／`brew services`（預設監聽位址即可） | `OLLAMA_HOST=0.0.0.0 ollama serve` | `OLLAMA_HOST=0.0.0.0 ollama serve`（systemd override）＋ NVIDIA 驅動 |
| `LLM_MODEL` | `qwen2.5-coder:14b` | `qwen2.5-coder:3b` | `qwen2.5-coder:32b`（效能測試） |
| `FRONTEND_BIND` | `127.0.0.1`；開放區網給團隊時用 `0.0.0.0` | `127.0.0.1`（用 port forwarding） | `127.0.0.1`＋SSH tunnel |
| 對外開放原則 | — | 11434 埠維持 private | Security group **不開放** 11434／8000／6333 的對內連線，只開 SSH |

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 每個環境各自的 compose 檔或 profile | 每個檔案都很明確 | 檔案之間會逐漸不一致，維護成本較高 | 一個檔案加上環境變數就夠了 |
| Linux 上把 Ollama 放進 Compose，Mac 上原生執行 | Linux＋NVIDIA 可以 GPU 直通 | 兩種架構，不同機器會出現不同的問題 | 一致性比較重要 |
| 後端使用 `network_mode: host` | Linux 上不需要 `host.docker.internal` | Docker Desktop 的行為不同；服務名稱 DNS（`qdrant`）會失效 | 無法跨平台 |
| 寫死 bridge IP（`172.17.0.1`） | 預設的 Linux 設定可用 | 脆弱，每台機器可能不同 | `host-gateway` 才是官方支援的做法 |

### GPU 環境比較（用於 32B 測試）

| 選項 | 說明 | 費用 |
| --- | --- | --- |
| AWS EC2 `g5.xlarge` | 1 張 NVIDIA A10G（24GB）、4 vCPU、16 GiB RAM；完整 VM，Docker 正常使用；GPU 機型需要先申請配額 | {待填} 美元／小時 |
| RunPod | GPU pod 按秒或小時計費；通常是容器環境，需確認能否在裡面執行 Docker Compose | {待填} 美元／小時 |
| Lambda | 預裝驅動的 GPU 雲端 VM；能否開到機器視時段而定 | {待填} 美元／小時 |

價格與可用性變動頻繁。實際測試時，請把每小時價格和總花費記錄到 `docs/metrics.md`。

## 後果

- **正面**：只有一個 compose 檔，到哪裡都用同樣的指令。Codespaces 提供免費、用完即丟的環境，可以在動到 Mac 之前先測試變更。
- **負面／取捨**：
  - Linux 上的 Ollama 會監聽所有網卡，必須用 private port、security group 或主機防火牆保護。Ollama 本身沒有驗證機制。
  - 只有 CPU 的 Codespaces 結果（速度，以及 3B 的品質）不代表正式環境，只能用來確認流程能不能跑通。
- **後續工作**：選一個 GPU 方案測試 32B，並把費用與結果記錄到 `docs/metrics.md`。如果 Linux 的步驟變多，可以考慮新增 `scripts/setup-linux.sh`。
