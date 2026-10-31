import { SoundManager } from "../audio/SoundManager";
import { FIXED_DT, MAX_FRAME_TIME, PACKAGES_PER_LEVEL, WORLD_HEIGHT, WORLD_WIDTH } from "../config/gameConfig";
import { getLevel } from "../config/levels.js";
import { Asteroid } from "../entities/Asteroid";
import { Package } from "../entities/Package";
import { Player } from "../entities/Player";
import { findOverlaps } from "../systems/collision";
import { InputManager } from "../systems/InputManager";
import { ScoreSystem } from "../systems/ScoreSystem";
import { Spawner } from "../systems/Spawner";
import { HIGH_SCORE_KEY, type GamePhase } from "./GameState";
import { createUiStore, type UiStore } from "./store";

/**
 * Owns the world and runs the main loop.
 *
 * Loop: requestAnimationFrame -> frame() accumulates elapsed time and runs
 * update() in FIXED_DT steps (so physics is frame-rate independent), then
 * render() once. Phase changes go through setPhase() so the UI store stays in sync.
 */
export class Game {
  readonly ui: UiStore;
  private phase: GamePhase = "title";
  private player = new Player();
  private asteroids: Asteroid[] = [];
  private packages: Package[] = [];
  private score = new ScoreSystem();
  private spawner = new Spawner();
  private sound = new SoundManager();
  private input: InputManager;
  private level = 0;
  private accumulator = 0;
  private lastTime = 0;
  private elapsedMs = 0;
  private rafId = 0;

  constructor(private ctx: CanvasRenderingContext2D) {
    this.input = new InputManager();
    this.ui = createUiStore({
      phase: "title",
      score: 0,
      lives: this.player.lives,
      level: 1,
      levelName: getLevel(0).name,
      comboMultiplier: 1,
      dashReady: true,
      highScore: Number(localStorage.getItem(HIGH_SCORE_KEY) ?? 0),
    });
  }

  start(): void {
    this.lastTime = performance.now();
    this.rafId = requestAnimationFrame(this.frame);
  }

  stop(): void {
    cancelAnimationFrame(this.rafId);
    this.input.dispose();
  }

  setPhase(phase: GamePhase): void {
    this.phase = phase;
    this.ui.set({ phase });
  }

  private frame = (now: number): void => {
    const frameTime = Math.min((now - this.lastTime) / 1000, MAX_FRAME_TIME);
    this.lastTime = now;
    this.elapsedMs += frameTime * 1000;

    this.handleGlobalInput();

    if (this.phase === "playing") {
      this.accumulator += frameTime;
      while (this.accumulator >= FIXED_DT) {
        this.update(FIXED_DT);
        this.accumulator -= FIXED_DT;
      }
    }

    this.render();
    this.input.endFrame();
    this.rafId = requestAnimationFrame(this.frame);
  };

  /** Enter starts/restarts; Esc toggles pause. Runs every frame regardless of phase. */
  private handleGlobalInput(): void {
    if (this.input.wasPressed("confirm") && (this.phase === "title" || this.phase === "gameOver")) {
      this.sound.unlock();
      this.resetRun();
      this.setPhase("playing");
    } else if (this.input.wasPressed("pause")) {
      if (this.phase === "playing") this.setPhase("paused");
      else if (this.phase === "paused") {
        // Drop time accumulated while paused so the game doesn't jump forward.
        this.accumulator = 0;
        this.setPhase("playing");
      }
    }
  }

  private update(dt: number): void {
    const wasDashReady = this.player.dashReady;
    this.player.update(dt, this.input);
    if (wasDashReady && !this.player.dashReady) this.sound.play("dash");

    this.spawner.update(dt, this.level, this.asteroids, this.packages);
    this.asteroids.forEach((a) => a.update(dt));
    this.packages.forEach((p) => p.update(dt));
    this.score.update(dt);

    this.handleCollisions();

    this.asteroids = this.asteroids.filter((a) => !a.isOffscreen());
    this.packages = this.packages.filter((p) => !p.collected && !p.expired);

    this.syncUi();
  }

  private handleCollisions(): void {
    if (findOverlaps(this.player, this.asteroids).length > 0 && this.player.takeDamage()) {
      this.score.onPlayerHit();
      this.sound.play("hit");
      if (this.player.isDead) {
        this.gameOver();
        return;
      }
    }

    for (const pkg of findOverlaps(this.player, this.packages)) {
      pkg.collected = true;
      this.score.onPackageCollected();
      this.sound.play("pickup");
      if (this.score.packagesCollected % PACKAGES_PER_LEVEL === 0) {
        this.levelUp();
      }
    }
  }

  private levelUp(): void {
    this.level += 1;
    this.sound.play("levelUp");
  }

  private gameOver(): void {
    this.sound.play("gameOver");
    const best = Math.max(this.score.score, this.ui.get().highScore);
    localStorage.setItem(HIGH_SCORE_KEY, String(best));
    this.ui.set({ highScore: best });
    this.setPhase("gameOver");
  }

  private resetRun(): void {
    this.player.reset();
    this.score.reset();
    this.spawner.reset();
    this.asteroids = [];
    this.packages = [];
    this.level = 0;
    this.accumulator = 0;
    this.syncUi();
  }

  private syncUi(): void {
    this.ui.set({
      score: this.score.score,
      lives: this.player.lives,
      level: this.level + 1,
      levelName: getLevel(this.level).name,
      comboMultiplier: this.score.multiplier,
      dashReady: this.player.dashReady,
    });
  }

  private render(): void {
    const ctx = this.ctx;
    ctx.fillStyle = getLevel(this.level).background;
    ctx.fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
    this.packages.forEach((p) => p.render(ctx));
    this.asteroids.forEach((a) => a.render(ctx));
    if (this.phase !== "title") this.player.render(ctx, this.elapsedMs);
  }
}
