# Evaluation comparison / 評估比較

- **A**: `codespace-3b-k4-baseline-ident` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · vector only (baseline) · prompt v1
- **B**: `codespace-3b-k4-split-ident` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · split (docs ≤ 1) · prompt v1

Δ = B − A. ▲ better, ▼ worse. Automatic metrics are proxies, not correctness (ADR 0012).
Δ = B − A。▲ 較好、▼ 較差。自動指標只是代理指標，不等於回答正確（ADR 0012）。

## Summary / 摘要

| Metric / 指標 | A | B | Δ |
| --- | --- | --- | --- |
| Time to first token, mean / 首字延遲平均 | 21.2 s | 17.8 s | -3.3 s ▲ |
| Time to first token, median / 首字延遲中位數 | 17.1 s | 11.2 s | -5.9 s ▲ |
| Total time, mean / 總耗時平均 | 27.4 s | 27.1 s | -0.4 s ▲ |
| Tokens, mean / 平均 token 數 | 68.4 | 99.2 | +30.8 |
| Expected-file recall / 預期檔案命中率 | 50% | 90% | +40 pt ▲ |
| Code file retrieved / 程式碼檔命中 | 80% | 100% | +20 pt ▲ |
| Doc file retrieved / 文件檔命中 | — | — | — |
| Defining file retrieved / 定義檔命中 | 33% | 100% | +67 pt ▲ |
| Expected file cited with [n] / 回答引用預期檔案 | 40% | 100% | +60 pt ▲ |
| Docs among retrieved chunks / 取回片段中文件比例 | 60% | 25% | -35 pt |
| Keyword hit rate / 關鍵字命中率 | 57% | 83% | +27 pt ▲ |
| Answers with Simplified / 混入簡體字的回答 | 0 | 0 | 0 |
| Trick question refused / 陷阱題正確拒答 | — | — | — |
| Manual correctness / 人工判定正確性 | — | — | — |
| Errors / 失敗題數 | 0 | 0 | 0 |

## Per question / 每題

| # | Type | First token A → B | Total A → B | Files A → B | Code A → B | Def. A → B | Keywords A → B | Simplified A / B | Manual A / B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | 定位設定 | 17.1 s → 42.9 s | 22.4 s → 49.8 s | 0/2 → 2/2 | 0/2 → 2/2 | 0/1 → 1/1 | 1/4 → 3/4 | — / — | — / — |
| 12 | 解釋邏輯 | 25.6 s → 8.7 s | 34.4 s → 27.6 s | 1/2 → 1/2 | 1/2 → 1/2 | — → — | 3/4 → 3/4 | — / — | — / — |
| 13 | 定位設定 | 16.2 s → 22.3 s | 21.5 s → 28.3 s | 1/2 → 2/2 | 1/2 → 2/2 | 0/1 → 1/1 | 2/4 → 4/4 | — / — | — / — |
| 14 | 定位設定 | 14.6 s → 11.2 s | 18.2 s → 17.5 s | 1/2 → 2/2 | 1/2 → 2/2 | 1/1 → 1/1 | 2/3 → 3/3 | — / — | — / — |
| 15 | 跨檔案流程 | 32.4 s → 4.0 s | 40.7 s → 12.2 s | 2/2 → 2/2 | 2/2 → 2/2 | — → — | 2/3 → 2/3 | — / — | — / — |
