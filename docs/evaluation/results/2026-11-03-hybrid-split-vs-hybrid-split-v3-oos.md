# Evaluation comparison / 評估比較

- **A**: `codespace-3b-k4-hybrid-split-oos` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · hybrid (RRF k=60) + split (docs ≤ 1) · prompt v1
- **B**: `codespace-3b-k4-hybrid-split-v3-oos` · 2026-11-03 · qwen2.5-coder:3b · top_k default 4 · zh · hybrid (RRF k=60) + split (docs ≤ 1) · prompt v3

Δ = B − A. ▲ better, ▼ worse. Automatic metrics are proxies, not correctness (ADR 0012).
Δ = B − A。▲ 較好、▼ 較差。自動指標只是代理指標，不等於回答正確（ADR 0012）。

## Summary / 摘要

| Metric / 指標 | A | B | Δ |
| --- | --- | --- | --- |
| Time to first token, mean / 首字延遲平均 | 19.1 s | 14.8 s | -4.2 s ▲ |
| Time to first token, median / 首字延遲中位數 | 19.9 s | 15.3 s | -4.6 s ▲ |
| Total time, mean / 總耗時平均 | 39.8 s | 15.9 s | -23.9 s ▲ |
| Rerank time, mean / rerank 耗時平均 | — | — | — |
| Tokens, mean / 平均 token 數 | 188.9 | 11.0 | -177.9 |
| Expected-file recall / 預期檔案命中率 | 17% | 17% | 0 |
| Code file retrieved / 程式碼檔命中 | 33% | 33% | 0 |
| Doc file retrieved / 文件檔命中 | — | — | — |
| Defining file retrieved / 定義檔命中 | 0% | 0% | 0 |
| Expected file cited with [n] / 回答引用預期檔案 | 33% | 0% | -33 pt ▼ |
| Docs among retrieved chunks / 取回片段中文件比例 | 25% | 25% | 0 |
| Keyword hit rate / 關鍵字命中率 | 12% | 62% | +50 pt ▲ |
| Answers with Simplified / 混入簡體字的回答 | 7 | 0 | -7 ▲ |
| Refusal rate, trick questions / 拒答率 | 20% | 100% | +80 pt ▲ |
| False refusal rate / 誤拒率 | 0% | 100% | +100 pt ▼ |
| Refused by SCORE_THRESHOLD / 因門檻直接拒答 | 0 | 0 | 0 |
| Manual correctness / 人工判定正確性 | — | — | — |
| Errors / 失敗題數 | 0 | 0 | 0 |

## Per question / 每題

| # | Type | First token A → B | Total A → B | Files A → B | Code A → B | Def. A → B | Keywords A → B | Simplified A / B | Manual A / B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 21 | 陷阱題 | 23.5 s → 16.9 s | 48.0 s → 18.0 s | — → — | — → — | — → — | 0/1 → 1/1 | 档 / — | — / — |
| 22 | 陷阱題 | 10.0 s → 9.5 s | 15.9 s → 10.5 s | — → — | — → — | — → — | 0/1 → 1/1 | 无关于内细为这处务码阅统档开发队联获 / — | — / — |
| 23 | 陷阱題 | 33.7 s → 26.3 s | 47.0 s → 27.4 s | — → — | — → — | — → — | 0/1 → 1/1 | 数 / — | — / — |
| 24 | 陷阱題 | 21.8 s → 17.2 s | 26.9 s → 18.4 s | — → — | — → — | — → — | 1/1 → 1/1 | 据码没关于项档 / — | — / — |
| 25 | 陷阱題 | 18.8 s → 14.5 s | 54.9 s → 15.6 s | — → — | — → — | — → — | 0/1 → 1/1 | — / — | — / — |
| 26 | 對照題 | 21.0 s → 16.1 s | 85.4 s → 17.2 s | 1/2 → 1/2 | 1/2 → 1/2 | 0/1 → 0/1 | 0/2 → 0/2 | 没 / — | — / — |
| 27 | 對照題 | 7.5 s → 8.4 s | 15.4 s → 9.5 s | 0/1 → 0/1 | 0/1 → 0/1 | — → — | 0/2 → 0/2 | 体 / — | — / — |
| 28 | 對照題 | 16.2 s → 9.8 s | 25.1 s → 10.8 s | 0/1 → 0/1 | 0/1 → 0/1 | — → — | 0/3 → 0/3 | 码没处时键实现这应来点类个并数 / — | — / — |
