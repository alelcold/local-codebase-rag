/**
 * Level definitions. Later levels spawn asteroids more often and faster.
 * `asteroidInterval` is in seconds; speeds are in px/s.
 */
export const LEVELS = [
  { name: "Inner Belt", asteroidInterval: 1.2, asteroidSpeed: [80, 140], packageInterval: 2.5, background: "#0b1026" },
  { name: "Drift Fields", asteroidInterval: 0.9, asteroidSpeed: [100, 180], packageInterval: 2.8, background: "#120b26" },
  { name: "Shard Storm", asteroidInterval: 0.6, asteroidSpeed: [140, 230], packageInterval: 3.2, background: "#1e0b1f" },
  { name: "The Maw", asteroidInterval: 0.4, asteroidSpeed: [180, 300], packageInterval: 3.6, background: "#260b0b" },
];

/**
 * Returns the level config for a 0-based level index.
 * Past the last level, difficulty keeps scaling by shrinking the spawn interval.
 */
export function getLevel(index) {
  if (index < LEVELS.length) {
    return LEVELS[index];
  }
  const last = LEVELS[LEVELS.length - 1];
  const extra = index - LEVELS.length + 1;
  return {
    ...last,
    name: `${last.name} +${extra}`,
    asteroidInterval: Math.max(0.15, last.asteroidInterval * Math.pow(0.9, extra)),
  };
}
