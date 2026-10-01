import { encodeCyclingPower, encodeHeartRate, encodeIndoorBikeData, OP, RESULT, SimulationParams } from "@rideprep/ble";

export interface EmulatorLogEntry { t: number; op: number; bytes: number[]; decoded?: Record<string, number> }

/**
 * Hardware-free emulator logic: FTMS control point handling and sensor notifications for a scripted rider.
 * The bleno wiring (main.ts) only moves bytes; everything testable lives here.
 */
export class EmulatorCore {
  controlGranted = false;
  started = false;
  sim: SimulationParams = { windSpeedMs: 0, gradePct: 0, crr: 0.004, cwKgM: 0.51 };
  ergTarget?: number;
  readonly log: EmulatorLogEntry[] = [];
  private crankRevs = 0;
  private crankTicks = 0;
  private t = 0;

  constructor(private script: { power: (t: number) => number; hr: (t: number) => number; cadence: (t: number) => number }, private now = () => Date.now()) {}

  /** Handle a control-point write; returns the 0x80 indication to send back. */
  controlPoint(data: Uint8Array): Uint8Array {
    const op = data[0];
    const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
    let result: number = RESULT.success;
    const entry: EmulatorLogEntry = { t: this.now(), op, bytes: Array.from(data) };
    if (op !== OP.requestControl && !this.controlGranted) result = RESULT.controlNotPermitted;
    else switch (op) {
      case OP.requestControl: this.controlGranted = true; break;
      case OP.reset: this.controlGranted = false; this.started = false; this.ergTarget = undefined; break;
      case OP.startOrResume: this.started = true; break;
      case OP.stopOrPause: this.started = false; break;
      case OP.setTargetPower:
        if (data.length < 3) { result = RESULT.invalidParameter; break; }
        this.ergTarget = dv.getInt16(1, true);
        entry.decoded = { targetW: this.ergTarget };
        break;
      case OP.setIndoorBikeSimulation:
        if (data.length < 7) { result = RESULT.invalidParameter; break; }
        this.sim = { windSpeedMs: dv.getInt16(1, true) / 1000, gradePct: dv.getInt16(3, true) / 100, crr: data[5] / 10000, cwKgM: data[6] / 100 };
        this.ergTarget = undefined;
        entry.decoded = { ...this.sim };
        break;
      default: result = RESULT.notSupported;
    }
    this.log.push(entry);
    return Uint8Array.of(OP.response, op, result);
  }

  /** Advance the scripted rider by dt and produce one round of notifications. */
  tick(dt: number) {
    this.t += dt;
    const cad = this.script.cadence(this.t);
    // In ERG the trainer holds the target; in simulation the rider's scripted power gets a small grade response
    const power = this.ergTarget ?? Math.max(0, this.script.power(this.t) * (1 + 0.02 * this.sim.gradePct));
    const before = Math.floor(this.crankRevs);
    this.crankRevs += (cad / 60) * dt;
    if (Math.floor(this.crankRevs) > before && cad > 0) {
      const frac = this.crankRevs - Math.floor(this.crankRevs);
      this.crankTicks = Math.round((this.t - frac / (cad / 60)) * 1024) & 0xffff;
    }
    const speedKmh = Math.max(0, 10 + power / 10 - this.sim.gradePct * 1.5);
    return {
      indoorBikeData: encodeIndoorBikeData({ speedKmh, cadenceRpm: cad, powerW: power }),
      cyclingPower: encodeCyclingPower({ powerW: power, crankRevs: Math.floor(this.crankRevs), crankEventTicks: this.crankTicks }),
      heartRate: encodeHeartRate(Math.round(this.script.hr(this.t)), [60 / Math.max(this.script.hr(this.t), 30)]),
    };
  }
}
