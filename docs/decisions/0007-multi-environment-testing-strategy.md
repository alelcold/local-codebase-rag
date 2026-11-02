# 0007. Multi-environment testing strategy

- **Status**: Accepted
- **Date**: 2026-11-02
- **Related**: [0005](0005-model-selection-and-hardware.md), [0006](0006-multi-environment-deployment.md), [0008](0008-ci-design.md), [0009](0009-timeout-settings.md), [devlog 2026-11-01 Codespaces setup](../devlog/2026-11-01-codespace-setup.md)

> English first; 繁體中文版本在下方. Privacy: illustrate only with the sample project.

## Context

ADR 0006 decided **how** the stack runs on the Mac, on Codespaces and on a GPU instance. It did not decide **what each environment is for when testing**, and the Codespaces run showed that this matters:

- The same code passed every unit test, yet on Codespaces the containers first could not reach Ollama (Linux networking), and later the UI returned 504 because a CPU-only query took 1.5–2 minutes.
- Neither problem can appear in unit tests: Ollama and Qdrant are faked there, so there is no real network and no real latency.
- Each environment is expensive in a different way: the Mac is the team's production machine, a GPU instance costs money per hour, and Codespaces uses free-tier core-hours.

## Decision

Use four test layers. Each layer answers one question and has a fixed place to run:

| Layer | Question it answers | Where | Model | When |
| --- | --- | --- | --- | --- |
| 1. Unit tests | Is the logic correct? (chunking, incremental index, citations, API errors) | CI + laptop | Fakes | Every push |
| 2. Compose and image checks | Do the config and images build? | CI | — | Every push |
| 3. End-to-end smoke test | Does the real pipeline work (network, Ollama API, Qdrant, nginx proxy, citations)? | CI runner (Linux, CPU) | `qwen2.5-coder:0.5b` + `nomic-embed-text` | PRs into `main` |
| 4. Manual environment runs | Does it work **and perform** on a real target? | Codespaces (3B), Mac M2 (14B), GPU instance (32B) | Target model | Before a release, or when changing models, chunking or deployment |

Rules:

- **Correctness first, cheapest environment first.** A change must pass layers 1–3 before anyone spends Codespaces hours or GPU money.
- **Codespaces is the Linux rehearsal for the Mac.** It catches Linux-only and CPU-only problems (networking, slow inference, timeouts). Its speed and answer quality are **not** reported as production numbers (ADR 0006).
- **Quality is only judged on the target model and hardware.** The 10-question evaluation (`docs/evaluation/questions.md`) runs on the Mac with 14B, or on a GPU instance with 32B, never with 0.5B or 3B.
- **Every manual run leaves a record**: a devlog entry with problems in the form Problem → Cause → Fix, and measured numbers in `docs/metrics.md` (`{待填}` when not measured).
- **A bug found in a higher layer gets a test in the lowest layer that can catch it.** For example, the 504 timeout is now covered by unit tests that check a clear 504 response (`test_query_llm_timeout_returns_504_with_setting_name`).

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Unit tests only | Fast, free | Missed both Codespaces problems and the earlier `text-dense` bug (devlog 2026-10-30) | Not enough |
| Test only on the Mac | Real target | Uses the team's production machine; Linux problems surface late, on the first Linux deploy | Too late and too risky |
| Run the full evaluation in CI | Automatic quality tracking | Needs a 14B+ model, so a GPU runner or very long CPU jobs; results with tiny models are meaningless | Cost and noise; revisit later |
| Ollama in Docker for tests | One `compose up` for everything | Different topology from production (ADR 0006) | Topology consistency matters more |

## Consequences

- **Positive**: Each environment has one clear purpose. Linux and network problems are caught in CI before they reach Codespaces or the Mac. Numbers in `docs/metrics.md` always state the environment, so CPU results are not mistaken for production performance.
- **Negative / trade-offs**: Answer quality is still checked by hand. The CI smoke test only proves that the pipeline works, not that answers are good. Layer 4 depends on discipline: someone has to run it and record the results.
- **Follow-ups**: Automate the 10-question evaluation once there is an affordable runner for 14B (self-hosted Mac runner, or a scheduled GPU job). Add a `scripts/setup-linux.sh` if the Codespaces steps keep growing.

---

# 0007. 多環境測試策略

- **狀態**：已接受
- **日期**：2026-11-02
- **相關**：[0005](0005-model-selection-and-hardware.md)、[0006](0006-multi-environment-deployment.md)、[0008](0008-ci-design.md)、[0009](0009-timeout-settings.md)、[devlog 2026-11-01 Codespaces 環境建置](../devlog/2026-11-01-codespace-setup.md)

## 背景

ADR 0006 決定了系統在 Mac、Codespaces 與 GPU 機器上**怎麼執行**，但沒有決定**測試時每個環境負責什麼**。Codespaces 的測試顯示這件事很重要：

- 同一份程式碼的單元測試全部通過，但在 Codespaces 上，先是容器連不到 Ollama（Linux 網路差異），後來介面又回傳 504，因為只有 CPU 時一次查詢要 1.5～2 分鐘。
- 這兩個問題都不可能在單元測試中出現：單元測試裡的 Ollama 和 Qdrant 都是假物件，沒有真實網路，也沒有真實延遲。
- 每個環境的成本不同：Mac 是團隊正式使用的機器，GPU 機器按小時計費，Codespaces 則消耗免費額度的核心小時數。

## 決策

測試分成四層，每一層只回答一個問題，並固定在某個環境執行：

| 層級 | 回答的問題 | 執行位置 | 模型 | 時機 |
| --- | --- | --- | --- | --- |
| 1. 單元測試 | 邏輯是否正確？（切塊、增量索引、引用、API 錯誤處理） | CI + 本機 | 假物件 | 每次 push |
| 2. Compose 與映像檔檢查 | 設定檔正確、映像檔 build 得起來？ | CI | — | 每次 push |
| 3. 端到端冒煙測試 | 真實流程是否正常（網路、Ollama API、Qdrant、nginx 代理、引用）？ | CI runner（Linux、CPU） | `qwen2.5-coder:0.5b` + `nomic-embed-text` | 對 `main` 的 PR |
| 4. 手動環境測試 | 在真實目標環境上能不能用、**效能**如何？ | Codespaces（3B）、Mac M2（14B）、GPU 機器（32B） | 目標模型 | 發佈前，或更換模型、切塊方式、部署方式時 |

規則：

- **先確認正確性，先用最便宜的環境**。變更要先通過第 1～3 層，才值得花 Codespaces 時數或 GPU 費用。
- **Codespaces 是 Mac 部署前的 Linux 預演**。它負責抓出只在 Linux 或只有 CPU 時才會發生的問題（網路、推論慢、逾時）。它的速度與回答品質**不**當作正式環境的數據（ADR 0006）。
- **回答品質只在目標模型與硬體上評估**。10 題評估（`docs/evaluation/questions.md`）在 Mac 上用 14B，或在 GPU 機器上用 32B 執行，不用 0.5B 或 3B。
- **每次手動測試都要留下紀錄**：devlog 以「問題 → 原因 → 解法」記錄，量到的數字寫進 `docs/metrics.md`（沒量到就保留 `{待填}`）。
- **在高層級發現的問題，要在最低、能抓到它的層級補測試**。例如 504 逾時問題，現在有單元測試確認會回傳清楚的 504（`test_query_llm_timeout_returns_504_with_setting_name`）。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 只做單元測試 | 快、免費 | 沒抓到 Codespaces 的兩個問題，也沒抓到先前的 `text-dense` 問題（devlog 2026-10-30） | 不夠 |
| 只在 Mac 上測試 | 就是目標環境 | 佔用團隊正式使用的機器；Linux 問題要到第一次部署 Linux 時才會發現 | 太晚、風險太高 |
| 在 CI 跑完整評估 | 自動追蹤品質 | 需要 14B 以上的模型，也就是 GPU runner 或很長的 CPU 工作；用極小模型跑出的分數沒有意義 | 成本高、結果沒參考價值；之後再評估 |
| 測試時把 Ollama 放進 Docker | 一次 `compose up` 就全部啟動 | 和正式環境的架構不同（ADR 0006） | 架構一致比較重要 |

## 後果

- **正面**：每個環境的用途清楚。Linux 與網路問題在 CI 就會被抓到，不會等到 Codespaces 或 Mac 才發現。`docs/metrics.md` 的數字一定註明環境，不會把 CPU 的結果誤當正式環境效能。
- **負面／取捨**：回答品質仍要人工檢查。CI 冒煙測試只能證明流程能跑，不能證明回答好。第 4 層要靠紀律：得有人去跑並記錄結果。
- **後續工作**：等到有負擔得起、能跑 14B 的 runner（自架 Mac runner，或排程的 GPU 工作），再把 10 題評估自動化。Codespaces 的步驟如果持續變多，考慮新增 `scripts/setup-linux.sh`。
