import {
  COMBO_STEP,
  COMBO_WINDOW_MS,
  MAX_COMBO_MULTIPLIER,
  PACKAGE_SCORE,
  SURVIVAL_POINTS_PER_SECOND,
} from "../config/gameConfig";

/**
 * Score and combo bookkeeping.
 * multiplier = 1 + combo * COMBO_STEP, capped at MAX_COMBO_MULTIPLIER.
 * The combo resets when no package is collected within COMBO_WINDOW_MS or the player is hit.
 */
export class ScoreSystem {
  score = 0;
  combo = 0;
  packagesCollected = 0;
  private sinceLastPickupMs = 0;
  private survivalAccumulator = 0;

  get multiplier(): number {
    return Math.min(MAX_COMBO_MULTIPLIER, 1 + this.combo * COMBO_STEP);
  }

  update(dt: number): void {
    this.sinceLastPickupMs += dt * 1000;
    if (this.combo > 0 && this.sinceLastPickupMs > COMBO_WINDOW_MS) {
      this.combo = 0;
    }

    // Survival bonus is awarded in whole points once per accumulated second.
    this.survivalAccumulator += dt;
    while (this.survivalAccumulator >= 1) {
      this.survivalAccumulator -= 1;
      this.score += SURVIVAL_POINTS_PER_SECOND;
    }
  }

  /** Returns the points awarded for this pickup. */
  onPackageCollected(): number {
    const points = Math.round(PACKAGE_SCORE * this.multiplier);
    this.score += points;
    this.combo += 1;
    this.packagesCollected += 1;
    this.sinceLastPickupMs = 0;
    return points;
  }

  onPlayerHit(): void {
    this.combo = 0;
  }

  reset(): void {
    this.score = 0;
    this.combo = 0;
    this.packagesCollected = 0;
    this.sinceLastPickupMs = 0;
    this.survivalAccumulator = 0;
  }
}
