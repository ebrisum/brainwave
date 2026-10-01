import { RideRecord, RideSummary } from "./record";
import { aerobicDecoupling, intensityFactor, kilojoules, mean, normalizedPower, trainingStressScore, variabilityIndex, wPrimeBalance } from "./power";

export function summarize(recs: RideRecord[], ftp: number, wPrime: number, cp = ftp): RideSummary {
  const p = recs.map((r) => r.powerW);
  const hr = recs.map((r) => r.hrBpm ?? 0);
  const np = normalizedPower(p);
  const avg = mean(p);
  const dur = recs.length ? (recs[recs.length - 1].t - recs[0].t) / 1000 + 1 : 0;
  const hrs = hr.filter((h) => h > 0);
  const cad = recs.map((r) => r.cadenceRpm ?? 0).filter((c) => c > 0);
  let asc = 0;
  let ref = recs[0]?.ele ?? 0;
  for (const r of recs) {
    if (r.ele - ref >= 1) { asc += r.ele - ref; ref = r.ele; }
    else if (r.ele - ref <= -1) ref = r.ele;
  }
  const wbal = wPrimeBalance(p, cp, wPrime);
  return {
    startTime: recs[0]?.t ?? 0, durationS: dur, distanceM: recs.length ? recs[recs.length - 1].s - recs[0].s : 0,
    avgPowerW: avg, npW: np, ifactor: intensityFactor(np, ftp), tss: trainingStressScore(dur, np, ftp), vi: variabilityIndex(np, avg),
    kJ: kilojoules(p), avgHr: hrs.length ? mean(hrs) : undefined, maxHr: hrs.length ? Math.max(...hrs) : undefined,
    avgCadence: cad.length ? mean(cad) : undefined, avgSpeedMs: mean(recs.map((r) => r.speedMs)), ascentM: asc,
    minWPrimeBalJ: wbal.length ? Math.min(...wbal) : wPrime, brakingTimeS: recs.filter((r) => r.braking).length,
    decouplingPct: aerobicDecoupling(p, hr),
  };
}

/** Per-segment actual vs planned power. */
export function segmentComparison(recs: RideRecord[], segmentM: number, planned: ArrayLike<number>) {
  const out: { index: number; actualW: number; plannedW: number; timeS: number }[] = [];
  const bins = new Map<number, number[]>();
  for (const r of recs) {
    const k = Math.floor(r.s / segmentM);
    (bins.get(k) ?? bins.set(k, []).get(k)!).push(r.powerW);
  }
  for (const [k, ps] of [...bins.entries()].sort((a, b) => a[0] - b[0])) {
    out.push({ index: k, actualW: mean(ps), plannedW: planned[Math.min(k, planned.length - 1)] ?? 0, timeS: ps.length });
  }
  return out;
}

/** Split times at given distances (s, m) from a recording (linear interpolation between 1 Hz samples). */
export function splitTimes(recs: RideRecord[], marks: number[]): number[] {
  const out: number[] = [];
  let j = 0;
  for (const m of marks) {
    while (j < recs.length - 1 && recs[j + 1].s < m) j++;
    if (j >= recs.length - 1) { out.push(NaN); continue; }
    const a = recs[j];
    const b = recs[j + 1];
    const f = b.s > a.s ? (m - a.s) / (b.s - a.s) : 0;
    out.push((a.t + (b.t - a.t) * f - recs[0].t) / 1000);
  }
  return out;
}
