# Evaluation comparison / 評估比較

- **A**: `codespace-3b-k4-hybrid-split-ident` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · hybrid (RRF k=60) + split (docs ≤ 1) · prompt v1
- **B**: `codespace-3b-k4-hybrid-split-v3-ident` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · hybrid (RRF k=60) + split (docs ≤ 1) · prompt v3

Δ = B − A. ▲ better, ▼ worse. Automatic metrics are proxies, not correctness (ADR 0012).
Δ = B − A。▲ 較好、▼ 較差。自動指標只是代理指標，不等於回答正確（ADR 0012）。

## Summary / 摘要

| Metric / 指標 | A | B | Δ |
| --- | --- | --- | --- |
| Time to first token, mean / 首字延遲平均 | 19.9 s | 26.3 s | +6.4 s ▼ |
| Time to first token, median / 首字延遲中位數 | 14.5 s | 27.6 s | +13.1 s ▼ |
| Total time, mean / 總耗時平均 | 30.1 s | 31.2 s | +1.1 s ▼ |
| Rerank time, mean / rerank 耗時平均 | — | — | — |
| Tokens, mean / 平均 token 數 | 101.6 | 46.6 | -55.0 |
| Expected-file recall / 預期檔案命中率 | 90% | 90% | 0 |
| Code file retrieved / 程式碼檔命中 | 100% | 100% | 0 |
| Doc file retrieved / 文件檔命中 | — | — | — |
| Defining file retrieved / 定義檔命中 | 100% | 100% | 0 |
| Expected file cited with [n] / 回答引用預期檔案 | 80% | 40% | -40 pt ▼ |
| Docs among retrieved chunks / 取回片段中文件比例 | 25% | 25% | 0 |
| Keyword hit rate / 關鍵字命中率 | 83% | 48% | -35 pt ▼ |
| Answers with Simplified / 混入簡體字的回答 | 2 | 0 | -2 ▲ |
| Refusal rate, trick questions / 拒答率 | — | — | — |
| False refusal rate / 誤拒率 | — | 40% | — |
| Refused by SCORE_THRESHOLD / 因門檻直接拒答 | 0 | 0 | 0 |
| Manual correctness / 人工判定正確性 | — | — | — |
| Errors / 失敗題數 | 0 | 0 | 0 |

## Per question / 每題

| # | Type | First token A → B | Total A → B | Files A → B | Code A → B | Def. A → B | Keywords A → B | Simplified A / B | Manual A / B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | 定位設定 | 42.3 s → 51.7 s | 51.3 s → 53.0 s | 2/2 → 2/2 | 2/2 → 2/2 | 1/1 → 1/1 | 3/4 → 0/4 | 类 / — | — / — |
| 12 | 解釋邏輯 | 12.0 s → 27.6 s | 23.3 s → 38.8 s | 1/2 → 1/2 | 1/2 → 1/2 | — → — | 3/4 → 3/4 | — / — | — / — |
| 13 | 定位設定 | 4.6 s → 5.7 s | 11.5 s → 6.9 s | 2/2 → 2/2 | 2/2 → 2/2 | 1/1 → 1/1 | 4/4 → 0/4 | — / — | — / — |
| 14 | 定位設定 | 14.5 s → 14.1 s | 29.9 s → 21.3 s | 2/2 → 2/2 | 2/2 → 2/2 | 1/1 → 1/1 | 3/3 → 3/3 | 体计储状态设为 / — | — / — |
| 15 | 跨檔案流程 | 26.3 s → 32.3 s | 34.4 s → 36.0 s | 2/2 → 2/2 | 2/2 → 2/2 | — → — | 2/3 → 2/3 | — / — | — / — |
