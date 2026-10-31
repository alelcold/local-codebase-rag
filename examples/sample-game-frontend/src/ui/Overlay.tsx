import { useSyncExternalStore } from "react";
import type { UiStore } from "../game/store";

/** Title, pause and game-over screens. Input is handled by Game; this only renders. */
export function Overlay({ store }: { store: UiStore }) {
  const ui = useSyncExternalStore(store.subscribe, store.get);

  switch (ui.phase) {
    case "title":
      return (
        <div className="overlay">
          <h1>Starlight Courier</h1>
          <p>Collect packages, dodge the rocks.</p>
          <p className="hint">Press Enter to launch</p>
          {ui.highScore > 0 && <p className="best">Best: {ui.highScore.toLocaleString()}</p>}
        </div>
      );
    case "paused":
      return (
        <div className="overlay">
          <h2>Paused</h2>
          <p className="hint">Press Esc to resume</p>
        </div>
      );
    case "gameOver":
      return (
        <div className="overlay">
          <h2>Delivery Failed</h2>
          <p>Score: {ui.score.toLocaleString()}</p>
          {ui.score >= ui.highScore && ui.score > 0 && <p className="best">New best!</p>}
          <p className="hint">Press Enter to try again</p>
        </div>
      );
    default:
      return null;
  }
}
