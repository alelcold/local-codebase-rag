# 0021. Retrieval-only `POST /search` endpoint for MCP and other callers

- **Status**: Proposed
- **Date**: 2026-11-07
- **Related**: [codebase-rag-mcp](https://github.com/alelcold/codebase-rag-mcp) ADR 0001

> English first; 繁體中文版本在下方. Privacy: illustrate only with the sample project.

## Context

The MCP server `codebase-rag-mcp` exposes this backend to MCP hosts (Claude Code, Claude Desktop) as a `search_codebase` tool. The host's model writes the answer itself; it needs the retrieved excerpts, not an answer from `qwen2.5-coder`. `/query` always calls the local LLM, which costs 10–30 s per call on the Mac (README, metrics) and puts a second, weaker model between the code and the host's model.

## Decision

Add `POST /search`: same request body as `/query` (`question`, `top_k`), runs `RagService.retrieve_detailed` only and returns `{"indexed", "no_relevant", "sources"}`. Every retrieval switch (`HYBRID_SEARCH`, `SPLIT_RETRIEVAL`, `RERANK`, ...) applies exactly as in `/query`, so evaluation results carry over. Timeouts return 504, other failures 502, like `/query`.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
| --- | --- | --- | --- |
| MCP server calls `/query` and uses only `sources` | No backend change | Every call waits for the local LLM, whose answer is thrown away | Wasted 10–30 s per call |
| MCP server imports `app.rag` in-process | No HTTP hop | Needs LlamaIndex, Qdrant client and the `.env` on the host; two processes write one Qdrant | Couples the two repos tightly |
| `/query?llm=false` flag | One endpoint | Response shape depends on a flag; harder to document and test | A separate endpoint is clearer |

## Consequences

- **Positive**: MCP calls cost one embedding + vector search (sub-second when the model is loaded). Any other tool (scripts, IDE plugins) can reuse it.
- **Negative / trade-offs**: One more endpoint to keep in step with `/query`. Bound to `127.0.0.1` like the rest of the backend, with no authentication.
- **Follow-ups**: Add `/search` to `scripts/smoke-test.sh`; measure `/search` latency on the Mac in `docs/metrics.md` ({待填}).

---

# 0021. 只做檢索的 `POST /search` 端點，供 MCP 與其他呼叫端使用

- **狀態**：提議中
- **日期**：2026-11-07
- **相關**：[codebase-rag-mcp](https://github.com/alelcold/codebase-rag-mcp) ADR 0001

## 背景

MCP Server `codebase-rag-mcp` 把本後端以 `search_codebase` tool 的形式提供給 MCP host（Claude Code、Claude Desktop）。回答由 host 的模型自己寫，它需要的是取回的片段，而不是 `qwen2.5-coder` 的回答。`/query` 一定會呼叫本機 LLM，在 Mac 上每次要 10–30 秒，還在程式碼與 host 的模型之間多插了一個較弱的模型。

## 決策

新增 `POST /search`：請求格式與 `/query` 相同（`question`、`top_k`），只執行 `RagService.retrieve_detailed`，回傳 `{"indexed", "no_relevant", "sources"}`。所有檢索開關（`HYBRID_SEARCH`、`SPLIT_RETRIEVAL`、`RERANK` 等）與 `/query` 完全相同，評估結果可以直接沿用。逾時回 504，其他錯誤回 502，與 `/query` 一致。

## 替代方案

| 方案 | 優點 | 缺點 | 未採用原因 |
| --- | --- | --- | --- |
| MCP Server 呼叫 `/query`，只取 `sources` | 後端不用改 | 每次都要等本機 LLM，而回答直接丟掉 | 每次浪費 10–30 秒 |
| MCP Server 直接 import `app.rag` | 少一次 HTTP | host 上要裝 LlamaIndex、Qdrant client 與 `.env`；兩個行程寫同一個 Qdrant | 兩個倉庫綁太緊 |
| `/query?llm=false` 參數 | 只有一個端點 | 回應格式隨參數改變，文件與測試都比較難寫 | 分開的端點比較清楚 |

## 後果

- **正面**：MCP 呼叫只需一次 embedding 加向量檢索（模型已載入時不到一秒）。其他工具（腳本、IDE 外掛）也能共用。
- **負面／取捨**：多一個要與 `/query` 保持一致的端點。與後端其他端點一樣只綁 `127.0.0.1`、沒有驗證。
- **後續工作**：把 `/search` 加進 `scripts/smoke-test.sh`；在 Mac 上量測 `/search` 延遲，寫進 `docs/metrics.md`（{待填}）。
