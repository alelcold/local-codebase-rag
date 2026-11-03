# Evaluation comparison / 評估比較

- **A**: `codespace-3b-k4-split` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · split (docs ≤ 1) · prompt v1
- **B**: `codespace-3b-k4-hybrid-split-rerank` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · hybrid (RRF k=60) + split (docs ≤ 1) + rerank (BAAI/bge-reranker-base, 10 → 4) · prompt v1

Δ = B − A. ▲ better, ▼ worse. Automatic metrics are proxies, not correctness (ADR 0012).
Δ = B − A。▲ 較好、▼ 較差。自動指標只是代理指標，不等於回答正確（ADR 0012）。

## Summary / 摘要

| Metric / 指標 | A | B | Δ |
| --- | --- | --- | --- |
| Time to first token, mean / 首字延遲平均 | 15.9 s | 26.8 s | +10.9 s ▼ |
| Time to first token, median / 首字延遲中位數 | 12.5 s | 21.3 s | +8.8 s ▼ |
| Total time, mean / 總耗時平均 | 25.7 s | 40.7 s | +15.0 s ▼ |
| Rerank time, mean / rerank 耗時平均 | — | 4.8 s | — |
| Tokens, mean / 平均 token 數 | 109.0 | 141.3 | +32.3 |
| Expected-file recall / 預期檔案命中率 | 40% | 56% | +16 pt ▲ |
| Code file retrieved / 程式碼檔命中 | 67% | 78% | +11 pt ▲ |
| Doc file retrieved / 文件檔命中 | 50% | 50% | 0 |
| Defining file retrieved / 定義檔命中 | 33% | 100% | +67 pt ▲ |
| Expected file cited with [n] / 回答引用預期檔案 | 11% | 22% | +11 pt ▲ |
| Docs among retrieved chunks / 取回片段中文件比例 | 25% | 22% | -2 pt |
| Keyword hit rate / 關鍵字命中率 | 28% | 45% | +18 pt ▲ |
| Answers with Simplified / 混入簡體字的回答 | 3 | 0 | -3 ▲ |
| Trick question refused / 陷阱題正確拒答 | 0% | 0% | 0 |
| Refused by SCORE_THRESHOLD / 因門檻直接拒答 | — | 0 | — |
| Manual correctness / 人工判定正確性 | — | — | — |
| Errors / 失敗題數 | 0 | 0 | 0 |

## Per question / 每題

| # | Type | First token A → B | Total A → B | Files A → B | Code A → B | Def. A → B | Keywords A → B | Simplified A / B | Manual A / B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 定位設定 | 16.8 s → 21.4 s | 23.0 s → 25.7 s | 0/3 → 1/3 | 0/2 → 1/2 | 0/1 → 1/1 | 0/5 → 3/5 | 体码 / — | — / — |
| 2 | 解釋邏輯 | 9.3 s → 17.1 s | 14.2 s → 28.3 s | 0/3 → 0/3 | 0/2 → 0/2 | — → — | 1/4 → 0/4 | — / — | — / — |
| 3 | 解釋邏輯 | 47.2 s → 53.2 s | 59.6 s → 74.1 s | 2/2 → 2/2 | 1/1 → 1/1 | — → — | 4/5 → 5/5 | — / — | — / — |
| 4 | 跨檔案流程 | 13.1 s → 18.9 s | 18.9 s → 38.3 s | 0/2 → 0/2 | 0/2 → 0/2 | — → — | 0/5 → 2/5 | 义为这个随关变过后频会 / — | — / — |
| 5 | 跨檔案流程 | 13.1 s → 23.3 s | 25.3 s → 33.5 s | 1/2 → 2/2 | 1/2 → 2/2 | — → — | 3/4 → 2/4 | — / — | — / — |
| 6 | 跨檔案流程 | 19.9 s → 21.1 s | 32.4 s → 32.3 s | 3/4 → 2/4 | 2/3 → 1/3 | — → — | 3/4 → 2/4 | — / — | — / — |
| 7 | 解釋邏輯 | 7.5 s → 13.8 s | 21.4 s → 18.8 s | 1/2 → 1/2 | 1/2 → 1/2 | — → — | 0/4 → 0/4 | — / — | — / — |
| 8 | 定位設定 | 9.2 s → 54.5 s | 17.8 s → 70.1 s | 1/3 → 2/3 | 1/3 → 2/3 | 1/2 → 1/2 | 1/5 → 1/5 | — / — | — / — |
| 9 | 定位設定 | 11.9 s → 23.7 s | 14.4 s → 26.2 s | 1/2 → 2/2 | 1/2 → 2/2 | 0/1 → 1/1 | 0/3 → 1/3 | 于体来说储当 / — | — / — |
| 10 | 陷阱題 | 11.2 s → 20.9 s | 30.0 s → 59.8 s | — → — | — → — | — → — | 0/1 → 1/1 | — / — | — / — |
