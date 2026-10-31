import { useSyncExternalStore } from "react";
import type { UiStore } from "../game/store";

interface HudProps {
  store: UiStore;
}

/** Score, lives, level and combo, drawn over the canvas. */
export function Hud({ store }: HudProps) {
  const ui = useSyncExternalStore(store.subscribe, store.get);
  if (ui.phase === "title") return null;

  return (
    <div className="hud">
      <div className="hud-left">
        <span className="score">{ui.score.toLocaleString()}</span>
        {ui.comboMultiplier > 1 && <span className="combo">×{ui.comboMultiplier.toFixed(2)}</span>}
      </div>
      <div className="hud-center">
        Lv.{ui.level} {ui.levelName}
      </div>
      <div className="hud-right">
        <Lives count={ui.lives} />
        <span className={ui.dashReady ? "dash ready" : "dash"}>DASH</span>
      </div>
    </div>
  );
}

function Lives({ count }: { count: number }) {
  return (
    <span className="lives" aria-label={`${count} lives`}>
      {Array.from({ length: Math.max(0, count) }, (_, i) => (
        <span key={i} className="life" />
      ))}
    </span>
  );
}
