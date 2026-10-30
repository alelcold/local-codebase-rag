import { clamp } from "./util";

/** Gravity applied every frame, in px/s². */
export const GRAVITY = 1800;

/**
 * The controllable character.
 */
export class Player {
  x = 0;
  y = 0;
  vy = 0;

  /** Start a jump if the player is on the ground. */
  jump(): void {
    if (this.y === 0) {
      this.vy = -600;
    }
  }

  update(dt: number): void {
    this.vy += GRAVITY * dt;
    this.y = clamp(this.y + this.vy * dt, -10000, 0);
  }
}

export function createPlayer(): Player {
  return new Player();
}
