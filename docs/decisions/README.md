# Architecture decision records

> English first; 繁體中文版本在下方. Each title below is given in both languages.

One file per significant decision, in the format of [`TEMPLATE.md`](TEMPLATE.md): Context, Decision, Alternatives, Consequences. Accepted ADRs are never rewritten; a changed decision gets a new ADR and the old one is marked `Superseded by NNNN` (rule in [`CLAUDE.md`](../../CLAUDE.md)).

Good places to start: [0002](0002-ollama-outside-docker-on-mac.md) (why the LLM runs outside Docker on a Mac), [0010](0010-streaming-responses.md) (streaming through proxies with idle limits), [0018](0018-codespaces-default-retrieval-settings.md) (which retrieval techniques survived the experiments, and why most did not).

| ADR | Decision / 決策 |
| --- | --- |
| [0001](0001-on-prem-rag-over-cloud-api.md) | 採用地端 RAG 而非雲端 API / On-prem RAG instead of a cloud API |
| [0002](0002-ollama-outside-docker-on-mac.md) | Mac 上 Ollama 不放進 Docker / Ollama outside Docker on Mac |
| [0003](0003-qdrant-vector-database.md) | 向量資料庫選用 Qdrant / Qdrant as the vector database |
| [0004](0004-chunking-by-file-type.md) | 依檔案類型切塊 / Chunking by file type |
| [0005](0005-model-selection-and-hardware.md) | 模型選擇與硬體對應 / Model selection and hardware |
| [0006](0006-multi-environment-deployment.md) | 多環境部署差異 / Multi-environment deployment |
| [0007](0007-multi-environment-testing-strategy.md) | 多環境測試策略 / Multi-environment testing strategy |
| [0008](0008-ci-design.md) | CI 設計：拆分 job、冒煙測試用最小模型 / CI design: split jobs, smallest model for the smoke test |
| [0009](0009-timeout-settings.md) | 逾時設定的取捨 / Timeout settings for slow inference |
| [0010](0010-streaming-responses.md) | 以 SSE 串流回答 / Streaming answers with Server-Sent Events |
| [0011](0011-devcontainer-for-codespaces.md) | Codespaces 的 dev container / Dev container for Codespaces |
| [0012](0012-automated-evaluation-metrics.md) | 自動化評估的指標與限制 / Automated evaluation: metrics and their limits |
| [0013](0013-hybrid-retrieval-and-split-retrieval.md) | 混合檢索、分類取回、切塊 metadata / Hybrid retrieval, split code/doc retrieval, chunk metadata |
| [0014](0014-similarity-threshold.md) | 相似度門檻與固定的「找不到」回答 / Similarity threshold and a fixed "not found" answer |
| [0015](0015-rerank.md) | Cross-encoder rerank：選用、延遲載入 / Cross-encoder rerank, optional and lazily loaded |
| [0016](0016-refuse-out-of-scope-questions-in-the-prompt.md) | 在提示中拒答範圍外的問題（提示 v3，未採用）/ Refuse out-of-scope questions in the prompt (prompt v3, not adopted) |
| [0017](0017-one-command-mac-benchmark.md) | Mac M2 一鍵實機測試 / One-command benchmark on the Mac M2 |
| [0018](0018-codespaces-default-retrieval-settings.md) | Codespaces 的預設檢索設定：只開分類取回 / Default retrieval settings for Codespaces: split retrieval only |
| [0019](0019-refusal-scoring-simplified-and-fabrication-check.md) | 拒答計分：簡體拒答字句與編造檢查 / Refusal scoring: Simplified refusal phrases and a fabrication check |
| [0020](0020-query-glossary-instead-of-chinese-word-segmentation.md) | 查詢詞彙表（中文詞 → 識別字），不用中文斷詞 / Query glossary (Chinese terms → identifiers) instead of Chinese word segmentation |

---

# 架構決策紀錄（ADR）

每個重要決策一份檔案，格式見 [`TEMPLATE.md`](TEMPLATE.md)：背景、決策、替代方案、後果。已接受的 ADR 不改寫；決策改變時新增一份 ADR，並把舊的標記為 `Superseded by NNNN`（規則見 [`CLAUDE.md`](../../CLAUDE.md)）。上表的標題已附中英文。

建議從這幾份開始：[0002](0002-ollama-outside-docker-on-mac.md)（為什麼在 Mac 上 LLM 不放進 Docker）、[0010](0010-streaming-responses.md)（在有閒置上限的代理後面串流回答）、[0018](0018-codespaces-default-retrieval-settings.md)（哪些檢索技巧在實驗後留下來，以及為什麼大多數沒有）。
