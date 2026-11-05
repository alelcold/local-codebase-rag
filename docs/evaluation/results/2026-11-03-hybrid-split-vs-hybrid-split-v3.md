# Evaluation comparison / 評估比較

- **A**: `codespace-3b-k4-hybrid-split` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · hybrid (RRF k=60) + split (docs ≤ 1) · prompt v1
- **B**: `codespace-3b-k4-hybrid-split-v3` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · hybrid (RRF k=60) + split (docs ≤ 1) · prompt v3

Δ = B − A. ▲ better, ▼ worse. Automatic metrics are proxies, not correctness (ADR 0012).
Δ = B − A。▲ 較好、▼ 較差。自動指標只是代理指標，不等於回答正確（ADR 0012）。

## Summary / 摘要

| Metric / 指標 | A | B | Δ |
| --- | --- | --- | --- |
| Time to first token, mean / 首字延遲平均 | 17.2 s | 20.3 s | +3.1 s ▼ |
| Time to first token, median / 首字延遲中位數 | 12.8 s | 15.9 s | +3.1 s ▼ |
| Total time, mean / 總耗時平均 | 26.3 s | 23.2 s | -3.1 s ▲ |
| Rerank time, mean / rerank 耗時平均 | — | — | — |
| Tokens, mean / 平均 token 數 | 94.9 | 25.9 | -69.0 |
| Expected-file recall / 預期檔案命中率 | 45% | 45% | 0 |
| Code file retrieved / 程式碼檔命中 | 67% | 67% | 0 |
| Doc file retrieved / 文件檔命中 | 50% | 50% | 0 |
| Defining file retrieved / 定義檔命中 | 0% | 0% | 0 |
| Expected file cited with [n] / 回答引用預期檔案 | 33% | 0% | -33 pt ▼ |
| Docs among retrieved chunks / 取回片段中文件比例 | 25% | 25% | 0 |
| Keyword hit rate / 關鍵字命中率 | 28% | 18% | -10 pt ▼ |
| Answers with Simplified / 混入簡體字的回答 | 4 | 0 | -4 ▲ |
| Refusal rate, trick questions / 拒答率 | 0% | 100% | +100 pt ▲ |
| False refusal rate / 誤拒率 | 0% | 89% | +89 pt ▼ |
| Suspected fabrication / 疑似編造 | 4 | 0 | -4 ▲ |
| Refused by SCORE_THRESHOLD / 因門檻直接拒答 | 0 | 0 | 0 |
| Manual correctness / 人工判定正確性 | 7 | 3 | -4 |
| Errors / 失敗題數 | 0 | 0 | 0 |

## Per question / 每題

| # | Type | First token A → B | Total A → B | Files A → B | Code A → B | Def. A → B | Keywords A → B | Simplified A / B | Manual A / B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 定位設定 | 18.8 s → 19.8 s | 25.2 s → 20.9 s | 0/3 → 0/3 | 0/2 → 0/2 | 0/1 → 0/1 | 0/5 → 0/5 | 体码 / — | 0 / 0 |
| 2 | 解釋邏輯 | 10.4 s → 11.0 s | 15.5 s → 12.1 s | 0/3 → 0/3 | 0/2 → 0/2 | — → — | 1/4 → 0/4 | — / — | 0 / 0 |
| 3 | 解釋邏輯 | 52.9 s → 53.1 s | 67.3 s → 72.3 s | 2/2 → 2/2 | 1/1 → 1/1 | — → — | 4/5 → 4/5 | — / — | 2 / 1 |
| 4 | 跨檔案流程 | 14.6 s → 15.2 s | 22.4 s → 16.3 s | 0/2 → 0/2 | 0/2 → 0/2 | — → — | 0/5 → 0/5 | 义为这个频没随关变过后 / — | 0 / 0 |
| 5 | 跨檔案流程 | 7.0 s → 24.8 s | 17.0 s → 25.9 s | 2/2 → 2/2 | 2/2 → 2/2 | — → — | 2/4 → 0/4 | — / — | 2 / 0 |
| 6 | 跨檔案流程 | 22.5 s → 23.1 s | 29.8 s → 24.3 s | 3/4 → 3/4 | 2/3 → 2/3 | — → — | 2/4 → 0/4 | 并 / — | 2 / 0 |
| 7 | 解釋邏輯 | 8.5 s → 16.7 s | 19.3 s → 17.7 s | 1/2 → 1/2 | 1/2 → 1/2 | — → — | 0/4 → 0/4 | — / — | 0 / 0 |
| 8 | 定位設定 | 11.6 s → 12.6 s | 21.0 s → 13.8 s | 1/3 → 1/3 | 1/3 → 1/3 | 0/2 → 0/2 | 4/5 → 0/5 | — / — | 1 / 0 |
| 9 | 定位設定 | 13.2 s → 13.8 s | 14.8 s → 15.0 s | 1/2 → 1/2 | 1/2 → 1/2 | 0/1 → 0/1 | 0/3 → 0/3 | 于体 / — | 0 / 0 |
| 10 | 陷阱題 | 12.4 s → 13.1 s | 30.9 s → 14.3 s | — → — | — → — | — → — | 0/1 → 1/1 | — / — | 0 / 2 |
