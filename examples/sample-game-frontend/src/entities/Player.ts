import {
  DASH_COOLDOWN_MS,
  DASH_DURATION_MS,
  DASH_SPEED,
  INVINCIBLE_BLINK_MS,
  INVINCIBLE_MS,
  PLAYER_MAX_LIVES,
  PLAYER_RADIUS,
  PLAYER_SPEED,
  WORLD_HEIGHT,
  WORLD_WIDTH,
} from "../config/gameConfig";
import type { InputManager } from "../systems/InputManager";
import { clamp, normalize } from "../utils/math.js";

/**
 * The courier ship controlled by the player.
 * Timers are tracked in milliseconds and counted down in update().
 */
export class Player {
  x = WORLD_WIDTH / 2;
  y = WORLD_HEIGHT / 2;
  radius = PLAYER_RADIUS;
  lives = PLAYER_MAX_LIVES;

  private invincibleMs = 0;
  private dashMs = 0;
  private dashCooldownMs = 0;
  private dashDir: [number, number] = [0, 0];

  /** True while the hit-invulnerability window or a dash is active. */
  get isInvincible(): boolean {
    return this.invincibleMs > 0 || this.dashMs > 0;
  }

  get dashReady(): boolean {
    return this.dashCooldownMs <= 0;
  }

  get isDead(): boolean {
    return this.lives <= 0;
  }

  update(dt: number, input: InputManager): void {
    const ms = dt * 1000;
    this.invincibleMs = Math.max(0, this.invincibleMs - ms);
    this.dashCooldownMs = Math.max(0, this.dashCooldownMs - ms);

    const [dx, dy] = normalize(input.axisX(), input.axisY());

    if (input.wasPressed("dash") && this.dashReady && (dx !== 0 || dy !== 0)) {
      this.startDash(dx, dy);
    }

    if (this.dashMs > 0) {
      this.dashMs = Math.max(0, this.dashMs - ms);
      this.x += this.dashDir[0] * DASH_SPEED * dt;
      this.y += this.dashDir[1] * DASH_SPEED * dt;
    } else {
      this.x += dx * PLAYER_SPEED * dt;
      this.y += dy * PLAYER_SPEED * dt;
    }

    this.x = clamp(this.x, this.radius, WORLD_WIDTH - this.radius);
    this.y = clamp(this.y, this.radius, WORLD_HEIGHT - this.radius);
  }

  /**
   * Applies one hit. Returns false if the hit was ignored because the
   * player is currently invincible (recently hit or dashing).
   */
  takeDamage(): boolean {
    if (this.isInvincible) {
      return false;
    }
    this.lives -= 1;
    this.invincibleMs = INVINCIBLE_MS;
    return true;
  }

  render(ctx: CanvasRenderingContext2D, timeMs: number): void {
    // Blink while invulnerable after a hit.
    if (this.invincibleMs > 0 && Math.floor(timeMs / INVINCIBLE_BLINK_MS) % 2 === 0) {
      return;
    }
    ctx.save();
    ctx.translate(this.x, this.y);
    ctx.fillStyle = this.dashMs > 0 ? "#9be7ff" : "#f5f1e6";
    ctx.beginPath();
    ctx.moveTo(this.radius, 0);
    ctx.lineTo(-this.radius * 0.8, this.radius * 0.7);
    ctx.lineTo(-this.radius * 0.4, 0);
    ctx.lineTo(-this.radius * 0.8, -this.radius * 0.7);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  reset(): void {
    this.x = WORLD_WIDTH / 2;
    this.y = WORLD_HEIGHT / 2;
    this.lives = PLAYER_MAX_LIVES;
    this.invincibleMs = 0;
    this.dashMs = 0;
    this.dashCooldownMs = 0;
  }

  private startDash(dx: number, dy: number): void {
    this.dashDir = [dx, dy];
    this.dashMs = DASH_DURATION_MS;
    this.dashCooldownMs = DASH_COOLDOWN_MS;
  }
}
