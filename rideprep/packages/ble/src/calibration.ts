/**
 * Trainer calibration check (spec §9.4): over 2 minutes of steady power on a flat (|grade| < 0.5 %), calm
 * (|w_head| < 1 m/s) section, compare trainer-reported power with the reference — the power meter if present,
 * otherwise the power the physics needs for the trainer's own speed. The result is logged, not applied.
 */
export interface CalibrationSample { t: number; trainerW?: number; referenceW?: number; gradePct: number; wHead: number }

export interface CalibrationResult { durationS: number; trainerAvgW: number; referenceAvgW: number; offsetPct: number; verdict: "ok" | "check" }

export class CalibrationCheck {
  private buf: CalibrationSample[] = [];
  result?: CalibrationResult;
  constructor(private windowS = 120, private tolerancePct = 3) {}

  add(s: CalibrationSample): CalibrationResult | undefined {
    if (this.result) return this.result;
    const usable = s.trainerW !== undefined && s.referenceW !== undefined && Math.abs(s.gradePct) < 0.5 && Math.abs(s.wHead) < 1;
    if (!usable) {
      this.buf = [];
      return undefined;
    }
    this.buf.push(s);
    while (this.buf.length && s.t - this.buf[0].t > this.windowS) this.buf.shift();
    if (this.buf.length < 2 || s.t - this.buf[0].t < this.windowS - 1) return undefined;
    const ref = this.buf.map((x) => x.referenceW!);
    const mean = ref.reduce((a, b) => a + b, 0) / ref.length;
    const cv = Math.sqrt(ref.reduce((a, b) => a + (b - mean) ** 2, 0) / ref.length) / Math.max(mean, 1);
    if (cv > 0.08 || mean < 80) return undefined; // not steady enough yet
    const tr = this.buf.reduce((a, b) => a + b.trainerW!, 0) / this.buf.length;
    const offsetPct = ((tr - mean) / mean) * 100;
    this.result = { durationS: s.t - this.buf[0].t, trainerAvgW: tr, referenceAvgW: mean, offsetPct,
      verdict: Math.abs(offsetPct) <= this.tolerancePct ? "ok" : "check" };
    return this.result;
  }
}
