export interface Circle {
  x: number;
  y: number;
  radius: number;
}

/** Circle-vs-circle overlap test using squared distances (no sqrt). */
export function circlesOverlap(a: Circle, b: Circle): boolean {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  const r = a.radius + b.radius;
  return dx * dx + dy * dy < r * r;
}

/** Returns every item in `others` that overlaps `subject`. */
export function findOverlaps<T extends Circle>(subject: Circle, others: readonly T[]): T[] {
  return others.filter((o) => circlesOverlap(subject, o));
}
