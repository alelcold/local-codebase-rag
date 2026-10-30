export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export const lerp = (a, b, t) => a + (b - a) * t;
