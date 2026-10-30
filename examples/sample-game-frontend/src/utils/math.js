export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export const lerp = (a, b, t) => a + (b - a) * t;

export function randomRange(min, max) {
  return min + Math.random() * (max - min);
}

/** Normalizes (x, y); returns [0, 0] for the zero vector. */
export function normalize(x, y) {
  const len = Math.hypot(x, y);
  return len === 0 ? [0, 0] : [x / len, y / len];
}
