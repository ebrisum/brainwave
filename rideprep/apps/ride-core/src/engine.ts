import { encode } from "@msgpack/msgpack";
import { BleAdapter, demoRider, lookaheadGrade, ManagedConnection, SensorHub, SERVICES, TrainerController, VirtualDeviceAdapter, windResistanceCoefficient } from "@rideprep/ble";
import { LoadedCourse, localToLatLon, poseAt, StreamCommand, StreamHello, StreamState, STREAM_VERSION } from "@rideprep/course-format";
import { normalizedPower, RideRecord, summarize, toFit } from "@rideprep/metrics";
import { airDensity, courseLength, DEFAULT_CORNERING, Environment, RideSimulator, RiderProfile, sampleCourse, WindAtRider, WindModel } from "@rideprep/physics";
import { solarPosition } from "./solar";

export interface EngineOptions {
  rider: RiderProfile;
  startEpoch: number;
  cornering?: boolean;
  gusts?: boolean;
  seed?: number;
  difficulty?: number;
  plan?: { segmentM: number; watts: number[] };
}

/**
 * Headless ride engine: the same physics, wind, BLE and metrics packages as the web client, at a fixed 50 Hz,
 * producing StreamState messages for renderers (Unreal, or the web client in "local ride core" mode).
 */
export class RideEngine {
  sim: RideSimulator;
  hub = new SensorHub();
  trainer?: TrainerController;
  connections: ManagedConnection[] = [];
  records: RideRecord[] = [];
  paused = false;
  difficulty: number;
  private wind: WindModel;
  private lastWind?: WindAtRider;
  private seq = 0;
  private crank = 0;
  private lastRecordSec = -1;
  private ascent = 0;
  private refZ?: number;
  private timer?: ReturnType<typeof setInterval>;
  private listeners = new Set<(buf: Uint8Array, st: StreamState) => void>();
  readonly startedAt = Date.now();

  constructor(public course: LoadedCourse, public opts: EngineOptions) {
    this.difficulty = opts.difficulty ?? 1;
    this.wind = new WindModel(course.wind, course.weather, { seed: opts.seed ?? 1, gusts: opts.gusts ?? true });
    const env: Environment = {
      at: (s, t, heading, elev, dt = 0.02) => {
        const w = this.wind.step(s, t, heading, dt);
        this.lastWind = w;
        return { rho: airDensity({ tempC: w.weather.tempC, rh: w.weather.rh, pMslHpa: w.weather.pMslHpa, elevationM: elev }), wHead: w.wHead,
          wCross: w.wCross, wet: w.weather.precipMmH > 0.2, tempC: w.weather.tempC, uRider: w.uRider, shelter: w.factors.shelter };
      },
    };
    this.sim = new RideSimulator(course.route, opts.rider, env, { startEpoch: opts.startEpoch, cornering: { ...DEFAULT_CORNERING, enabled: opts.cornering ?? true } });
  }

  hello(packageUrl: string): StreamHello {
    return { type: "hello", v: STREAM_VERSION, courseId: this.course.manifest.courseId, packageUrl, startEpoch: this.opts.startEpoch };
  }

  onState(cb: (buf: Uint8Array, st: StreamState) => void) {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  async pair(kind: "trainer" | "power" | "hr", adapter: BleAdapter) {
    const services = { trainer: [SERVICES.ftms], power: [SERVICES.cyclingPower], hr: [SERVICES.heartRate] }[kind];
    const dev = await adapter.requestDevice({ services });
    const mc = new ManagedConnection(dev, async (d) => {
      await this.hub.attach(d);
      if (kind === "trainer") {
        this.trainer = new TrainerController(d, { difficulty: this.difficulty });
        await this.trainer.start();
      }
    }, (s) => console.log(`[${kind}] ${dev.name}: ${s}`));
    await mc.start();
    this.connections.push(mc);
    return dev;
  }

  static virtual(ftp: number) {
    return new VirtualDeviceAdapter({ script: demoRider(ftp) });
  }

  command(c: StreamCommand) {
    if (c.type === "pause") this.paused = true;
    else if (c.type === "resume") this.paused = false;
    else if (c.type === "difficulty") { this.difficulty = c.value; if (this.trainer) this.trainer.difficulty = c.value; }
    else if (c.type === "end") void this.finish();
  }

  /** Start the fixed-step loop (wall-clock accumulator, 20 ms steps, one state message per step). */
  start() {
    let last = performance.now();
    let acc = 0;
    let trainerAcc = 0;
    this.timer = setInterval(() => {
      const now = performance.now();
      const dt = Math.min((now - last) / 1000, 0.25);
      last = now;
      if (this.paused || this.sim.state.finished) {
        this.emit(0);
        return;
      }
      if (this.hub.r.powerW !== undefined) this.sim.setPower(this.hub.r.powerW);
      acc += dt;
      while (acc >= this.sim.dt) {
        this.sim.step();
        acc -= this.sim.dt;
        this.emit(this.sim.dt);
      }
      trainerAcc += dt;
      if (trainerAcc >= 0.1) {
        trainerAcc = 0;
        this.controlTrainer();
      }
      this.record();
    }, 5);
  }

  private controlTrainer() {
    const t = this.trainer;
    if (!t) return;
    const st = this.sim.state;
    const w = this.lastWind;
    t.setSimulation({ gradePct: lookaheadGrade((s) => sampleCourse(this.course.route, s).grade * 100, st.s, st.v), windSpeedMs: w?.wHead ?? 0,
      crr: this.opts.rider.crrBase * st.sample.crrMultiplier, cwKgM: windResistanceCoefficient(st.env.rho, this.opts.rider.cda) });
    void t.tick();
  }

  private targetW(s: number) {
    const p = this.opts.plan;
    return p ? p.watts[Math.min(Math.floor(s / p.segmentM), p.watts.length - 1)] : undefined;
  }

  private emit(dt: number) {
    if (!this.listeners.size) return;
    const st = this.sim.state;
    const w = this.lastWind;
    const cad = this.hub.r.cadenceRpm ?? (st.powerW > 0 ? 85 : 0);
    this.crank = (this.crank + (cad / 60) * 2 * Math.PI * dt) % (2 * Math.PI);
    const p = poseAt(this.course.route, st.s);
    const o = this.course.manifest.origin;
    const sun = solarPosition(new Date((this.opts.startEpoch + st.t) * 1000), o.lat, o.lon);
    const laps = this.course.manifest.segments.laps;
    const np = normalizedPower(this.records.map((r) => r.powerW));
    const h1 = sampleCourse(this.course.route, st.s + 5).headingRad;
    const turn = Math.sin(h1 - p.headingRad);
    const msg: StreamState = {
      type: "state", v: STREAM_VERSION, seq: this.seq++, sentAt: Date.now(), t: st.t, s: st.s, pos: [p.x, p.y, p.z], heading: p.headingRad, speed: st.v,
      power: st.powerW, hr: this.hub.r.heartRateBpm, cadence: this.hub.r.cadenceRpm, crank: this.crank, lean: st.leanRad * Math.sign(turn), braking: st.braking,
      gradePct: st.sample.grade * 100,
      wind: { u10: w?.u10 ?? 0, dir10: w?.dir10 ?? 0, uRider: w?.uRider ?? 0, dirRider: w?.dirRider ?? 0, wHead: w?.wHead ?? 0, wCross: w?.wCross ?? 0, gust: w?.gust ?? 1, shelter: w?.factors.shelter ?? 1 },
      weather: { tempC: w?.weather.tempC ?? 15, rh: w?.weather.rh ?? 0.7, pMslHpa: w?.weather.pMslHpa ?? 1013, precipMmH: w?.weather.precipMmH ?? 0,
        cloudCover: w?.weather.cloudCover ?? 0.5, visibilityM: w?.weather.visibilityM ?? 20000, rho: st.env.rho },
      sun: { elevationDeg: sun.elevationDeg, azimuthDeg: sun.azimuthDeg },
      hud: { npW: np, ifactor: np / this.opts.rider.ftpW, wkg: st.powerW / this.opts.rider.riderMassKg, lap: Math.max(1, laps.findIndex((l) => st.s < l.sEnd) + 1 || laps.length),
        laps: laps.length, ascentM: this.ascent, targetW: this.targetW(st.s), elapsedS: st.t, distanceM: courseLength(this.course.route) },
      paused: this.paused, finished: st.finished,
    };
    const buf = encode(msg);
    for (const l of this.listeners) l(buf, msg);
  }

  private record() {
    const st = this.sim.state;
    const sec = Math.floor(st.t);
    if (sec === this.lastRecordSec || this.paused) return;
    this.lastRecordSec = sec;
    const smp = sampleCourse(this.course.route, st.s);
    if (this.refZ === undefined) this.refZ = smp.z;
    if (smp.z - this.refZ >= 1) { this.ascent += smp.z - this.refZ; this.refZ = smp.z; }
    else if (smp.z - this.refZ <= -1) this.refZ = smp.z;
    const o = this.course.manifest.origin;
    const [lat, lon] = localToLatLon(o.lat, o.lon, smp.x, smp.y);
    const w = this.lastWind;
    this.records.push({ t: this.startedAt + sec * 1000, s: st.s, lat, lon, ele: smp.z, powerW: st.powerW, hrBpm: this.hub.r.heartRateBpm, cadenceRpm: this.hub.r.cadenceRpm,
      speedMs: st.v, gradePct: smp.grade * 100, windSpeed10: w?.u10 ?? 0, windDirDeg: w?.dir10 ?? 0, uRider: w?.uRider ?? 0, wHead: w?.wHead ?? 0, wCross: w?.wCross ?? 0,
      shelter: w?.factors.shelter ?? 1, tempC: st.env.tempC, rho: st.env.rho, crrEff: this.opts.rider.crrBase * smp.crrMultiplier, targetPowerW: this.targetW(st.s), braking: st.braking });
    if (st.finished) void this.finish();
  }

  finished?: Promise<Uint8Array>;
  finish(): Promise<Uint8Array> {
    if (!this.finished) {
      this.stop();
      const sum = summarize(this.records, this.opts.rider.ftpW, this.opts.rider.wPrimeJ);
      this.finished = Promise.resolve(toFit(this.records, sum));
    }
    return this.finished;
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    for (const c of this.connections) void c.stop();
  }
}
