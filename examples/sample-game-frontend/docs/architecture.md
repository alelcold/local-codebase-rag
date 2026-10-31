# 架構說明

## 遊戲主迴圈

`Game`（`src/game/Game.ts`）使用固定時間步長：每一幀把經過的時間累加到 accumulator，
再以 `FIXED_DT`（1/60 秒）為單位呼叫 `update()`，最後呼叫一次 `render()`。
這樣物理與碰撞的結果不會因為螢幕更新率不同而改變。

為了避免分頁切回來時一次補跑太多步，單幀最多累積 `MAX_FRAME_TIME` 秒。

## 狀態機

遊戲狀態定義在 `src/game/GameState.ts`：

- `title`：標題畫面，按 Enter 開始
- `playing`：遊戲進行中
- `paused`：按 Esc 暫停，主迴圈仍在跑但不呼叫 `update()`
- `gameOver`：生命歸零

狀態切換一律透過 `Game.setPhase()`，它會同步更新 UI store。

## 系統

| 系統 | 檔案 | 職責 |
| --- | --- | --- |
| InputManager | `src/systems/InputManager.ts` | 鍵盤狀態、單次按下事件 |
| Spawner | `src/systems/Spawner.ts` | 依關卡設定生成小行星與包裹 |
| collision | `src/systems/collision.ts` | 圓形碰撞判定 |
| ScoreSystem | `src/systems/ScoreSystem.ts` | 分數、連擊倍率 |

## Canvas 與 React 的分工

Canvas 只負責畫遊戲世界；HUD、暫停選單等 UI 由 React 繪製。
兩者透過 `src/game/store.ts` 的小型 store 溝通：`Game` 寫入，React 用 `useSyncExternalStore` 訂閱。
store 只有在數值改變時才通知，避免每幀重新 render React。
