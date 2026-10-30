import React from "react";

interface HudProps {
  score: number;
  lives: number;
}

export const Hud = ({ score, lives }: HudProps) => (
  <div className="hud">
    <span>Score: {score}</span>
    <span>Lives: {lives}</span>
  </div>
);

export default function GameOver() {
  return <h1>Game Over</h1>;
}
