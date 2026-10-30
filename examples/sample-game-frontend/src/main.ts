import { createElement } from "react";
import { createRoot } from "react-dom/client";
import { WORLD_HEIGHT, WORLD_WIDTH } from "./config/gameConfig";
import { Game } from "./game/Game";
import { Hud } from "./ui/Hud";
import { Overlay } from "./ui/Overlay";

/** Entry point: sets up the canvas, starts the game loop and mounts the React UI layer. */
function bootstrap(): void {
  const canvas = document.querySelector<HTMLCanvasElement>("#game");
  const uiRoot = document.querySelector<HTMLDivElement>("#ui");
  if (!canvas || !uiRoot) {
    throw new Error("Missing #game canvas or #ui root element");
  }

  canvas.width = WORLD_WIDTH;
  canvas.height = WORLD_HEIGHT;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D not supported");

  const game = new Game(ctx);
  createRoot(uiRoot).render([
    createElement(Hud, { key: "hud", store: game.ui }),
    createElement(Overlay, { key: "overlay", store: game.ui }),
  ]);
  game.start();

  // Stop the loop when the page is hidden for good (e.g. bfcache eviction).
  window.addEventListener("pagehide", () => game.stop());
}

bootstrap();
