# 0001. Use on-premises RAG instead of a cloud LLM API

- **Status**: Accepted
- **Date**: 2026-10-30
- **Related**: [devlog 2026-10-30](../devlog/2026-10-30.md), [0005](0005-model-selection-and-hardware.md)

> English first; 繁體中文版本在下方.

## Context

The team wants to ask natural-language questions about a game front-end codebase (about 50–300 files). Source code is the most sensitive asset involved. Requirements:

- **Privacy**: code and questions must not leave the company machine, and no third-party retention policy should have to be reviewed.
- **Cost**: usage is open-ended (many people, many questions). Per-token billing makes the cost hard to predict.
- **Quality**: answers must be grounded in the actual code and cite file and line, not general knowledge.
- **Hardware available**: one Mac M2 with 32 GB unified memory.

## Decision

Run the whole RAG pipeline locally. Ollama on the Mac serves both the LLM and the embedding model, and Qdrant stores the vectors. No cloud API is called at index or query time.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| Cloud LLM API (e.g. Claude / GPT) + hosted vector DB | Best answer quality; no hardware to manage | Code leaves the network; needs legal and security review; per-token cost grows with usage | Privacy requirement |
| Cloud LLM API + local embeddings and local vector DB | Only the retrieved snippets are sent | Snippets are still source code | Same privacy issue, smaller surface |
| IDE assistant with whole-repo context | No infrastructure | Usually cloud-backed; per-seat cost; not a shared team tool | Privacy and cost |
| Plain code search (grep / IDE search) | Zero cost, exact | Requires knowing the identifiers; no explanations | Does not answer "how does X work" questions |

## Consequences

- **Positive**: Code never leaves the machine. Marginal cost per question is about zero (only electricity). It works offline. The models can be changed freely.
- **Negative / trade-offs**:
  - A 14B local model is weaker than frontier cloud models at multi-step reasoning, so the answers rely more heavily on good retrieval. That is why chunking (ADR 0004) and evaluation (`docs/evaluation/`) matter.
  - Throughput is limited to one Mac. Concurrent users queue behind each other.
  - The team owns operations: model updates, the Ollama process, disk space.
- **Follow-ups**: Measure the quality gap with the evaluation set (`docs/metrics.md`). If quality is not good enough, test larger models on a GPU instance (ADR 0005, ADR 0006) before reconsidering cloud APIs.

Note: the system itself was **built** with a cloud coding assistant (a Claude Code session, about USD 7). That used only this repo and the sample project, never company code.

---

# 0001. 採用地端 RAG，而非雲端 LLM API

- **狀態**：已接受
- **日期**：2026-10-30

## 背景

團隊希望能用自然語言查詢遊戲前端專案的程式碼（約 50–300 個檔案）。這裡最敏感的資產就是原始碼。需求：

- **隱私**：程式碼與問題不能離開公司的機器，也不想為此審查第三方的資料保存政策。
- **成本**：使用量沒有上限（很多人、很多問題），按 token 計費很難預估花費。
- **品質**：回答必須根據實際程式碼，並引用檔案與行號，而不是一般常識。
- **可用硬體**：一台 32GB 統一記憶體的 Mac M2。

## 決策

整條 RAG 流程都在本機執行：Mac 上的 Ollama 同時提供 LLM 與 embedding 模型，Qdrant 儲存向量。索引和查詢時都不呼叫任何雲端 API。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| 雲端 LLM API（如 Claude／GPT）＋ 雲端向量資料庫 | 回答品質最好，不需要管硬體 | 程式碼離開公司網路；需要法務與資安審查；按 token 計費會隨用量增加 | 不符隱私需求 |
| 雲端 LLM API ＋ 本機 embedding 與本機向量資料庫 | 只會送出檢索到的片段 | 片段本身仍是原始碼 | 同樣有隱私問題，只是範圍較小 |
| 能讀整個 repo 的 IDE 助手 | 不需要架設任何東西 | 通常依賴雲端；按人數計費；不是團隊共用的工具 | 隱私與成本 |
| 單純的程式碼搜尋（grep／IDE 搜尋） | 零成本、結果精確 | 要先知道識別字名稱；不會解釋 | 回答不了「X 是怎麼運作的」這類問題 |

## 後果

- **正面**：程式碼不離開本機；每次提問的邊際成本幾乎為零（只有電費）；可以離線使用；可以自由更換模型。
- **負面／取捨**：
  - 14B 的地端模型在多步推理上不如頂尖雲端模型，所以回答更依賴檢索的品質。這也是切塊策略（ADR 0004）與評估（`docs/evaluation/`）很重要的原因。
  - 吞吐量受限於一台 Mac，多人同時使用時需要排隊。
  - 維運由團隊自己負責：模型更新、Ollama 行程、磁碟空間。
- **後續工作**：用評估題組量測品質落差（`docs/metrics.md`）。如果品質不夠，先在 GPU 機器上測試更大的模型（ADR 0005、ADR 0006），再考慮雲端 API。

註：這套系統本身是用雲端程式助手**建置**的（Claude Code 工作階段，約 7 美元），過程只用到本 repo 與範例專案，從未用到公司程式碼。
