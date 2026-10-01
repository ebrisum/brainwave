/** Small deterministic PRNG (mulberry32) with Gaussian draws, so rides are reproducible from a seed. */
export class Rng {
  private state: number;
  private spare: number | null = null;
  constructor(seed: number) {
    this.state = seed >>> 0 || 0x9e3779b9;
  }
  next(): number {
    let t = (this.state = (this.state + 0x6d2b79f5) >>> 0);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  gaussian(): number {
    if (this.spare !== null) {
      const s = this.spare;
      this.spare = null;
      return s;
    }
    let u = 0;
    while (u === 0) u = this.next();
    const v = this.next();
    const mag = Math.sqrt(-2 * Math.log(u));
    this.spare = mag * Math.sin(2 * Math.PI * v);
    return mag * Math.cos(2 * Math.PI * v);
  }
}

/** Ornstein-Uhlenbeck process with exact discretisation; stationary std = sigma. */
export class OrnsteinUhlenbeck {
  value: number;
  constructor(public mean: number, public sigma: number, public tau: number, private rng: Rng) {
    this.value = mean;
  }
  step(dt: number): number {
    const a = Math.exp(-dt / this.tau);
    this.value = this.mean + (this.value - this.mean) * a + this.sigma * Math.sqrt(1 - a * a) * this.rng.gaussian();
    return this.value;
  }
}
