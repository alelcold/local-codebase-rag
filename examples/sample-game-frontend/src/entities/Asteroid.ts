import { WORLD_HEIGHT, WORLD_WIDTH } from "../config/gameConfig";

/** A drifting rock. Spawned off-screen by the Spawner and removed once it leaves the world. */
export class Asteroid {
  rotation = 0;

  constructor(
    public x: number,
    public y: number,
    public vx: number,
    public vy: number,
    public radius: number,
    private spin: number,
  ) {}

  update(dt: number): void {
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.rotation += this.spin * dt;
  }

  isOffscreen(margin = 80): boolean {
    return (
      this.x < -margin || this.x > WORLD_WIDTH + margin || this.y < -margin || this.y > WORLD_HEIGHT + margin
    );
  }

  render(ctx: CanvasRenderingContext2D): void {
    ctx.save();
    ctx.translate(this.x, this.y);
    ctx.rotate(this.rotation);
    ctx.strokeStyle = "#a99c8a";
    ctx.lineWidth = 2;
    ctx.beginPath();
    const points = 7;
    for (let i = 0; i <= points; i++) {
      const angle = (i / points) * Math.PI * 2;
      const r = this.radius * (i % 2 === 0 ? 1 : 0.78);
      ctx.lineTo(Math.cos(angle) * r, Math.sin(angle) * r);
    }
    ctx.stroke();
    ctx.restore();
  }
}
