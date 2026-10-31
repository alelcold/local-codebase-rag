# Starlight Courier（範例專案）

這是一個用來測試 Codebase RAG 流程的小型遊戲前端專案。玩家駕駛快遞飛船，在小行星帶中收集包裹並送達。

> 這個資料夾只是索引用的範例程式碼，不需要也無法單獨建置執行。

## 技術

- TypeScript + Canvas 2D 繪製遊戲畫面
- React 負責 HUD 與選單（疊在 canvas 上）
- 固定時間步長（fixed timestep）的遊戲主迴圈

## 目錄

| 路徑 | 內容 |
| --- | --- |
| `src/main.ts` | 進入點：建立 canvas、Game 與 React UI |
| `src/game/` | 主迴圈、遊戲狀態、UI 用的 store |
| `src/entities/` | 玩家、小行星、包裹 |
| `src/systems/` | 碰撞、輸入、計分、生成 |
| `src/config/` | 遊戲參數與關卡設定 |
| `src/ui/` | React 元件（HUD、暫停選單） |
| `src/audio/` | 音效管理 |
| `docs/` | 架構與玩法說明 |

## 可以試著問的問題

- 玩家受傷後的無敵時間在哪裡設定？
- 分數和連擊倍率是怎麼計算的？
- 遊戲主迴圈的流程是什麼？
- 小行星的生成頻率怎麼隨關卡變化？
- 按 Esc 暫停之後發生了什麼事？
