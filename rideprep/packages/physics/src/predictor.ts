import { cornerSpeedLimit, CorneringParams, DEFAULT_CORNERING } from "./cornering";
import { CourseProfile, courseLength, sampleCourse, CourseSample } from "./course";
import { Environment } from "./environment";
import { acceleration } from "./motion";
import { effectiveMass, RiderProfile } from "./rider";

/** Power plan: a constant or per-segment target powers. */
export type PowerPlan = number | { segmentM: number; watts: ArrayLike<number> };

export function planPowerAt(plan: PowerPlan, s: number): number {
  if (typeof plan === "number") return plan;
  const i = Math.min(Math.floor(s / plan.segmentM), plan.watts.length - 1);
  return plan.watts[Math.max(i, 0)];
}

export interface PredictOptions {
  startEpoch: number;
  dt?: number;
  cornering?: CorneringParams;
  startSpeed?: number;
  /** Stop after this many simulated seconds (safety). */
  maxTimeS?: number;
}

export interface Prediction {
  totalTimeS: number;
  distanceM: number;
  kJ: number;
  avgSpeed: number;
  brakingTimeS: number;
  /** Cumulative time (s) when passing each course sample (index = sample index). */
  timeAtSample: Float64Array;
  /** True if the safety time limit was hit. */
  stalled: boolean;
}

/** Time (s) to ride from s0 to s1 using a prediction. */
export function splitTime(p: Prediction, course: CourseProfile, s0: number, s1: number): number {
  const at = (s: number) => {
    const fi = Math.min(Math.max(s / course.spacingM, 0), course.count - 1);
    const i = Math.min(Math.floor(fi), course.count - 2);
    const t = fi - i;
    return p.timeAtSample[i] + (p.timeAtSample[i + 1] - p.timeAtSample[i]) * t;
  };
  return at(s1) - at(s0);
}

export function splitsEvery(p: Prediction, course: CourseProfile, everyM: number): { s0: number; s1: number; timeS: number; avgSpeed: number }[] {
  const L = courseLength(course);
  const out = [];
  for (let s0 = 0; s0 < L - 1e-6; s0 += everyM) {
    const s1 = Math.min(s0 + everyM, L);
    const timeS = splitTime(p, course, s0, s1);
    out.push({ s0, s1, timeS, avgSpeed: timeS > 0 ? (s1 - s0) / timeS : 0 });
  }
  return out;
}

/**
 * Run the ride physics at a coarse timestep (default 1 Hz) over the whole course for a power plan.
 * Same equation of motion and cornering rules as the 50 Hz simulator; no gusts.
 */
export function predict(course: CourseProfile, rider: RiderProfile, plan: PowerPlan, env: Environment, opts: PredictOptions): Prediction {
  const dt = opts.dt ?? 1;
  const corn = opts.cornering ?? DEFAULT_CORNERING;
  const L = courseLength(course);
  const mEff = effectiveMass(rider);
  const vMaxDry = new Float32Array(course.count);
  const vMaxWet = new Float32Array(course.count);
  for (let i = 0; i < course.count; i++) {
    vMaxDry[i] = cornerSpeedLimit(course.radiusM[i], false, corn);
    vMaxWet[i] = cornerSpeedLimit(course.radiusM[i], true, corn);
  }
  const lookN = Math.ceil(corn.lookAheadM / course.spacingM);
  const timeAtSample = new Float64Array(course.count);
  let s = 0;
  let v = opts.startSpeed ?? 0.5;
  let t = 0;
  let energy = 0;
  let brakingTimeS = 0;
  let nextIdx = 1;
  const maxT = opts.maxTimeS ?? 48 * 3600;
  const smp: CourseSample = sampleCourse(course, 0);
  const cond = { grade: 0, crrMultiplier: 1, wetFactor: 1, rho: 1.225, wHead: 0, wCross: 0 };
  let stalled = false;
  while (s < L) {
    sampleCourse(course, s, smp);
    const e = env.at(s, opts.startEpoch + t, smp.headingRad, smp.z, dt);
    const P = planPowerAt(plan, s);
    // Braking look-ahead
    let braking = false;
    if (corn.enabled) {
      const vMax = e.wet ? vMaxWet : vMaxDry;
      const aB = e.wet ? corn.aBrakeWet : corn.aBrakeDry;
      const i0 = Math.floor(s / course.spacingM);
      for (let i = i0; i <= Math.min(i0 + lookN, course.count - 1); i++) {
        const vm = vMax[i];
        if (v <= vm + 0.1) continue;
        if ((v * v - vm * vm) / (2 * aB) >= course.s[i] - s - v * dt) {
          braking = true;
          break;
        }
      }
    }
    const aB = e.wet ? corn.aBrakeWet : corn.aBrakeDry;
    cond.grade = smp.grade;
    cond.crrMultiplier = smp.crrMultiplier;
    cond.wetFactor = e.wet ? 1.05 : 1;
    cond.rho = e.rho;
    cond.wHead = e.wHead;
    cond.wCross = e.wCross;
    const a = acceleration(rider, cond, P, v, braking ? mEff * aB : 0);
    v = Math.max(0.3, v + a * dt); // a walking-pace floor keeps the predictor from stalling on walls
    if (braking) brakingTimeS += dt;
    const sPrev = s;
    s += v * dt;
    t += dt;
    energy += P * dt;
    while (nextIdx < course.count && course.s[nextIdx] <= s) {
      const frac = (course.s[nextIdx] - sPrev) / (s - sPrev);
      timeAtSample[nextIdx] = t - dt + frac * dt;
      nextIdx++;
    }
    if (t > maxT) {
      stalled = true;
      break;
    }
  }
  for (; nextIdx < course.count; nextIdx++) timeAtSample[nextIdx] = t;
  const totalTimeS = timeAtSample[course.count - 1];
  return { totalTimeS, distanceM: L, kJ: energy / 1000, avgSpeed: L / totalTimeS, brakingTimeS, timeAtSample, stalled };
}
