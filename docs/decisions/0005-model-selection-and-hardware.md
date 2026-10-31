# 0005. Model selection and hardware mapping (3B / 14B / 32B)

- **Status**: Accepted (default 14B on Mac M2 32 GB; 32B to be evaluated)
- **Date**: 2026-10-30
- **Related**: [0002](0002-ollama-outside-docker-on-mac.md), [0006](0006-multi-environment-deployment.md), [metrics](../metrics.md)

> English first; 繁體中文版本在下方.

## Context

The LLM has to read 4–16 code snippets and explain them accurately with citations. A code-specialized model family helps. The target machine is a Mac M2 with **32 GB unified memory**, shared by macOS, Docker Desktop, the browser and the model.

The memory a model needs is roughly **weights + KV cache + runtime overhead**:

- Weights at 4-bit quantization (Ollama's default `Q4_K_M` tags) take about 0.6 GB per billion parameters.
- The KV cache grows with the context length (`LLM_NUM_CTX`, default 16384). RAG prompts are long, so it cannot be ignored.

Approximate download sizes of the Ollama `qwen2.5-coder` tags (Q4):

| Model | Weights (Q4) | Est. total at 16K ctx | Fits on | Role |
| --- | --- | --- | --- | --- |
| `qwen2.5-coder:3b` | ~1.9 GB | ~3–4 GB | Any machine, including CPU-only Codespaces | Pipeline checks; low-memory fallback |
| `qwen2.5-coder:7b` | ~4.7 GB | ~6–7 GB | 16 GB Macs | Faster option |
| `qwen2.5-coder:14b` | ~9 GB | ~12–13 GB | **32 GB Mac (default)** | Best quality/speed balance on target |
| `qwen2.5-coder:32b` | ~20 GB | ~23–26 GB | 32 GB Mac only borderline; 24 GB+ GPU (e.g. A10G) or 48 GB+ Mac | Quality ceiling to compare against |

The totals are estimates and still need to be measured (`ollama ps`, Activity Monitor). Also, macOS by default lets the GPU use only part of unified memory, so a 32B model on a 32 GB Mac may partly fall back to CPU or crowd out other apps.

Embedding model: `nomic-embed-text` (~0.3 GB). It has an 8K-token context, works well for English and code, and is a single small download.

## Decision

- Default `LLM_MODEL=qwen2.5-coder:14b` and `EMBED_MODEL=nomic-embed-text`. Both can be changed in `.env`.
- Use `qwen2.5-coder:3b` for validating the flow on CPU-only environments (Codespaces).
- Treat `qwen2.5-coder:32b` as an **experiment** on a GPU instance or a larger Mac, to measure how much quality is gained per extra second of latency.
- Send `num_ctx` explicitly (`LLM_NUM_CTX=16384`) so retrieved code is not silently truncated.

## Alternatives considered

| Option | Pros | Cons | Why not chosen as default |
| --- | --- | --- | --- |
| General chat models (e.g. Llama 3.x 8B) | Good general language | Weaker on code than code-tuned models of similar size | Domain is code |
| 32B as default | Best quality in the family | Borderline memory on 32 GB; slow; competes with Docker and the IDE | Risky on target hardware |
| 7B as default | Fast; fits 16 GB | Noticeably weaker explanations | 32 GB allows 14B |
| Different embedding model (e.g. `mxbai-embed-large`, `bge-m3`) | Possibly better multilingual retrieval | Larger; needs re-index | Start simple; the evaluation set decides. Switching is just a config change, because collections are per model. |

## Consequences

- **Positive**: The default fits comfortably and leaves memory for Docker and an IDE. Model choice is one env var, and the collection is named per embedding model, so switching is safe.
- **Negative / trade-offs**: 14B is not the best possible quality. Chinese questions go against an English-centric embedding model, so retrieval may be weaker than for English questions. This needs evaluation.
- **Follow-ups**: Fill in the 3B / 14B / 32B comparison table in `docs/metrics.md` (speed, memory, evaluation score). Revisit this ADR with that data.

---

# 0005. 模型選擇與硬體對應（3B／14B／32B）

- **狀態**：已接受（Mac M2 32GB 預設 14B；32B 待評估）
- **日期**：2026-10-30

## 背景

LLM 要閱讀 4–16 段程式碼，並在附上引用的前提下準確說明。程式碼專用的模型系列會有幫助。目標機器是 **32GB 統一記憶體**的 Mac M2，由 macOS、Docker Desktop、瀏覽器和模型共用。

模型需要的記憶體大約是**權重 ＋ KV cache ＋ 執行時開銷**：

- 4-bit 量化（Ollama 預設的 `Q4_K_M` 標籤）的權重，每 10 億參數約需 0.6GB。
- KV cache 會隨上下文長度（`LLM_NUM_CTX`，預設 16384）增加。RAG 的提示詞很長，這部分不能忽略。

Ollama `qwen2.5-coder` 各標籤（Q4）的大約下載大小：

| 模型 | 權重（Q4） | 16K 上下文時的估計總量 | 適用硬體 | 用途 |
| --- | --- | --- | --- | --- |
| `qwen2.5-coder:3b` | 約 1.9GB | 約 3–4GB | 任何機器，包含只有 CPU 的 Codespaces | 驗證流程；記憶體不足時的備案 |
| `qwen2.5-coder:7b` | 約 4.7GB | 約 6–7GB | 16GB 的 Mac | 較快的選項 |
| `qwen2.5-coder:14b` | 約 9GB | 約 12–13GB | **32GB 的 Mac（預設）** | 目標硬體上品質與速度最平衡 |
| `qwen2.5-coder:32b` | 約 20GB | 約 23–26GB | 32GB 的 Mac 只是勉強可行；24GB 以上的 GPU（如 A10G）或 48GB 以上的 Mac | 作為品質上限的比較基準 |

總量都是估計值，還需要實測（`ollama ps`、活動監視器）。另外，macOS 預設只讓 GPU 使用一部分統一記憶體，所以在 32GB 的 Mac 上跑 32B，可能有部分退回 CPU，或排擠其他應用程式。

Embedding 模型：`nomic-embed-text`（約 0.3GB）。上下文長度 8K tokens，英文與程式碼表現良好，只需下載一個小模型。

## 決策

- 預設 `LLM_MODEL=qwen2.5-coder:14b`、`EMBED_MODEL=nomic-embed-text`，兩者都可以在 `.env` 修改。
- 在只有 CPU 的環境（Codespaces）驗證流程時，使用 `qwen2.5-coder:3b`。
- `qwen2.5-coder:32b` 當作**實驗**，在 GPU 機器或更大的 Mac 上測試，量測每多花一秒延遲能換到多少品質。
- 明確傳入 `num_ctx`（`LLM_NUM_CTX=16384`），避免檢索到的程式碼被默默截斷。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用為預設的原因 |
| --- | --- | --- | --- |
| 通用聊天模型（如 Llama 3.x 8B） | 一般語言能力好 | 寫程式的能力不如同尺寸的程式碼模型 | 這裡處理的是程式碼 |
| 預設用 32B | 同系列中品質最好 | 32GB 記憶體勉強夠；速度慢；會和 Docker、IDE 搶資源 | 在目標硬體上風險太高 |
| 預設用 7B | 快；16GB 也放得下 | 解釋品質明顯較弱 | 32GB 足以使用 14B |
| 其他 embedding 模型（如 `mxbai-embed-large`、`bge-m3`） | 多語言檢索可能更好 | 模型較大；需要重新索引 | 先從簡單的開始，由評估題組決定。每個模型有自己的 collection，切換只需要改設定 |

## 後果

- **正面**：預設模型放得下，還能留記憶體給 Docker 和 IDE。換模型只要改一個環境變數，而且 collection 依 embedding 模型命名，切換很安全。
- **負面／取捨**：14B 不是能達到的最佳品質。中文問題要對上以英文為主的 embedding 模型，檢索效果可能不如英文問題，需要評估。
- **後續工作**：填寫 `docs/metrics.md` 中 3B／14B／32B 的比較表（速度、記憶體、評估分數），再用這些數據重新檢視這份 ADR。
