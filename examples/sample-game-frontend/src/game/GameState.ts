export type GamePhase = "title" | "playing" | "paused" | "gameOver";

export interface UiSnapshot {
  phase: GamePhase;
  score: number;
  lives: number;
  level: number;
  levelName: string;
  comboMultiplier: number;
  dashReady: boolean;
  highScore: number;
}

export const HIGH_SCORE_KEY = "starlight-courier.highScore";
