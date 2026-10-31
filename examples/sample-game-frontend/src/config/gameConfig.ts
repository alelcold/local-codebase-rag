/** Fixed simulation step, in seconds. */
export const FIXED_DT = 1 / 60;
/** Upper bound on elapsed time processed per frame (avoids spiral of death). */
export const MAX_FRAME_TIME = 0.25;

export const WORLD_WIDTH = 960;
export const WORLD_HEIGHT = 540;

export const PLAYER_SPEED = 260; // px/s
export const PLAYER_RADIUS = 14;
export const PLAYER_MAX_LIVES = 3;
/** Invulnerability after taking a hit, in milliseconds. */
export const INVINCIBLE_MS = 1500;
/** Blink period while invulnerable, in milliseconds. */
export const INVINCIBLE_BLINK_MS = 100;

export const DASH_SPEED = 720; // px/s
export const DASH_DURATION_MS = 180;
export const DASH_COOLDOWN_MS = 900;

export const PACKAGE_SCORE = 100;
export const SURVIVAL_POINTS_PER_SECOND = 5;
export const COMBO_WINDOW_MS = 2500;
export const COMBO_STEP = 0.25;
export const MAX_COMBO_MULTIPLIER = 4;
export const PACKAGES_PER_LEVEL = 8;
