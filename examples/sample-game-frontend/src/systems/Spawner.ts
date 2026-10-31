import { WORLD_HEIGHT, WORLD_WIDTH } from "../config/gameConfig";
import { getLevel } from "../config/levels.js";
import { Asteroid } from "../entities/Asteroid";
import { Package } from "../entities/Package";
import { normalize, randomRange } from "../utils/math.js";

/** Spawns asteroids from the screen edges and packages inside the play area, paced by the current level. */
export class Spawner {
  private asteroidTimer = 0;
  private packageTimer = 0;

  update(dt: number, level: number, asteroids: Asteroid[], packages: Package[]): void {
    const config = getLevel(level);

    this.asteroidTimer -= dt;
    if (this.asteroidTimer <= 0) {
      asteroids.push(this.spawnAsteroid(config.asteroidSpeed));
      this.asteroidTimer = config.asteroidInterval;
    }

    this.packageTimer -= dt;
    if (this.packageTimer <= 0) {
      packages.push(new Package(randomRange(60, WORLD_WIDTH - 60), randomRange(60, WORLD_HEIGHT - 60)));
      this.packageTimer = config.packageInterval;
    }
  }

  reset(): void {
    this.asteroidTimer = 0;
    this.packageTimer = 1;
  }

  /** Picks a random edge, then aims roughly at the center of the screen. */
  private spawnAsteroid([minSpeed, maxSpeed]: readonly number[]): Asteroid {
    const edge = Math.floor(Math.random() * 4);
    const x = edge === 0 ? -40 : edge === 1 ? WORLD_WIDTH + 40 : randomRange(0, WORLD_WIDTH);
    const y = edge === 2 ? -40 : edge === 3 ? WORLD_HEIGHT + 40 : randomRange(0, WORLD_HEIGHT);
    const targetX = WORLD_WIDTH / 2 + randomRange(-200, 200);
    const targetY = WORLD_HEIGHT / 2 + randomRange(-120, 120);
    const [dx, dy] = normalize(targetX - x, targetY - y);
    const speed = randomRange(minSpeed, maxSpeed);
    return new Asteroid(x, y, dx * speed, dy * speed, randomRange(14, 34), randomRange(-2, 2));
  }
}
