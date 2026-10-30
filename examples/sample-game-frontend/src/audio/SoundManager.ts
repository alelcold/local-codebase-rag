export type SoundName = "pickup" | "hit" | "dash" | "levelUp" | "gameOver";

/**
 * Generates short synthesized sound effects with the Web Audio API,
 * so the game ships without audio assets.
 * Browsers only allow audio after a user gesture; call unlock() from a key handler.
 */
export class SoundManager {
  private ctx: AudioContext | null = null;
  muted = false;

  unlock(): void {
    if (!this.ctx) this.ctx = new AudioContext();
    if (this.ctx.state === "suspended") void this.ctx.resume();
  }

  play(name: SoundName): void {
    if (this.muted || !this.ctx) return;
    const presets: Record<SoundName, [freq: number, duration: number, type: OscillatorType]> = {
      pickup: [880, 0.08, "square"],
      hit: [110, 0.25, "sawtooth"],
      dash: [440, 0.06, "triangle"],
      levelUp: [660, 0.3, "sine"],
      gameOver: [70, 0.8, "sawtooth"],
    };
    const [freq, duration, type] = presets[name];
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.2, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + duration);
    osc.connect(gain).connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + duration);
  }
}
