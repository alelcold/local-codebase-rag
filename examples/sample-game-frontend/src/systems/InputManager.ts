export type Action = "up" | "down" | "left" | "right" | "dash" | "pause" | "confirm";

const KEY_BINDINGS: Record<string, Action> = {
  ArrowUp: "up",
  KeyW: "up",
  ArrowDown: "down",
  KeyS: "down",
  ArrowLeft: "left",
  KeyA: "left",
  ArrowRight: "right",
  KeyD: "right",
  ShiftLeft: "dash",
  ShiftRight: "dash",
  Escape: "pause",
  Enter: "confirm",
};

/**
 * Tracks which actions are held and which were pressed this frame.
 * Call endFrame() once per rendered frame to clear one-shot presses.
 */
export class InputManager {
  private held = new Set<Action>();
  private pressed = new Set<Action>();

  constructor(private target: Window = window) {
    target.addEventListener("keydown", this.onKeyDown);
    target.addEventListener("keyup", this.onKeyUp);
    target.addEventListener("blur", this.onBlur);
  }

  isHeld(action: Action): boolean {
    return this.held.has(action);
  }

  wasPressed(action: Action): boolean {
    return this.pressed.has(action);
  }

  axisX(): number {
    return (this.isHeld("right") ? 1 : 0) - (this.isHeld("left") ? 1 : 0);
  }

  axisY(): number {
    return (this.isHeld("down") ? 1 : 0) - (this.isHeld("up") ? 1 : 0);
  }

  endFrame(): void {
    this.pressed.clear();
  }

  dispose(): void {
    this.target.removeEventListener("keydown", this.onKeyDown);
    this.target.removeEventListener("keyup", this.onKeyUp);
    this.target.removeEventListener("blur", this.onBlur);
  }

  private onKeyDown = (e: KeyboardEvent) => {
    const action = KEY_BINDINGS[e.code];
    if (!action) return;
    e.preventDefault();
    if (!e.repeat) this.pressed.add(action);
    this.held.add(action);
  };

  private onKeyUp = (e: KeyboardEvent) => {
    const action = KEY_BINDINGS[e.code];
    if (action) this.held.delete(action);
  };

  /** Releasing focus would otherwise leave keys "stuck" down. */
  private onBlur = () => {
    this.held.clear();
  };
}
