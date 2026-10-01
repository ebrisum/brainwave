import { BleDevice } from "./adapter";
import {
  ControlPointResponse, encodeRequestControl, encodeSetTargetPower, encodeSetTargetResistance, encodeSimulation,
  encodeStartOrResume, OP, parseControlPointResponse, RESULT, SimulationParams,
} from "./ftms";
import { CHARS, SERVICES } from "./uuids";

export interface TrainerControllerOptions {
  now?: () => number;
  responseTimeoutMs?: number;
  /** Supported grade range in % (from the trainer if known). */
  gradeRange?: [number, number];
  /** Scales only the grade sent to the trainer, never the physics. 1 = 100 %. */
  difficulty?: number;
  onWarning?: (msg: string) => void;
  onCommand?: (bytes: Uint8Array, res: ControlPointResponse | "timeout") => void;
}

export type TrainerMode = "simulation" | "erg" | "resistance-fallback";

/**
 * FTMS trainer controller. Serialises control-point writes (one in flight, waiting for the 0x80 indication or a
 * 1.5 s timeout) and rate-limits simulation updates: send on Δgrade ≥ 0.1 % or Δwind ≥ 0.2 m/s, at most 2/s,
 * and at least every 5 s as keep-alive.
 */
export class TrainerController {
  mode: TrainerMode = "simulation";
  private chain: Promise<unknown> = Promise.resolve();
  private pending?: { op: number; resolve: (r: ControlPointResponse | "timeout") => void };
  private lastSent?: SimulationParams;
  private lastSentAt = -Infinity;
  private desired?: SimulationParams;
  private inFlight = false;
  private opts: Required<Omit<TrainerControllerOptions, "onWarning" | "onCommand">> & TrainerControllerOptions;
  readonly log: { t: number; bytes: number[]; result: number | "timeout" }[] = [];

  constructor(private device: BleDevice, opts: TrainerControllerOptions = {}) {
    this.opts = { now: () => Date.now(), responseTimeoutMs: 1500, gradeRange: [-20, 20], difficulty: 1, ...opts };
  }

  set difficulty(d: number) { this.opts.difficulty = Math.min(Math.max(d, 0), 2); }

  async start(): Promise<void> {
    await this.device.subscribe(SERVICES.ftms, CHARS.ftmsControlPoint, (dv) => this.onIndication(dv));
    const rc = await this.send(encodeRequestControl());
    if (rc === "timeout" || rc.result !== RESULT.success) throw new Error("FTMS Request Control failed");
    await this.send(encodeStartOrResume());
  }

  private onIndication(dv: DataView) {
    const r = parseControlPointResponse(dv);
    if (r && this.pending && r.requestOp === this.pending.op) {
      const p = this.pending;
      this.pending = undefined;
      p.resolve(r);
    }
  }

  /** Queue a raw control-point command; resolves with the response or "timeout". */
  send(bytes: Uint8Array): Promise<ControlPointResponse | "timeout"> {
    const run = async (): Promise<ControlPointResponse | "timeout"> => {
      const result = new Promise<ControlPointResponse | "timeout">((resolve) => {
        this.pending = { op: bytes[0], resolve };
        setTimeout(() => {
          if (this.pending?.resolve === resolve) {
            this.pending = undefined;
            resolve("timeout");
          }
        }, this.opts.responseTimeoutMs);
      });
      await this.device.write(SERVICES.ftms, CHARS.ftmsControlPoint, bytes, true);
      const r = await result;
      this.log.push({ t: this.opts.now(), bytes: Array.from(bytes), result: r === "timeout" ? r : r.result });
      this.opts.onCommand?.(bytes, r);
      return r;
    };
    const p = this.chain.then(run, run);
    this.chain = p.catch(() => undefined);
    return p;
  }

  /** Grade actually sent: difficulty-scaled and clamped to the trainer's range. */
  gradeToSend(gradePct: number): number {
    const g = gradePct * (gradePct > 0 ? this.opts.difficulty : 1);
    return Math.min(Math.max(g, this.opts.gradeRange[0]), this.opts.gradeRange[1]);
  }

  /** Record the desired simulation state; call `tick()` regularly (e.g. 10 Hz) to flush per the rate rules. */
  setSimulation(p: SimulationParams): void {
    this.desired = { ...p, gradePct: this.gradeToSend(p.gradePct) };
  }

  /** Whether a simulation update should be sent now. */
  shouldSend(now = this.opts.now()): boolean {
    if (!this.desired || this.mode === "erg") return false;
    const since = now - this.lastSentAt;
    if (since < 500) return false;
    if (since >= 5000) return true;
    const l = this.lastSent;
    if (!l) return true;
    return Math.abs(this.desired.gradePct - l.gradePct) >= 0.1 || Math.abs(this.desired.windSpeedMs - l.windSpeedMs) >= 0.2
      || Math.abs(this.desired.crr - l.crr) >= 0.0001 || Math.abs(this.desired.cwKgM - l.cwKgM) >= 0.01;
  }

  async tick(now = this.opts.now()): Promise<void> {
    if (this.inFlight || !this.shouldSend(now) || !this.desired) return;
    const p = this.desired;
    this.inFlight = true;
    this.lastSentAt = now;
    this.lastSent = p;
    try {
      if (this.mode === "resistance-fallback") {
        await this.send(encodeSetTargetResistance(gradeToResistance(p.gradePct)));
        return;
      }
      const r = await this.send(encodeSimulation(p));
      if (r !== "timeout" && r.result === RESULT.notSupported) {
        this.mode = "resistance-fallback";
        this.opts.onWarning?.("Trainer does not support simulation mode (0x11); falling back to resistance levels.");
      }
    } finally {
      this.inFlight = false;
    }
  }

  /** ERG mode: the trainer holds a target power; virtual speed still comes from the physics. */
  async setErg(watts: number): Promise<void> {
    this.mode = "erg";
    await this.send(encodeSetTargetPower(watts));
  }

  leaveErg(): void {
    this.mode = "simulation";
    this.lastSentAt = -Infinity;
  }
}

/** Fallback mapping: grade (%) to resistance level 0..100 (trainer units differ; documented as approximate). */
export function gradeToResistance(gradePct: number): number {
  return Math.min(Math.max(30 + gradePct * 5, 0), 100);
}

/**
 * Grade to send: average over the next `windowM` metres starting at the position the rider will reach after
 * `latencyS` at the current speed (compensates for trainer latency).
 */
export function lookaheadGrade(gradeAt: (s: number) => number, s: number, v: number, latencyS = 0.7, windowM = 15): number {
  const start = s + v * latencyS;
  const n = 6;
  let sum = 0;
  for (let i = 0; i < n; i++) sum += gradeAt(start + (windowM * (i + 0.5)) / n);
  return sum / n;
}

export { OP };
