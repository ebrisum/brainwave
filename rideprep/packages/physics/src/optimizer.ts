import { CourseProfile, courseLength, sampleCourse } from "./course";
import { Environment } from "./environment";
import { steadyStateSpeed } from "./motion";
import { predict, Prediction, splitTime } from "./predictor";
import { RiderProfile } from "./rider";

export interface OptimizeOptions {
  startEpoch: number;
  /** Target normalized power for the whole ride (W). Defaults to ifTarget·FTP. */
  targetNpW?: number;
  ifTarget?: number;
  segmentM?: number;
  /** Bounds relative to the target average power. */
  lowerFrac?: number;
  upperFrac?: number;
  /** Keep W' balance above this fraction of W' (e.g. 0.2). Omit to ignore W'. */
  minWPrimeFrac?: number;
  /** Critical power for the W' model (defaults to FTP). */
  cpW?: number;
}

export interface PacingPlan {
  segmentM: number;
  watts: number[];
  prediction: Prediction;
  baseline: Prediction;
  npW: number;
  minWPrimeBalJ?: number;
  timeSavedS: number;
}

interface Seg {
  len: number;
  grade: number;
  crr: number;
  rho: number;
  wHead: number;
  wCross: number;
  wet: boolean;
  /** Correction from steady-state to full-dynamics time (captured at the baseline). */
  k: number;
  /** k·t_ss(P) tabulated on a uniform power grid over [lo, hi]. */
  table: Float64Array;
}

const GRID = 64;

/** Time-weighted normalised power over segment powers. */
export function segmentNp(watts: ArrayLike<number>, times: ArrayLike<number>): number {
  let num = 0;
  let den = 0;
  for (let i = 0; i < watts.length; i++) {
    num += times[i] * Math.pow(watts[i], 4);
    den += times[i];
  }
  return den > 0 ? Math.pow(num / den, 0.25) : 0;
}

/** Skiba differential W' balance over (power, duration) segments; returns the minimum balance (J). */
export function minWPrimeBalance(watts: ArrayLike<number>, times: ArrayLike<number>, cp: number, wPrime: number): number {
  let bal = wPrime;
  let min = wPrime;
  for (let i = 0; i < watts.length; i++) {
    const P = watts[i];
    const dt = times[i];
    if (P > cp) bal -= (P - cp) * dt;
    else bal = wPrime - (wPrime - bal) * Math.exp(-((cp - P) * dt) / wPrime);
    min = Math.min(min, bal);
  }
  return min;
}

/**
 * Pacing optimizer. Minimises Σ t_i(P_i) subject to NP ≤ target and per-segment bounds.
 * Uses a separable Lagrangian on a steady-state segment model calibrated against the full predictor,
 * with bisection on the multiplier; the final plan is verified with the full predictor.
 */
export function optimizePacing(course: CourseProfile, rider: RiderProfile, env: Environment, opts: OptimizeOptions): PacingPlan {
  const segM = opts.segmentM ?? 500;
  const np = opts.targetNpW ?? (opts.ifTarget ?? 0.8) * rider.ftpW;
  const lo = np * (1 - (opts.lowerFrac ?? 0.2));
  const hi = np * (1 + (opts.upperFrac ?? 0.15));
  const L = courseLength(course);
  const nSeg = Math.ceil(L / segM);

  const baseline = predict(course, rider, np, env, { startEpoch: opts.startEpoch });
  const segs: Seg[] = [];
  for (let i = 0; i < nSeg; i++) {
    const s0 = i * segM;
    const s1 = Math.min(L, s0 + segM);
    const sm = (s0 + s1) / 2;
    const smp = sampleCourse(course, sm);
    const tMid = baseline.timeAtSample[Math.min(Math.round(sm / course.spacingM), course.count - 1)];
    const e = env.at(sm, opts.startEpoch + tMid, smp.headingRad, smp.z);
    const z0 = sampleCourse(course, s0).z;
    const z1 = sampleCourse(course, s1).z;
    let crr = 0;
    const n0 = Math.floor(s0 / course.spacingM);
    const n1 = Math.max(n0 + 1, Math.floor(s1 / course.spacingM));
    for (let j = n0; j < n1; j++) crr += course.crrMultiplier[Math.min(j, course.count - 1)];
    const seg: Seg = {
      len: s1 - s0, grade: (z1 - z0) / Math.max(s1 - s0, 1), crr: crr / (n1 - n0), rho: e.rho, wHead: e.wHead, wCross: e.wCross,
      wet: e.wet, k: 1, table: new Float64Array(GRID + 1),
    };
    const tss = segTime(rider, seg, np);
    const tFull = splitTime(baseline, course, s0, s1);
    seg.k = tss > 0 && isFinite(tss) ? Math.min(Math.max(tFull / tss, 0.5), 2) : 1;
    for (let g = 0; g <= GRID; g++) seg.table[g] = seg.k * segTime(rider, seg, lo + ((hi - lo) * g) / GRID);
    segs.push(seg);
  }
  const timeOf = (i: number, P: number): number => {
    const tab = segs[i].table;
    const f = Math.min(Math.max(((P - lo) / (hi - lo)) * GRID, 0), GRID);
    const g = Math.min(Math.floor(f), GRID - 1);
    return tab[g] + (tab[g + 1] - tab[g]) * (f - g);
  };

  const solveFor = (lambda: number, upper: number[]): number[] =>
    segs.map((_, i) => goldenMin((P) => {
      const t = timeOf(i, P);
      return t + lambda * t * (Math.pow(P / np, 4) - 1);
    }, lo, upper[i]));

  let upper = new Array(nSeg).fill(hi);
  let watts: number[] = [];
  for (let wIter = 0; wIter < 8; wIter++) {
    // Bisection on λ so that NP(watts) ≈ target.
    let lamLo = 0;
    let lamHi = 1;
    const npOf = (w: number[]) => segmentNp(w, w.map((P, i) => timeOf(i, P)));
    while (npOf(solveFor(lamHi, upper)) > np && lamHi < 1e6) lamHi *= 4;
    watts = solveFor(lamHi, upper);
    if (npOf(solveFor(0, upper)) > np) {
      for (let it = 0; it < 40; it++) {
        const mid = (lamLo + lamHi) / 2;
        if (npOf(solveFor(mid, upper)) > np) lamLo = mid;
        else lamHi = mid;
      }
      watts = solveFor(lamHi, upper);
    } else {
      watts = solveFor(0, upper);
    }
    if (opts.minWPrimeFrac === undefined) break;
    const times = watts.map((P, i) => timeOf(i, P));
    const cp = opts.cpW ?? rider.ftpW;
    const minBal = minWPrimeBalance(watts, times, cp, rider.wPrimeJ);
    if (minBal >= opts.minWPrimeFrac * rider.wPrimeJ) break;
    // Tighten the cap on segments above CP and retry.
    upper = upper.map((u, i) => (watts[i] > cp ? Math.max(lo, u - (u - cp) * 0.3) : u));
  }

  const plan = { segmentM: segM, watts };
  const prediction = predict(course, rider, plan, env, { startEpoch: opts.startEpoch });
  const segTimes = watts.map((_, i) => splitTime(prediction, course, i * segM, Math.min(L, (i + 1) * segM)));
  const result: PacingPlan = {
    segmentM: segM, watts, prediction, baseline, npW: segmentNp(watts, segTimes),
    timeSavedS: baseline.totalTimeS - prediction.totalTimeS,
  };
  if (opts.minWPrimeFrac !== undefined) result.minWPrimeBalJ = minWPrimeBalance(watts, segTimes, opts.cpW ?? rider.ftpW, rider.wPrimeJ);
  return result;
}

function segTime(r: RiderProfile, sg: Seg, P: number): number {
  const v = steadyStateSpeed(r, {
    grade: sg.grade, crrMultiplier: sg.crr, wetFactor: sg.wet ? 1.05 : 1, rho: sg.rho, wHead: sg.wHead, wCross: sg.wCross,
  }, P);
  return sg.len / Math.max(v, 0.3);
}

function goldenMin(f: (x: number) => number, a: number, b: number, iters = 40): number {
  if (b <= a) return a;
  const g = (Math.sqrt(5) - 1) / 2;
  let c = b - g * (b - a);
  let d = a + g * (b - a);
  let fc = f(c);
  let fd = f(d);
  for (let i = 0; i < iters; i++) {
    if (fc < fd) {
      b = d; d = c; fd = fc; c = b - g * (b - a); fc = f(c);
    } else {
      a = c; c = d; fc = fd; d = a + g * (b - a); fd = f(d);
    }
  }
  return (a + b) / 2;
}
