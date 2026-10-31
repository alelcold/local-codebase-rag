# Evaluation questions (sample project)

> English first; 繁體中文版本在下方.
> Target: `examples/sample-game-frontend/` (index it with the default `PROJECT_PATH`). Never put company code in this file.

## How to run

1. Index the sample project (`./scripts/index.sh --full`) and record the model and settings in the run header below.
2. Ask each question **exactly as written**, in the language you are testing. Use the Chinese wording for the main run, because the team asks in Chinese. Keep `top_k` at its default (8) unless the run is testing `top_k`.
3. Score each answer:
   - **Correctness** (0–2): 2 = all key facts right; 1 = partly right or missing a key fact; 0 = wrong or hallucinated.
   - **Citation** (✔/✘): ✔ when at least one cited `[n]` points to an expected file, and the cited lines actually contain the fact.
   - **Seconds**: time from submit to complete answer. Mark the first query after model load with `*`.
4. Copy the totals into [`../metrics.md`](../metrics.md), section 4.

Expected line ranges are the chunk ranges at the time of writing (`CHUNK_MAX_CHARS=3000`). Accept any citation inside the listed file and symbol, even if the line numbers have shifted.

## Questions

| # | Question (EN) | 問題（中文） | Key facts the answer must contain | Expected citations (any of) | What it tests |
| --- | --- | --- | --- | --- | --- |
| 1 | Where is the invincibility time after the player gets hit configured, and how long is it? | 玩家受傷後的無敵時間在哪裡設定？是多久？ | `INVINCIBLE_MS = 1500` ms in `gameConfig.ts`; set in `Player.takeDamage()`; hits are ignored while `isInvincible` (also true while dashing) | `src/config/gameConfig.ts:1-26`; `src/entities/Player.ts:16-113` (`Player`); `docs/gameplay.md:10-14` | Constant lookup + usage across files |
| 2 | How is the combo multiplier calculated, and when does the combo reset? | 連擊倍率怎麼計算？什麼時候會歸零？ | `1 + combo × 0.25` (`COMBO_STEP`), capped at 4 (`MAX_COMBO_MULTIPLIER`); resets after `COMBO_WINDOW_MS` (2500 ms) without a pickup, or when the player is hit | `src/systems/ScoreSystem.ts:9-60` (`ScoreSystem`); `src/config/gameConfig.ts:1-26`; `docs/gameplay.md:16-21` | Formula extraction |
| 3 | Describe the main game loop. How does it stay frame-rate independent? | 遊戲主迴圈的流程是什麼？怎麼做到不受畫面更新率影響？ | `requestAnimationFrame` → `Game.frame`; elapsed time accumulated and `update()` run in fixed steps of `FIXED_DT` (1/60 s); frame time capped by `MAX_FRAME_TIME` (0.25 s); then `render()` once | `src/game/Game.ts:66-84` (`Game.frame`); `docs/architecture.md:1-9` | Explaining a flow |
| 4 | How does asteroid spawn frequency change between levels? What happens after the last level? | 小行星的生成頻率怎麼隨關卡變化？超過最後一關之後呢？ | Per-level `asteroidInterval` in `LEVELS` (1.2 → 0.9 → 0.6 → 0.4 s); beyond the last level `getLevel()` multiplies the interval by 0.9 per extra level, min 0.15 s; `Spawner.update` uses it | `src/config/levels.js:12-27` (`getLevel`); `src/config/levels.js:1-10`; `src/systems/Spawner.ts:7-44` | JS file + data table |
| 5 | What happens when the player presses Esc during play, and when they resume? | 遊戲中按 Esc 暫停之後發生什麼事？恢復時又做了什麼？ | Phase becomes `paused` via `setPhase`; loop keeps running but `update()` is not called; resume sets `accumulator = 0` so the game does not jump forward; `Overlay` shows "Paused" | `src/game/Game.ts:86-100` (`Game.handleGlobalInput`); `src/ui/Overlay.tsx:4-37` | State machine |
| 6 | How does the React HUD get game data without re-rendering every frame? | React 的 HUD 怎麼取得遊戲資料，又不會每一幀都重新 render？ | `createUiStore` external store; `set()` only notifies listeners when a value changed; `Hud` uses `useSyncExternalStore`; `Game.syncUi` writes to it | `src/game/store.ts:5-28` (`createUiStore`); `src/ui/Hud.tsx:8-28`; `docs/architecture.md:31-35` | Cross-layer design |
| 7 | How is collision detection implemented? | 碰撞偵測是怎麼實作的？ | Circle vs. circle; compares squared distance with squared radius sum (no `sqrt`); `findOverlaps` filters a list; used in `Game.handleCollisions` | `src/systems/collision.ts:7-13`; `src/systems/collision.ts:15-18`; `src/game/Game.ts:120-138` | Small utility lookup |
| 8 | How does the dash work: which key, how fast, how long, and the cooldown? | 衝刺（dash）怎麼運作？按哪個鍵、速度、持續時間、冷卻時間？ | Shift (`ShiftLeft`/`ShiftRight` → `dash`); requires a movement direction; `DASH_SPEED` 720 px/s, `DASH_DURATION_MS` 180, `DASH_COOLDOWN_MS` 900; player is invincible while dashing | `src/entities/Player.ts:16-113`; `src/config/gameConfig.ts:1-26`; `src/systems/InputManager.ts:3-16` | Combining 3 files |
| 9 | Where is the high score saved? | 最高分存在哪裡？ | `localStorage` under `HIGH_SCORE_KEY` = `"starlight-courier.highScore"`; written in `Game.gameOver()`; read in the `Game` constructor | `src/game/GameState.ts:14-14`; `src/game/Game.ts:145-151` (`Game.gameOver`); `src/game/Game.ts:37-49` | Persistence lookup |
| 10 | How does online multiplayer synchronize player positions? | 線上多人模式怎麼同步玩家位置？ | **Trick question**: there is no multiplayer or networking in this project. A correct answer says it cannot find this and does not invent code. | None. Any citation used to claim multiplayer exists counts as ✘. | Hallucination resistance |

## Score sheet

Copy this block once per run.

```text
Run: {YYYY-MM-DD} · Env: {Codespaces / Mac M2 / GPU} · LLM: {model} · Embed: {model} · top_k: {8} · Language: {zh / en}
```

| # | Correctness (0–2) | Citation (✔/✘) | Seconds | Notes |
| --- | --- | --- | --- | --- |
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | | | |
| 9 | | | | |
| 10 | | | | |
| **Total** | **/20** | **/10** | **avg** | |

---

# 評估問題（範例專案）

> 對象：`examples/sample-game-frontend/`（使用預設的 `PROJECT_PATH` 建立索引）。不得在此檔案放入公司程式碼。

## 執行方式

1. 為範例專案建立索引（`./scripts/index.sh --full`），並在下方的執行紀錄標頭寫下模型與設定。
2. 每題**完全照原文**提問，使用要測試的語言。主要評估用中文問，因為團隊是用中文提問。除非這次是在測試 `top_k`，否則維持預設值（8）。
3. 評分方式：
   - **正確性**（0–2）：2 = 關鍵事實全對；1 = 部分正確或缺少關鍵事實；0 = 錯誤或編造。
   - **引用**（✔／✘）：至少有一個 `[n]` 指向預期的檔案，而且引用的行確實包含該事實，才算 ✔。
   - **秒數**：從送出到回答完整出現的時間。模型載入後的第一次查詢以 `*` 標記。
4. 把總分抄到 [`../metrics.md`](../metrics.md) 第 4 節。

預期行號是撰寫時的片段範圍（`CHUNK_MAX_CHARS=3000`）。即使行號有變動，只要引用落在列出的檔案與符號內都算正確。

## 題目

| # | 問題 | 回答必須包含的關鍵事實 | 預期引用（任一即可） | 測試重點 |
| --- | --- | --- | --- | --- |
| 1 | 玩家受傷後的無敵時間在哪裡設定？是多久？ | `gameConfig.ts` 的 `INVINCIBLE_MS = 1500` 毫秒；在 `Player.takeDamage()` 設定；`isInvincible` 為真時（衝刺時也是）不會受傷 | `src/config/gameConfig.ts:1-26`；`src/entities/Player.ts:16-113`（`Player`）；`docs/gameplay.md:10-14` | 跨檔案找常數與用法 |
| 2 | 連擊倍率怎麼計算？什麼時候會歸零？ | `1 + 連擊數 × 0.25`（`COMBO_STEP`），最高 4 倍（`MAX_COMBO_MULTIPLIER`）；超過 `COMBO_WINDOW_MS`（2500 毫秒）沒有收集包裹，或玩家受傷時歸零 | `src/systems/ScoreSystem.ts:9-60`（`ScoreSystem`）；`src/config/gameConfig.ts:1-26`；`docs/gameplay.md:16-21` | 擷取公式 |
| 3 | 遊戲主迴圈的流程是什麼？怎麼做到不受畫面更新率影響？ | `requestAnimationFrame` → `Game.frame`；累加經過時間，以 `FIXED_DT`（1/60 秒）為單位執行 `update()`；單幀時間上限 `MAX_FRAME_TIME`（0.25 秒）；最後呼叫一次 `render()` | `src/game/Game.ts:66-84`（`Game.frame`）；`docs/architecture.md:1-9` | 說明流程 |
| 4 | 小行星的生成頻率怎麼隨關卡變化？超過最後一關之後呢？ | `LEVELS` 裡每關的 `asteroidInterval`（1.2 → 0.9 → 0.6 → 0.4 秒）；超過最後一關後，`getLevel()` 每多一關把間隔乘以 0.9，最低 0.15 秒；`Spawner.update` 使用這個值 | `src/config/levels.js:12-27`（`getLevel`）；`src/config/levels.js:1-10`；`src/systems/Spawner.ts:7-44` | JS 檔案＋資料表 |
| 5 | 遊戲中按 Esc 暫停之後發生什麼事？恢復時又做了什麼？ | 透過 `setPhase` 進入 `paused`；迴圈繼續跑，但不呼叫 `update()`；恢復時把 `accumulator` 設為 0，避免遊戲一下子往前跳；`Overlay` 顯示「Paused」 | `src/game/Game.ts:86-100`（`Game.handleGlobalInput`）；`src/ui/Overlay.tsx:4-37` | 狀態機 |
| 6 | React 的 HUD 怎麼取得遊戲資料，又不會每一幀都重新 render？ | `createUiStore` 外部 store；`set()` 只在數值改變時通知；`Hud` 使用 `useSyncExternalStore`；`Game.syncUi` 負責寫入 | `src/game/store.ts:5-28`（`createUiStore`）；`src/ui/Hud.tsx:8-28`；`docs/architecture.md:31-35` | 跨層設計 |
| 7 | 碰撞偵測是怎麼實作的？ | 圓形對圓形；比較距離平方與半徑和的平方（不開根號）；`findOverlaps` 過濾清單；在 `Game.handleCollisions` 中使用 | `src/systems/collision.ts:7-13`；`src/systems/collision.ts:15-18`；`src/game/Game.ts:120-138` | 小工具函式查找 |
| 8 | 衝刺（dash）怎麼運作？按哪個鍵、速度、持續時間、冷卻時間？ | Shift 鍵（`ShiftLeft`／`ShiftRight` → `dash`）；必須有移動方向；`DASH_SPEED` 720 px/s、`DASH_DURATION_MS` 180、`DASH_COOLDOWN_MS` 900；衝刺期間無敵 | `src/entities/Player.ts:16-113`；`src/config/gameConfig.ts:1-26`；`src/systems/InputManager.ts:3-16` | 整合 3 個檔案 |
| 9 | 最高分存在哪裡？ | `localStorage`，key 為 `HIGH_SCORE_KEY` = `"starlight-courier.highScore"`；在 `Game.gameOver()` 寫入；在 `Game` 建構子讀取 | `src/game/GameState.ts:14-14`；`src/game/Game.ts:145-151`（`Game.gameOver`）；`src/game/Game.ts:37-49` | 持久化查找 |
| 10 | 線上多人模式怎麼同步玩家位置？ | **陷阱題**：專案中沒有多人或網路功能。正確的回答應該說找不到，而不是編造程式碼。 | 無。用任何引用來宣稱有多人功能都算 ✘。 | 抗幻覺能力 |

## 計分表

每次執行複製一份。

```text
執行：{YYYY-MM-DD} · 環境：{Codespaces / Mac M2 / GPU} · LLM：{模型} · Embedding：{模型} · top_k：{8} · 語言：{中文 / 英文}
```

| # | 正確性（0–2） | 引用（✔／✘） | 秒數 | 備註 |
| --- | --- | --- | --- | --- |
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | | | |
| 9 | | | | |
| 10 | | | | |
| **總計** | **/20** | **/10** | **平均** | |
