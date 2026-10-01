import { PHYSICS_DT } from "./constants";
import { cornerSpeedLimit, CorneringParams, DEFAULT_CORNERING, leanAngle, needsBraking } from "./cornering";
import { CourseProfile, courseLength, CourseSample, sampleCourse } from "./course";
import { Environment, EnvSample } from "./environment";
import { acceleration } from "./motion";
import { effectiveMass, RiderProfile } from "./rider";

export interface SimulatorOptions {
  startEpoch: number;
  cornering?: CorneringParams;
  /** How long a power sample is held on dropout (s). */
  holdS?: number;
  /** Ramp to 0 over this time after the hold (s). */
  rampS?: number;
  wetCrrFactor?: number;
}

export interface SimState {
  /** Simulated seconds since start. */
  t: number;
  s: number;
  v: number;
  powerW: number;
  braking: boolean;
  brakingTimeS: number;
  finished: boolean;
  leanRad: number;
  sample: CourseSample;
  env: EnvSample;
}

/** Deterministic fixed-step (50 Hz) ride simulation. The app's single source of truth for virtual speed. */
export class RideSimulator {
  readonly dt = PHYSICS_DT;
  state: SimState;
  private lastPower = 0;
  private lastPowerAt = -Infinity;
  private vMaxDry: Float32Array;
  private vMaxWet: Float32Array;
  private length: number;
  private opts: Required<SimulatorOptions>;

  constructor(public course: CourseProfile, public rider: RiderProfile, public env: Environment, opts: SimulatorOptions) {
    this.opts = { cornering: DEFAULT_CORNERING, holdS: 3, rampS: 2, wetCrrFactor: 1.05, ...opts };
    this.length = courseLength(course);
    this.vMaxDry = new Float32Array(course.count);
    this.vMaxWet = new Float32Array(course.count);
    for (let i = 0; i < course.count; i++) {
      this.vMaxDry[i] = cornerSpeedLimit(course.radiusM[i], false, this.opts.cornering);
      this.vMaxWet[i] = cornerSpeedLimit(course.radiusM[i], true, this.opts.cornering);
    }
    const sample = sampleCourse(course, 0);
    this.state = {
      t: 0, s: 0, v: 0, powerW: 0, braking: false, brakingTimeS: 0, finished: false, leanRad: 0, sample,
      env: env.at(0, opts.startEpoch, sample.headingRad, sample.z),
    };
  }

  /** Feed a new power sample (W) measured at simulated time t. */
  setPower(watts: number, t = this.state.t): void {
    this.lastPower = Math.max(0, watts);
    this.lastPowerAt = t;
  }

  /** Effective power after dropout hold-and-ramp. */
  effectivePower(t = this.state.t): number {
    const age = t - this.lastPowerAt;
    if (age <= this.opts.holdS) return this.lastPower;
    const r = 1 - (age - this.opts.holdS) / this.opts.rampS;
    return r > 0 ? this.lastPower * r : 0;
  }

  /** Iterates (distanceAhead, vMax) over the look-ahead window. */
  private *ahead(s: number, wet: boolean): Generator<[number, number]> {
    const c = this.course;
    const vMax = wet ? this.vMaxWet : this.vMaxDry;
    const i0 = Math.max(0, Math.floor(s / c.spacingM));
    const n = Math.ceil(this.opts.cornering.lookAheadM / c.spacingM);
    for (let i = i0; i <= Math.min(i0 + n, c.count - 1); i++) {
      yield [Math.max(0, c.s[i] - s), vMax[i]];
    }
  }

  step(): SimState {
    const st = this.state;
    if (st.finished) return st;
    const sample = sampleCourse(this.course, st.s, st.sample);
    const env = this.env.at(st.s, this.opts.startEpoch + st.t, sample.headingRad, sample.z, this.dt);
    const P = this.effectivePower(st.t);
    const braking = needsBraking(st.v, this.ahead(st.s, env.wet), env.wet, this.opts.cornering);
    const aBrake = env.wet ? this.opts.cornering.aBrakeWet : this.opts.cornering.aBrakeDry;
    const brakeN = braking ? effectiveMass(this.rider) * aBrake : 0;
    const cond = {
      grade: sample.grade, crrMultiplier: sample.crrMultiplier, wetFactor: env.wet ? this.opts.wetCrrFactor : 1,
      rho: env.rho, wHead: env.wHead, wCross: env.wCross,
    };
    const a = acceleration(this.rider, cond, P, st.v, brakeN);
    const v = Math.max(0, st.v + a * this.dt);
    st.v = v;
    st.s += v * this.dt;
    st.t += this.dt;
    st.powerW = P;
    st.braking = braking;
    if (braking) st.brakingTimeS += this.dt;
    st.env = env;
    st.leanRad = leanAngle(v, sample.radiusM);
    if (st.s >= this.length) {
      st.s = this.length;
      st.finished = true;
    }
    return st;
  }

  /** Advance by a wall-clock duration, stepping at 50 Hz. Returns the number of steps taken. */
  advance(seconds: number): number {
    const n = Math.round(seconds / this.dt);
    for (let i = 0; i < n && !this.state.finished; i++) this.step();
    return n;
  }
}
