# SCORE_THRESHOLD calibration / 相似度門檻校準

Not used / 未使用的報告（not counted below / 不列入下方統計）：

- 2026-11-03-codespace-3b-k4-all-ident.json: not used, no cosine scores (a hybrid run written before vector_score existed stores only RRF scores)
- 2026-11-03-codespace-3b-k4-all.json: not used, no cosine scores (a hybrid run written before vector_score existed stores only RRF scores)
- 2026-11-03-codespace-3b-k4-hybrid-ident.json: not used, no cosine scores (a hybrid run written before vector_score existed stores only RRF scores)
- 2026-11-03-codespace-3b-k4-hybrid.json: not used, no cosine scores (a hybrid run written before vector_score existed stores only RRF scores)

## Embedding `nomic-embed-text`

Reports used (4) / 使用的報告: `2026-11-03-codespace-3b-k4-baseline-ident.json`, `2026-11-03-codespace-3b-k4-baseline.json`, `2026-11-03-codespace-3b-k4-split-ident.json`, `2026-11-03-codespace-3b-k4-split.json`

### Cosine distribution / 分數分布

| Excerpts / 片段 | Cosine |
| --- | --- |
| Expected file / 預期檔案 | n=27 · min 0.487 · p25 0.559 · median 0.616 · p75 0.679 · max 0.745 |
| Other file / 非預期檔案 | n=63 · min 0.466 · p25 0.565 · median 0.604 · p75 0.646 · max 0.759 |
| Trick question (should be refused) / 陷阱題 | n=7 · min 0.478 · p25 0.486 · median 0.542 · p75 0.567 · max 0.570 |

Lowest expected excerpts (what a threshold would cut first) / 分數最低的預期片段：

- 0.487 `src/game/Game.ts:14-35` — 遊戲主迴圈的流程是什麼？怎麼做到不受畫面更新率影響？
- 0.492 `src/game/Game.ts:102-118` — 遊戲主迴圈的流程是什麼？怎麼做到不受畫面更新率影響？
- 0.519 `src/game/Game.ts:86-100` — 最高分存在哪裡？
- 0.540 `src/game/Game.ts:61-64` — 碰撞偵測是怎麼實作的？
- 0.550 `src/game/Game.ts:86-100` — 遊戲中按 Esc 暫停之後發生什麼事？恢復時又做了什麼？

### Candidates / 候選門檻

| Threshold | Expected dropped / 丟掉的正確片段 | Not-expected blocked / 擋掉的非預期片段 | Questions losing every expected excerpt / 失去所有預期片段的題目 | Trick refused / 陷阱題拒答 |
| --- | --- | --- | --- | --- |
| 0.30 | 0/27 (0%) | 0/70 (0%) | 0 | 0/1 |
| 0.35 | 0/27 (0%) | 0/70 (0%) | 0 | 0/1 |
| 0.40 | 0/27 (0%) | 0/70 (0%) | 0 | 0/1 |
| 0.45 | 0/27 (0%) | 0/70 (0%) | 0 | 0/1 |
| 0.50 | 2/27 (7%) | 10/70 (14%) | 0 | 0/1 |
| 0.55 | 4/27 (15%) | 18/70 (26%) | 2: 最高分存在哪裡？; 碰撞偵測是怎麼實作的？ | 0/1 |
| 0.60 | 13/27 (48%) | 36/70 (51%) | 6: INVINCIBLE_MS 在哪裡定義？值是多少？在哪裡用到？; 最高分存在哪裡？; 玩家受傷後的無敵時間在哪裡設定？是多久？; 碰撞偵測是怎麼實作的？; 衝刺（dash）怎麼運作？按哪個鍵、速度、持續時間、冷卻時間？; 遊戲中按 Esc 暫停之後發生什麼事？恢復時又做了什麼？ | 1/1 |
| 0.65 | 18/27 (67%) | 58/70 (83%) | 7: INVINCIBLE_MS 在哪裡定義？值是多少？在哪裡用到？; 最高分存在哪裡？; 玩家受傷後的無敵時間在哪裡設定？是多久？; 碰撞偵測是怎麼實作的？; 衝刺（dash）怎麼運作？按哪個鍵、速度、持續時間、冷卻時間？; 遊戲中按 Esc 暫停之後發生什麼事？恢復時又做了什麼？; 遊戲主迴圈的流程是什麼？怎麼做到不受畫面更新率影響？ | 1/1 |
| 0.70 | 25/27 (93%) | 69/70 (99%) | 10: DASH_COOLDOWN_MS 和 DASH_DURATION_MS 在哪裡設定？各是多少？; HIGH_SCORE_KEY 定義在哪裡？最高分怎麼存？; INVINCIBLE_MS 在哪裡定義？值是多少？在哪裡用到？; getLevel 在哪裡定義？Spawner 怎麼用它？; 最高分存在哪裡？; 玩家受傷後的無敵時間在哪裡設定？是多久？; 碰撞偵測是怎麼實作的？; 衝刺（dash）怎麼運作？按哪個鍵、速度、持續時間、冷卻時間？; 遊戲中按 Esc 暫停之後發生什麼事？恢復時又做了什麼？; 遊戲主迴圈的流程是什麼？怎麼做到不受畫面更新率影響？ | 1/1 |
| 0.75 | 27/27 (100%) | 69/70 (99%) | 12: DASH_COOLDOWN_MS 和 DASH_DURATION_MS 在哪裡設定？各是多少？; HIGH_SCORE_KEY 定義在哪裡？最高分怎麼存？; INVINCIBLE_MS 在哪裡定義？值是多少？在哪裡用到？; React 的 HUD 怎麼取得遊戲資料，又不會每一幀都重新 render？; ScoreSystem 的 multiplier 怎麼計算？; getLevel 在哪裡定義？Spawner 怎麼用它？; 最高分存在哪裡？; 玩家受傷後的無敵時間在哪裡設定？是多久？; 碰撞偵測是怎麼實作的？; 衝刺（dash）怎麼運作？按哪個鍵、速度、持續時間、冷卻時間？; 遊戲中按 Esc 暫停之後發生什麼事？恢復時又做了什麼？; 遊戲主迴圈的流程是什麼？怎麼做到不受畫面更新率影響？ | 1/1 |
| 0.80 | 27/27 (100%) | 70/70 (100%) | 12: DASH_COOLDOWN_MS 和 DASH_DURATION_MS 在哪裡設定？各是多少？; HIGH_SCORE_KEY 定義在哪裡？最高分怎麼存？; INVINCIBLE_MS 在哪裡定義？值是多少？在哪裡用到？; React 的 HUD 怎麼取得遊戲資料，又不會每一幀都重新 render？; ScoreSystem 的 multiplier 怎麼計算？; getLevel 在哪裡定義？Spawner 怎麼用它？; 最高分存在哪裡？; 玩家受傷後的無敵時間在哪裡設定？是多久？; 碰撞偵測是怎麼實作的？; 衝刺（dash）怎麼運作？按哪個鍵、速度、持續時間、冷卻時間？; 遊戲中按 Esc 暫停之後發生什麼事？恢復時又做了什麼？; 遊戲主迴圈的流程是什麼？怎麼做到不受畫面更新率影響？ | 1/1 |

### Suggestion / 建議

**No value suggested / 不建議數值.** Every safe candidate (≤ 0.45) blocks no not-expected excerpt: a threshold would do nothing on this data. 安全的候選值都擋不到任何非預期片段，門檻在這些資料上沒有作用。
