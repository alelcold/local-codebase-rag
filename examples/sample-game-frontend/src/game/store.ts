import type { UiSnapshot } from "./GameState";

type Listener = () => void;

/**
 * Tiny external store bridging the game loop and React.
 * The game writes with `set`; React reads with useSyncExternalStore.
 * Listeners only fire when a value actually changed, so the HUD does
 * not re-render on every frame.
 */
export function createUiStore(initial: UiSnapshot) {
  let snapshot = initial;
  const listeners = new Set<Listener>();

  return {
    get: () => snapshot,
    subscribe(listener: Listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    set(patch: Partial<UiSnapshot>) {
      const changed = (Object.keys(patch) as (keyof UiSnapshot)[]).some((k) => patch[k] !== snapshot[k]);
      if (!changed) return;
      snapshot = { ...snapshot, ...patch };
      listeners.forEach((l) => l());
    },
  };
}

export type UiStore = ReturnType<typeof createUiStore>;
