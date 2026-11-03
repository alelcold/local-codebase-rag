# Evaluation comparison / 評估比較

- **A**: `codespace-3b-k4-baseline` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · vector only (baseline) · prompt v1
- **B**: `codespace-3b-k4-hybrid-split-rerank` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · hybrid (RRF k=60) + split (docs ≤ 1) + rerank (BAAI/bge-reranker-base, 10 → 4) · prompt v1

Δ = B − A. ▲ better, ▼ worse. Automatic metrics are proxies, not correctness (ADR 0012).
Δ = B − A。▲ 較好、▼ 較差。自動指標只是代理指標，不等於回答正確（ADR 0012）。

## Summary / 摘要

| Metric / 指標 | A | B | Δ |
| --- | --- | --- | --- |
| Time to first token, mean / 首字延遲平均 | 13.0 s | 26.8 s | +13.8 s ▼ |
| Time to first token, median / 首字延遲中位數 | 13.4 s | 21.3 s | +7.9 s ▼ |
| Total time, mean / 總耗時平均 | 20.9 s | 40.7 s | +19.8 s ▼ |
| Rerank time, mean / rerank 耗時平均 | — | 4.8 s | — |
| Tokens, mean / 平均 token 數 | 89.3 | 141.3 | +52.0 |
| Expected-file recall / 預期檔案命中率 | 15% | 56% | +41 pt ▲ |
| Code file retrieved / 程式碼檔命中 | 11% | 78% | +67 pt ▲ |
| Doc file retrieved / 文件檔命中 | 75% | 50% | -25 pt ▼ |
| Defining file retrieved / 定義檔命中 | 0% | 100% | +100 pt ▲ |
| Expected file cited with [n] / 回答引用預期檔案 | 0% | 22% | +22 pt ▲ |
| Docs among retrieved chunks / 取回片段中文件比例 | 95% | 22% | -72 pt |
| Keyword hit rate / 關鍵字命中率 | 32% | 45% | +13 pt ▲ |
| Answers with Simplified / 混入簡體字的回答 | 1 | 0 | -1 ▲ |
| Trick question refused / 陷阱題正確拒答 | 0% | 0% | 0 |
| Refused by SCORE_THRESHOLD / 因門檻直接拒答 | — | 0 | — |
| Manual correctness / 人工判定正確性 | — | — | — |
| Errors / 失敗題數 | 0 | 0 | 0 |

## Per question / 每題

| # | Type | First token A → B | Total A → B | Files A → B | Code A → B | Def. A → B | Keywords A → B | Simplified A / B | Manual A / B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 定位設定 | 18.6 s → 21.4 s | 23.7 s → 25.7 s | 1/3 → 1/3 | 0/2 → 1/2 | 0/1 → 1/1 | 1/5 → 3/5 | — / — | — / — |
| 2 | 解釋邏輯 | 17.0 s → 17.1 s | 28.6 s → 28.3 s | 0/3 → 0/3 | 0/2 → 0/2 | — → — | 1/4 → 0/4 | — / — | — / — |
| 3 | 解釋邏輯 | 3.9 s → 53.2 s | 14.0 s → 74.1 s | 1/2 → 2/2 | 0/1 → 1/1 | — → — | 4/5 → 5/5 | — / — | — / — |
| 4 | 跨檔案流程 | 11.9 s → 18.9 s | 17.3 s → 38.3 s | 0/2 → 0/2 | 0/2 → 0/2 | — → — | 0/5 → 2/5 | — / — | — / — |
| 5 | 跨檔案流程 | 11.7 s → 23.3 s | 17.8 s → 33.5 s | 0/2 → 2/2 | 0/2 → 2/2 | — → — | 1/4 → 2/4 | — / — | — / — |
| 6 | 跨檔案流程 | 16.1 s → 21.1 s | 25.8 s → 32.3 s | 2/4 → 2/4 | 1/3 → 1/3 | — → — | 2/4 → 2/4 | — / — | — / — |
| 7 | 解釋邏輯 | 11.3 s → 13.8 s | 17.5 s → 18.8 s | 0/2 → 1/2 | 0/2 → 1/2 | — → — | 0/4 → 0/4 | — / — | — / — |
| 8 | 定位設定 | 16.2 s → 54.5 s | 23.9 s → 70.1 s | 0/3 → 2/3 | 0/3 → 2/3 | 0/2 → 1/2 | 1/5 → 1/5 | — / — | — / — |
| 9 | 定位設定 | 15.0 s → 23.7 s | 17.8 s → 26.2 s | 0/2 → 2/2 | 0/2 → 2/2 | 0/1 → 1/1 | 0/3 → 1/3 | 体 / — | — / — |
| 10 | 陷阱題 | 8.6 s → 20.9 s | 22.9 s → 59.8 s | — → — | — → — | — → — | 1/1 → 1/1 | — / — | — / — |
