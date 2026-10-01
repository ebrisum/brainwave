import { BleDevice } from "./adapter";
import { parseCsc, parseCyclingPower, parseHeartRate, parseIndoorBikeData, RevolutionRate } from "./parsers";
import { CHARS, SERVICES } from "./uuids";

export type PowerSource = "powerMeter" | "trainer";
export type CadenceSource = "powerMeter" | "csc" | "trainer";

export interface SensorReadings {
  powerW?: number;
  powerSource?: PowerSource;
  trainerPowerW?: number;
  meterPowerW?: number;
  cadenceRpm?: number;
  cadenceSource?: CadenceSource;
  heartRateBpm?: number;
  rrIntervalsS: number[];
  trainerSpeedKmh?: number;
  updatedAt: Record<string, number>;
}

/**
 * Merges sensor streams using the priority rules: power meter > trainer for power,
 * power-meter crank data > CSC > FTMS for cadence. A source counts as live for `staleMs`.
 */
export class SensorHub {
  readonly r: SensorReadings = { rrIntervalsS: [], updatedAt: {} };
  private crankPm = new RevolutionRate();
  private crankCsc = new RevolutionRate();
  private cad: Partial<Record<CadenceSource, number>> = {};
  constructor(private now: () => number = () => Date.now(), private staleMs = 3000) {}

  private live(k: string) { return this.now() - (this.r.updatedAt[k] ?? -Infinity) < this.staleMs; }

  private resolve() {
    const r = this.r;
    if (this.live("meterPower")) { r.powerW = r.meterPowerW; r.powerSource = "powerMeter"; }
    else if (this.live("trainerPower")) { r.powerW = r.trainerPowerW; r.powerSource = "trainer"; }
    for (const src of ["powerMeter", "csc", "trainer"] as CadenceSource[]) {
      if (this.live(`cad_${src}`) && this.cad[src] !== undefined) { r.cadenceRpm = this.cad[src]; r.cadenceSource = src; break; }
    }
  }

  onIndoorBikeData(dv: DataView) {
    const d = parseIndoorBikeData(dv);
    const t = this.now();
    if (d.powerW !== undefined) { this.r.trainerPowerW = d.powerW; this.r.updatedAt.trainerPower = t; }
    if (d.cadenceRpm !== undefined) { this.cad.trainer = d.cadenceRpm; this.r.updatedAt.cad_trainer = t; }
    if (d.speedKmh !== undefined) this.r.trainerSpeedKmh = d.speedKmh;
    if (d.heartRateBpm && !this.live("hr")) this.r.heartRateBpm = d.heartRateBpm;
    this.resolve();
  }

  onCyclingPower(dv: DataView) {
    const d = parseCyclingPower(dv);
    const t = this.now();
    this.r.meterPowerW = d.powerW;
    this.r.updatedAt.meterPower = t;
    if (d.crank) { this.cad.powerMeter = this.crankPm.update(d.crank, t / 1000); this.r.updatedAt.cad_powerMeter = t; }
    this.resolve();
  }

  onCsc(dv: DataView) {
    const d = parseCsc(dv);
    if (d.crank) { this.cad.csc = this.crankCsc.update(d.crank, this.now() / 1000); this.r.updatedAt.cad_csc = this.now(); }
    this.resolve();
  }

  onHeartRate(dv: DataView) {
    const d = parseHeartRate(dv);
    this.r.heartRateBpm = d.bpm;
    this.r.rrIntervalsS.push(...d.rrIntervalsS);
    this.r.updatedAt.hr = this.now();
  }

  /** Take (and clear) RR intervals collected since the last call, for recording. */
  drainRr(): number[] { return this.r.rrIntervalsS.splice(0); }

  /** Subscribe to every sensor service the device offers. */
  async attach(d: BleDevice) {
    const has = async (s: string) => (d.hasService ? d.hasService(s) : true);
    if (await has(SERVICES.ftms)) await d.subscribe(SERVICES.ftms, CHARS.indoorBikeData, (dv) => this.onIndoorBikeData(dv));
    if (await has(SERVICES.cyclingPower)) await d.subscribe(SERVICES.cyclingPower, CHARS.cyclingPowerMeasurement, (dv) => this.onCyclingPower(dv));
    if (await has(SERVICES.heartRate)) await d.subscribe(SERVICES.heartRate, CHARS.heartRateMeasurement, (dv) => this.onHeartRate(dv));
    if (await has(SERVICES.cscs)) await d.subscribe(SERVICES.cscs, CHARS.cscMeasurement, (dv) => this.onCsc(dv));
  }
}
