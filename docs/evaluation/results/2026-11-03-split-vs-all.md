# Evaluation comparison / 評估比較

- **A**: `codespace-3b-k4-split` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · split (docs ≤ 1) · prompt v1
- **B**: `codespace-3b-k4-all` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · hybrid (RRF k=60) + split (docs ≤ 1) + metadata · prompt v2

Δ = B − A. ▲ better, ▼ worse. Automatic metrics are proxies, not correctness (ADR 0012).
Δ = B − A。▲ 較好、▼ 較差。自動指標只是代理指標，不等於回答正確（ADR 0012）。

## Summary / 摘要

| Metric / 指標 | A | B | Δ |
| --- | --- | --- | --- |
| Time to first token, mean / 首字延遲平均 | 15.9 s | 19.6 s | +3.7 s ▼ |
| Time to first token, median / 首字延遲中位數 | 12.5 s | 16.4 s | +3.9 s ▼ |
| Total time, mean / 總耗時平均 | 25.7 s | 42.8 s | +17.1 s ▼ |
| Rerank time, mean / rerank 耗時平均 | — | — | — |
| Tokens, mean / 平均 token 數 | 109.0 | 241.0 | +132.0 |
| Expected-file recall / 預期檔案命中率 | 40% | 40% | 0 |
| Code file retrieved / 程式碼檔命中 | 67% | 56% | -11 pt ▼ |
| Doc file retrieved / 文件檔命中 | 50% | 50% | 0 |
| Defining file retrieved / 定義檔命中 | 33% | 0% | -33 pt ▼ |
| Expected file cited with [n] / 回答引用預期檔案 | 11% | 44% | +33 pt ▲ |
| Docs among retrieved chunks / 取回片段中文件比例 | 25% | 25% | 0 |
| Keyword hit rate / 關鍵字命中率 | 28% | 31% | +3 pt ▲ |
| Answers with Simplified / 混入簡體字的回答 | 3 | 2 | -1 ▲ |
| Refusal rate, trick questions / 拒答率 | 0% | 0% | 0 |
| False refusal rate / 誤拒率 | — | — | — |
| Refused by SCORE_THRESHOLD / 因門檻直接拒答 | — | — | — |
| Manual correctness / 人工判定正確性 | 7 | 6 | -1 |
| Errors / 失敗題數 | 0 | 0 | 0 |

## Per question / 每題

| # | Type | First token A → B | Total A → B | Files A → B | Code A → B | Def. A → B | Keywords A → B | Simplified A / B | Manual A / B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 定位設定 | 16.8 s → 14.0 s | 23.0 s → 17.8 s | 0/3 → 0/3 | 0/2 → 0/2 | 0/1 → 0/1 | 0/5 → 0/5 | 体码 / — | 0 / 0 |
| 2 | 解釋邏輯 | 9.3 s → 7.7 s | 14.2 s → 23.1 s | 0/3 → 0/3 | 0/2 → 0/2 | — → — | 1/4 → 0/4 | — / — | 0 / 0 |
| 3 | 解釋邏輯 | 47.2 s → 17.5 s | 59.6 s → 28.4 s | 2/2 → 2/2 | 1/1 → 1/1 | — → — | 4/5 → 4/5 | — / — | 2 / 2 |
| 4 | 跨檔案流程 | 13.1 s → 15.2 s | 18.9 s → 64.2 s | 0/2 → 0/2 | 0/2 → 0/2 | — → — | 0/5 → 0/5 | 义为这个随关变过后频会 / 体 | 0 / 0 |
| 5 | 跨檔案流程 | 13.1 s → 31.4 s | 25.3 s → 46.9 s | 1/2 → 2/2 | 1/2 → 2/2 | — → — | 3/4 → 3/4 | — / — | 2 / 1 |
| 6 | 跨檔案流程 | 19.9 s → 21.3 s | 32.4 s → 46.3 s | 3/4 → 3/4 | 2/3 → 2/3 | — → — | 3/4 → 3/4 | — / — | 2 / 2 |
| 7 | 解釋邏輯 | 7.5 s → 9.8 s | 21.4 s → 23.5 s | 1/2 → 0/2 | 1/2 → 0/2 | — → — | 0/4 → 0/4 | — / — | 0 / 0 |
| 8 | 定位設定 | 9.2 s → 47.2 s | 17.8 s → 91.3 s | 1/3 → 1/3 | 1/3 → 1/3 | 1/2 → 0/2 | 1/5 → 4/5 | — / 冲 | 1 / 1 |
| 9 | 定位設定 | 11.9 s → 19.7 s | 14.4 s → 26.5 s | 1/2 → 1/2 | 1/2 → 1/2 | 0/1 → 0/1 | 0/3 → 0/3 | 于体来说储当 / — | 0 / 0 |
| 10 | 陷阱題 | 11.2 s → 12.3 s | 30.0 s → 59.6 s | — → — | — → — | — → — | 0/1 → 0/1 | — / — | 0 / 0 |
