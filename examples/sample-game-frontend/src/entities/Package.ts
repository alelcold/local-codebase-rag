/** A collectible delivery crate. Expires if not picked up in time. */
export class Package {
  static readonly LIFETIME_MS = 6000;
  readonly radius = 10;
  ageMs = 0;
  collected = false;

  constructor(
    public x: number,
    public y: number,
  ) {}

  update(dt: number): void {
    this.ageMs += dt * 1000;
  }

  get expired(): boolean {
    return this.ageMs >= Package.LIFETIME_MS;
  }

  render(ctx: CanvasRenderingContext2D): void {
    // Fade out during the last second of its life.
    const remaining = Package.LIFETIME_MS - this.ageMs;
    ctx.globalAlpha = remaining < 1000 ? remaining / 1000 : 1;
    ctx.fillStyle = "#ffcc4d";
    ctx.fillRect(this.x - this.radius, this.y - this.radius, this.radius * 2, this.radius * 2);
    ctx.globalAlpha = 1;
  }
}
