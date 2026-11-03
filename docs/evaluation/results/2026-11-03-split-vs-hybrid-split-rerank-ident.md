# Evaluation comparison / 評估比較

- **A**: `codespace-3b-k4-split-ident` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · split (docs ≤ 1) · prompt v1
- **B**: `codespace-3b-k4-hybrid-split-rerank-ident` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · hybrid (RRF k=60) + split (docs ≤ 1) + rerank (BAAI/bge-reranker-base, 10 → 4) · prompt v1

Δ = B − A. ▲ better, ▼ worse. Automatic metrics are proxies, not correctness (ADR 0012).
Δ = B − A。▲ 較好、▼ 較差。自動指標只是代理指標，不等於回答正確（ADR 0012）。

## Summary / 摘要

| Metric / 指標 | A | B | Δ |
| --- | --- | --- | --- |
| Time to first token, mean / 首字延遲平均 | 17.8 s | 26.3 s | +8.5 s ▼ |
| Time to first token, median / 首字延遲中位數 | 11.2 s | 22.8 s | +11.6 s ▼ |
| Total time, mean / 總耗時平均 | 27.1 s | 37.7 s | +10.7 s ▼ |
| Rerank time, mean / rerank 耗時平均 | — | 6.4 s | — |
| Tokens, mean / 平均 token 數 | 99.2 | 113.6 | +14.4 |
| Expected-file recall / 預期檔案命中率 | 90% | 90% | 0 |
| Code file retrieved / 程式碼檔命中 | 100% | 100% | 0 |
| Doc file retrieved / 文件檔命中 | — | — | — |
| Defining file retrieved / 定義檔命中 | 100% | 100% | 0 |
| Expected file cited with [n] / 回答引用預期檔案 | 100% | 40% | -60 pt ▼ |
| Docs among retrieved chunks / 取回片段中文件比例 | 25% | 15% | -10 pt |
| Keyword hit rate / 關鍵字命中率 | 83% | 77% | -7 pt ▼ |
| Answers with Simplified / 混入簡體字的回答 | 0 | 0 | 0 |
| Trick question refused / 陷阱題正確拒答 | — | — | — |
| Refused by SCORE_THRESHOLD / 因門檻直接拒答 | — | 0 | — |
| Manual correctness / 人工判定正確性 | — | — | — |
| Errors / 失敗題數 | 0 | 0 | 0 |

## Per question / 每題

| # | Type | First token A → B | Total A → B | Files A → B | Code A → B | Def. A → B | Keywords A → B | Simplified A / B | Manual A / B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | 定位設定 | 42.9 s → 57.3 s | 49.8 s → 72.3 s | 2/2 → 2/2 | 2/2 → 2/2 | 1/1 → 1/1 | 3/4 → 3/4 | — / — | — / — |
| 12 | 解釋邏輯 | 8.7 s → 22.8 s | 27.6 s → 43.0 s | 1/2 → 1/2 | 1/2 → 1/2 | — → — | 3/4 → 3/4 | — / — | — / — |
| 13 | 定位設定 | 22.3 s → 26.1 s | 28.3 s → 32.2 s | 2/2 → 2/2 | 2/2 → 2/2 | 1/1 → 1/1 | 4/4 → 4/4 | — / — | — / — |
| 14 | 定位設定 | 11.2 s → 18.6 s | 17.5 s → 25.0 s | 2/2 → 2/2 | 2/2 → 2/2 | 1/1 → 1/1 | 3/3 → 2/3 | — / — | — / — |
| 15 | 跨檔案流程 | 4.0 s → 6.6 s | 12.2 s → 16.3 s | 2/2 → 2/2 | 2/2 → 2/2 | — → — | 2/3 → 2/3 | — / — | — / — |
