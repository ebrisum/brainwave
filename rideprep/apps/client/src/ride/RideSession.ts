import {
  BleAdapter, BleDevice, CalibrationCheck, CHARS, demoRider, lookaheadGrade, ManagedConnection, SensorHub, SERVICES, TrainerController, VirtualDeviceAdapter,
  WebBluetoothAdapter, windResistanceCoefficient,
} from "@rideprep/ble";
import { LoadedCourse, localToLatLon } from "@rideprep/course-format";
import { normalizedPower, RideRecord, summarize } from "@rideprep/metrics";
import { courseLength, powerForSpeed, RiderProfile, sampleCourse, WeatherJson } from "@rideprep/physics";
import { HudState } from "../store";
import { feelsLike } from "../units";
import { PhysicsState, ToWorker } from "./protocol";
import { saveRide, StoredRide } from "./recorder";
import { solarPosition } from "./solar";
import { RenderState } from "../engine/World";

export type DeviceKind = "trainer" | "power" | "hr" | "cadence";

export interface SessionOptions {
  rider: RiderProfile & { maxHr: number };
  startEpoch: number;
  cornering: boolean;
  gusts: boolean;
  difficulty: number;
  plan?: { segmentM: number; watts: number[] };
  erg?: boolean;
  ghost?: RideRecord[];
  /** Start position along the course (m) — practise a section such as a climb. */
  startS?: number;
}

/**
 * One ride: physics worker, devices (Web Bluetooth or virtual), trainer control, 1 Hz recording, HUD feed and the
 * interpolated render state.
 */
export class RideSession {
  worker: Worker;
  hub = new SensorHub();
  trainer?: TrainerController;
  connections: Partial<Record<DeviceKind, ManagedConnection>> = {};
  deviceStates: Record<string, string> = {};
  records: RideRecord[] = [];
  private prev?: PhysicsState;
  private curr?: PhysicsState;
  private timers: ReturnType<typeof setInterval>[] = [];
  private lastRecordT = -1;
  private p3: number[] = [];
  private ascent = 0;
  private refZ?: number;
  private crank = 0;
  private lastFrame = performance.now();
  private started = false;
  paused = false;
  warnings: string[] = [];
  calibration = new CalibrationCheck();
  readonly startedAt = Date.now();

  constructor(public course: LoadedCourse, public opts: SessionOptions, private onHud: (h: HudState) => void, private onFinish: (id: string) => void) {
    this.worker = new Worker(new URL("./physics.worker.ts", import.meta.url), { type: "module" });
    this.worker.onmessage = (e: MessageEvent<PhysicsState>) => {
      this.prev = this.curr;
      this.curr = e.data;
    };
  }

  static adapter(kind: "web" | "virtual", ftp: number): BleAdapter {
    return kind === "web" ? new WebBluetoothAdapter() : new VirtualDeviceAdapter({ script: demoRider(ftp) });
  }

  /** Pair a device for a role. Must be called from a click handler for Web Bluetooth. */
  async pair(kind: DeviceKind, adapter: BleAdapter): Promise<BleDevice> {
    const services = { trainer: [SERVICES.ftms], power: [SERVICES.cyclingPower], hr: [SERVICES.heartRate], cadence: [SERVICES.cscs] }[kind];
    const dev = await adapter.requestDevice({ services });
    const setup = async (d: BleDevice) => {
      await this.hub.attach(d);
      if (kind === "trainer") {
        this.trainer = new TrainerController(d, { difficulty: this.opts.difficulty, onWarning: (w) => this.warn(w) });
        await this.trainer.start();
        if (this.opts.erg && this.opts.plan) await this.trainer.setErg(this.opts.plan.watts[0]);
      }
    };
    const mc = new ManagedConnection(dev, setup, (s) => (this.deviceStates[`${kind}: ${dev.name}`] = s));
    await mc.start();
    this.connections[kind] = mc;
    return dev;
  }

  warn(w: string) {
    if (!this.warnings.includes(w)) this.warnings.push(w);
  }

  start(weather?: WeatherJson) {
    const r = this.course.route;
    const msg: ToWorker = {
      type: "init",
      route: { spacingM: r.spacingM, count: r.count, s: r.s, x: r.x, y: r.y, z: r.z, gradePct: r.gradePct, headingRad: r.headingRad, radiusM: r.radiusM, crrMultiplier: r.crrMultiplier },
      wind: { data: this.course.wind.data, count: this.course.wind.count, spacingM: this.course.wind.spacingM, bins: this.course.wind.bins, layers: [...this.course.wind.layers] },
      weather: weather ?? this.course.weatherJson, rider: this.opts.rider, startEpoch: this.opts.startEpoch, cornering: this.opts.cornering,
      gusts: this.opts.gusts, seed: (this.startedAt % 100000) | 0, startS: this.opts.startS,
    };
    this.worker.postMessage(msg);
    this.started = true;
    // Feed power at 4 Hz, trainer control at 10 Hz, record at 1 Hz, HUD at 10 Hz
    this.timers.push(setInterval(() => this.feedPower(), 250));
    this.timers.push(setInterval(() => this.controlTrainer(), 100));
    this.timers.push(setInterval(() => this.record(), 200));
    this.timers.push(setInterval(() => this.hud(), 100));
  }

  private feedPower() {
    const p = this.hub.r.powerW;
    if (p !== undefined && !this.paused) this.worker.postMessage({ type: "power", watts: p } satisfies ToWorker);
  }

  targetPower(s: number): number | undefined {
    const plan = this.opts.plan;
    if (!plan) return undefined;
    return plan.watts[Math.min(Math.floor(s / plan.segmentM), plan.watts.length - 1)];
  }

  private lastErgTarget?: number;
  private controlTrainer() {
    const st = this.curr;
    const t = this.trainer;
    if (!st || !t) return;
    const c = this.course.route;
    if (this.opts.erg && this.opts.plan) {
      const target = this.targetPower(st.s);
      if (target !== undefined && target !== this.lastErgTarget) {
        this.lastErgTarget = target;
        void t.setErg(target);
      }
      return;
    }
    const grade = lookaheadGrade((s) => sampleCourse(c, s).grade * 100, st.s, st.v);
    t.setSimulation({ gradePct: grade, windSpeedMs: st.wind.wHead, crr: st.crrEff, cwKgM: windResistanceCoefficient(st.rho, this.opts.rider.cda) });
    void t.tick();
  }

  private record() {
    const st = this.curr;
    if (!st || this.paused) return;
    const sec = Math.floor(st.t);
    if (sec === this.lastRecordT) return;
    this.lastRecordT = sec;
    const c = this.course.route;
    const smp = sampleCourse(c, st.s);
    if (this.refZ === undefined) this.refZ = smp.z;
    if (smp.z - this.refZ >= 1) { this.ascent += smp.z - this.refZ; this.refZ = smp.z; }
    else if (smp.z - this.refZ <= -1) this.refZ = smp.z;
    const [lat, lon] = this.latLon(st.s);
    this.records.push({
      t: this.startedAt + sec * 1000, s: st.s, lat, lon, ele: smp.z, powerW: st.powerW, hrBpm: this.hub.r.heartRateBpm, rrS: this.hub.drainRr(),
      cadenceRpm: this.hub.r.cadenceRpm, speedMs: st.v, trainerSpeedMs: this.hub.r.trainerSpeedKmh !== undefined ? this.hub.r.trainerSpeedKmh / 3.6 : undefined,
      gradePct: st.gradePct, windSpeed10: st.wind.u10, windDirDeg: st.wind.dir10, uRider: st.wind.uRider, wHead: st.wind.wHead, wCross: st.wind.wCross,
      shelter: st.wind.shelter, tempC: st.tempC, rho: st.rho, crrEff: st.crrEff, targetPowerW: this.targetPower(st.s), braking: st.braking,
    });
    // Calibration check: trainer power vs power meter (or physics power for the trainer's own speed)
    const tw = this.hub.r.trainerPowerW;
    const ref = this.hub.r.meterPowerW ?? (this.hub.r.trainerSpeedKmh !== undefined
      ? powerForSpeed(this.opts.rider, { grade: 0, crrMultiplier: 1, wetFactor: 1, rho: st.rho, wHead: 0, wCross: 0 }, this.hub.r.trainerSpeedKmh / 3.6) : undefined);
    const cal = this.calibration.result ? undefined : this.calibration.add({ t: sec, trainerW: tw, referenceW: ref, gradePct: st.gradePct, wHead: st.wind.wHead });
    if (cal) {
      console.info("[calibration]", cal);
      if (cal.verdict === "check") this.warn(`Trainer reads ${cal.offsetPct > 0 ? "+" : ""}${cal.offsetPct.toFixed(1)} % vs reference — consider a spin-down`);
    }
    if (st.finished) void this.finish();
  }

  /** WGS84 position at route distance s (inverse of the package's local transverse Mercator frame). */
  latLon(s: number): [number, number] {
    const smp = sampleCourse(this.course.route, s);
    const o = this.course.manifest.origin;
    return localToLatLon(o.lat, o.lon, smp.x, smp.y);
  }

  private hud() {
    const st = this.curr;
    if (!st) return;
    const m = this.course.manifest;
    const laps = m.segments.laps;
    const lap = Math.max(1, laps.findIndex((l) => st.s < l.sEnd) + 1 || laps.length);
    const np = normalizedPower(this.records.map((r) => r.powerW));
    const ftp = this.opts.rider.ftpW;
    const target = this.targetPower(st.s);
    this.p3.push(st.powerW);
    if (this.p3.length > 30) this.p3.shift();
    const ts = this.trainer?.status;
    this.onHud({
      t: st.t, s: st.s, speedMs: st.v, powerW: st.powerW, npW: np, ifactor: ftp ? np / ftp : 0, hr: this.hub.r.heartRateBpm, cadence: this.hub.r.cadenceRpm,
      ascentM: this.ascent, lap, laps: laps.length, wkg: st.powerW / this.opts.rider.riderMassKg,
      targetLow: target ? target * 0.97 : undefined, targetHigh: target ? target * 1.03 : undefined, braking: st.braking,
      wind: { u10: st.wind.u10, dir10: st.wind.dir10, uRider: st.wind.uRider, wHead: st.wind.wHead, wCross: st.wind.wCross, shelter: st.wind.shelter, gust: st.wind.gust },
      tempC: st.tempC, feelsC: feelsLike(st.tempC, st.weather.rh, st.wind.uRider + st.v), rho: st.rho, gradePct: st.gradePct,
      devices: { ...this.deviceStates }, paused: this.paused, finished: st.finished, warnings: this.warnings, trainerMode: this.trainer?.mode,
      power3sW: this.p3.reduce((a, b) => a + b, 0) / this.p3.length, ftpW: ftp, maxHr: this.opts.rider.maxHr,
      trainer: ts && { mode: ts.mode, gradePct: ts.sim?.gradePct, windMs: ts.sim?.windSpeedMs, crr: ts.sim?.crr, cwKgM: ts.sim?.cwKgM, ergW: ts.ergW,
        difficulty: ts.difficulty },
      powerSource: this.hub.r.powerSource, cadenceSource: this.hub.r.cadenceSource,
    });
  }

  /** Interpolated render state at the current wall time. */
  renderState(): RenderState {
    const now = performance.now();
    const dt = (now - this.lastFrame) / 1000;
    this.lastFrame = now;
    const a = this.prev ?? this.curr;
    const b = this.curr;
    const o = this.course.manifest.origin;
    if (!a || !b) {
      const sun = solarPosition(new Date(this.opts.startEpoch * 1000), o.lat, o.lon);
      return { s: 0, speed: 0, leanRad: 0, crankRad: 0, gradePct: 0, cadence: 0, powerW: 0, windToX: 0, windToY: 1, uRider: 0, gust: 1,
        sunElevationDeg: sun.elevationDeg, sunAzimuthDeg: sun.azimuthDeg, cloud: 0.3, visibilityM: 20000, rainMmH: 0 };
    }
    // b is the latest state; extrapolate a little past it by wall time to avoid stutter between 50 Hz posts
    const since = Math.min((now - b.wall) / 1000, 0.05);
    const s = b.s + b.v * (this.paused ? 0 : since);
    const cad = this.hub.r.cadenceRpm ?? (b.powerW > 0 ? 85 : 0);
    if (!this.paused) this.crank += (cad / 60) * 2 * Math.PI * dt;
    const sun = solarPosition(new Date((this.opts.startEpoch + b.t) * 1000), o.lat, o.lon);
    const toDeg = b.wind.dirRider + 180;
    const turn = (b.leanRad || 0) * Math.sign(this.turnSign(b.s));
    void a;
    return {
      s, speed: b.v, leanRad: turn, crankRad: this.crank, gradePct: b.gradePct, cadence: cad, powerW: b.powerW,
      windToX: Math.sin((toDeg * Math.PI) / 180), windToY: Math.cos((toDeg * Math.PI) / 180), uRider: b.wind.uRider, gust: b.wind.gust,
      sunElevationDeg: sun.elevationDeg, sunAzimuthDeg: sun.azimuthDeg, cloud: b.weather.cloudCover, visibilityM: b.weather.visibilityM,
      rainMmH: b.weather.precipMmH, ghostS: this.ghostS(b.t), hr: this.hub.r.heartRateBpm,
    };
  }

  private turnSign(s: number): number {
    const c = this.course.route;
    const h0 = sampleCourse(c, s).headingRad;
    const h1 = sampleCourse(c, s + 5).headingRad;
    return Math.sin(h1 - h0);
  }

  private ghostS(t: number): number | undefined {
    const g = this.opts.ghost;
    if (!g?.length) return undefined;
    const t0 = g[0].t;
    const k = Math.min(Math.max(Math.floor(t), 0), g.length - 1);
    return (g[k].t - t0) / 1000 <= t ? g[k].s : g[Math.max(0, k - 1)].s;
  }

  pause() {
    this.paused = true;
    this.worker.postMessage({ type: "pause" } satisfies ToWorker);
  }

  resume() {
    this.paused = false;
    this.worker.postMessage({ type: "resume" } satisfies ToWorker);
  }

  setDifficulty(d: number) {
    if (this.trainer) this.trainer.difficulty = d;
  }

  progress(): number {
    return (this.curr?.s ?? 0) / courseLength(this.course.route);
  }

  async finish(): Promise<string> {
    this.stop();
    const sum = summarize(this.records, this.opts.rider.ftpW, this.opts.rider.wPrimeJ);
    const id = `r_${this.startedAt}`;
    const ride: StoredRide = { id, courseId: this.course.manifest.courseId, courseName: this.course.manifest.name, startedAt: this.startedAt,
      records: this.records, summary: sum, plan: this.opts.plan };
    await saveRide(ride);
    this.onFinish(id);
    return id;
  }

  stop() {
    this.timers.forEach(clearInterval);
    this.timers = [];
    this.worker.terminate();
    for (const c of Object.values(this.connections)) void c?.stop();
  }

  get isStarted() {
    return this.started;
  }
}

export { CHARS };
