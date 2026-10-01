/** Power metrics on 1 Hz series. */

/** Normalized Power: 4th-power mean of the 30 s rolling average (Coggan). */
export function normalizedPower(p: ArrayLike<number>, windowS = 30): number {
  const n = p.length;
  if (n === 0) return 0;
  if (n < windowS) return mean(p);
  let sum = 0;
  for (let i = 0; i < windowS; i++) sum += p[i];
  let acc = 0;
  let cnt = 0;
  for (let i = windowS - 1; i < n; i++) {
    if (i >= windowS) sum += p[i] - p[i - windowS];
    acc += Math.pow(sum / windowS, 4);
    cnt++;
  }
  return Math.pow(acc / cnt, 0.25);
}

export function mean(a: ArrayLike<number>): number {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i];
  return a.length ? s / a.length : 0;
}

export const intensityFactor = (np: number, ftp: number) => (ftp > 0 ? np / ftp : 0);

/** TSS = (t · NP · IF) / (FTP · 3600) · 100. */
export const trainingStressScore = (durationS: number, np: number, ftp: number) =>
  ftp > 0 ? ((durationS * np * intensityFactor(np, ftp)) / (ftp * 3600)) * 100 : 0;

export const variabilityIndex = (np: number, avg: number) => (avg > 0 ? np / avg : 0);

export function kilojoules(p: ArrayLike<number>, dt = 1): number {
  let s = 0;
  for (let i = 0; i < p.length; i++) s += p[i] * dt;
  return s / 1000;
}

/**
 * W′ balance, Skiba differential model (Skiba et al. 2015): above CP, W′ is depleted by (P−CP)·dt;
 * below CP it recovers as dW′ = (W′ − W′bal)·(CP − P)/W′ · dt.
 */
export function wPrimeBalance(p: ArrayLike<number>, cp: number, wPrime: number, dt = 1): Float64Array {
  const out = new Float64Array(p.length);
  let bal = wPrime;
  for (let i = 0; i < p.length; i++) {
    const P = p[i];
    if (P > cp) bal -= (P - cp) * dt;
    else bal += ((wPrime - bal) * (cp - P) * dt) / wPrime;
    bal = Math.min(bal, wPrime);
    out[i] = bal;
  }
  return out;
}

/** Coggan power zones (fractions of FTP). Returns seconds in Z1..Z7. */
export const POWER_ZONES = [0, 0.56, 0.76, 0.91, 1.06, 1.21, 1.51];
export function timeInPowerZones(p: ArrayLike<number>, ftp: number, dt = 1): number[] {
  const z = new Array(7).fill(0);
  for (let i = 0; i < p.length; i++) {
    const f = p[i] / ftp;
    let k = 0;
    while (k < 6 && f >= POWER_ZONES[k + 1]) k++;
    z[k] += dt;
  }
  return z;
}

/** HR zones as fractions of max HR (5 zones: <60, 60–70, 70–80, 80–90, ≥90 %). */
export const HR_ZONES = [0, 0.6, 0.7, 0.8, 0.9];
export function timeInHrZones(hr: ArrayLike<number>, maxHr: number, dt = 1): number[] {
  const z = new Array(5).fill(0);
  for (let i = 0; i < hr.length; i++) {
    if (!(hr[i] > 0)) continue;
    const f = hr[i] / maxHr;
    let k = 0;
    while (k < 4 && f >= HR_ZONES[k + 1]) k++;
    z[k] += dt;
  }
  return z;
}

/** Aerobic decoupling Pa:HR (%): change in power/HR from the first to the second half. Positive = drift. */
export function aerobicDecoupling(p: ArrayLike<number>, hr: ArrayLike<number>): number | undefined {
  const n = Math.min(p.length, hr.length);
  if (n < 600) return undefined;
  const half = Math.floor(n / 2);
  const ratio = (a: number, b: number) => {
    let ps = 0;
    let hs = 0;
    for (let i = a; i < b; i++) {
      if (!(hr[i] > 0)) continue;
      ps += p[i];
      hs += hr[i];
    }
    return hs > 0 ? ps / hs : NaN;
  };
  const r1 = ratio(0, half);
  const r2 = ratio(half, n);
  if (!isFinite(r1) || !isFinite(r2) || r1 === 0) return undefined;
  return ((r1 - r2) / r1) * 100;
}

/** Best average power over a duration (mean-max). */
export function bestAverage(p: ArrayLike<number>, windowS: number): number {
  if (p.length < windowS) return 0;
  let s = 0;
  for (let i = 0; i < windowS; i++) s += p[i];
  let best = s;
  for (let i = windowS; i < p.length; i++) {
    s += p[i] - p[i - windowS];
    if (s > best) best = s;
  }
  return best / windowS;
}
