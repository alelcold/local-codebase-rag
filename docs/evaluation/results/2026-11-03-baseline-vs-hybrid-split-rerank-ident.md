# Evaluation comparison / 評估比較

- **A**: `codespace-3b-k4-baseline-ident` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · vector only (baseline) · prompt v1
- **B**: `codespace-3b-k4-hybrid-split-rerank-ident` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · hybrid (RRF k=60) + split (docs ≤ 1) + rerank (BAAI/bge-reranker-base, 10 → 4) · prompt v1

Δ = B − A. ▲ better, ▼ worse. Automatic metrics are proxies, not correctness (ADR 0012).
Δ = B − A。▲ 較好、▼ 較差。自動指標只是代理指標，不等於回答正確（ADR 0012）。

## Summary / 摘要

| Metric / 指標 | A | B | Δ |
| --- | --- | --- | --- |
| Time to first token, mean / 首字延遲平均 | 21.2 s | 26.3 s | +5.1 s ▼ |
| Time to first token, median / 首字延遲中位數 | 17.1 s | 22.8 s | +5.6 s ▼ |
| Total time, mean / 總耗時平均 | 27.4 s | 37.7 s | +10.3 s ▼ |
| Rerank time, mean / rerank 耗時平均 | — | 6.4 s | — |
| Tokens, mean / 平均 token 數 | 68.4 | 113.6 | +45.2 |
| Expected-file recall / 預期檔案命中率 | 50% | 90% | +40 pt ▲ |
| Code file retrieved / 程式碼檔命中 | 80% | 100% | +20 pt ▲ |
| Doc file retrieved / 文件檔命中 | — | — | — |
| Defining file retrieved / 定義檔命中 | 33% | 100% | +67 pt ▲ |
| Expected file cited with [n] / 回答引用預期檔案 | 40% | 40% | 0 |
| Docs among retrieved chunks / 取回片段中文件比例 | 60% | 15% | -45 pt |
| Keyword hit rate / 關鍵字命中率 | 57% | 77% | +20 pt ▲ |
| Answers with Simplified / 混入簡體字的回答 | 0 | 0 | 0 |
| Refusal rate, trick questions / 拒答率 | — | — | — |
| False refusal rate / 誤拒率 | 0% | 0% | 0 |
| Suspected fabrication / 疑似編造 | 1 | 0 | -1 ▲ |
| Refused by SCORE_THRESHOLD / 因門檻直接拒答 | 0 | 0 | 0 |
| Manual correctness / 人工判定正確性 | 6 | 9 | +3 |
| Errors / 失敗題數 | 0 | 0 | 0 |

## Per question / 每題

| # | Type | First token A → B | Total A → B | Files A → B | Code A → B | Def. A → B | Keywords A → B | Simplified A / B | Manual A / B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | 定位設定 | 17.1 s → 57.3 s | 22.4 s → 72.3 s | 0/2 → 2/2 | 0/2 → 2/2 | 0/1 → 1/1 | 1/4 → 3/4 | — / — | 0 / 1 |
| 12 | 解釋邏輯 | 25.6 s → 22.8 s | 34.4 s → 43.0 s | 1/2 → 1/2 | 1/2 → 1/2 | — → — | 3/4 → 3/4 | — / — | 2 / 2 |
| 13 | 定位設定 | 16.2 s → 26.1 s | 21.5 s → 32.2 s | 1/2 → 2/2 | 1/2 → 2/2 | 0/1 → 1/1 | 2/4 → 4/4 | — / — | 0 / 2 |
| 14 | 定位設定 | 14.6 s → 18.6 s | 18.2 s → 25.0 s | 1/2 → 2/2 | 1/2 → 2/2 | 1/1 → 1/1 | 2/3 → 2/3 | — / — | 2 / 2 |
| 15 | 跨檔案流程 | 32.4 s → 6.6 s | 40.7 s → 16.3 s | 2/2 → 2/2 | 2/2 → 2/2 | — → — | 2/3 → 2/3 | — / — | 2 / 2 |
