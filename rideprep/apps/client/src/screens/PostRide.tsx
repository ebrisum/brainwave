import { useEffect, useState } from "react";
import { segmentComparison, splitTimes, timeInPowerZones, toFit, toGpx, toTcx } from "@rideprep/metrics";
import { DEFAULT_CORNERING, predict, WeatherField, windEnvironment, WindModel } from "@rideprep/physics";
import { cache, startEpochOf } from "../courseCache";
import { ridesForCourse, StoredRide } from "../ride/recorder";
import { useApp } from "../store";
import { fmtDist, fmtDuration, fmtSpeed } from "../units";

/**
 * Race-prep costs (spec §12): replay the rider's actual per-500 m power through the predictor —
 * ride weather vs calm (time lost to wind) and cornering on vs off (time lost to braking).
 */
function timeCosts(ride: StoredRide, rider: Parameters<typeof predict>[1]): { windS: number; brakingS: number } | undefined {
  const c = cache.course;
  if (!c || c.manifest.courseId !== ride.courseId || ride.records.length < 30) return undefined;
  const seg = segmentComparison(ride.records, 500, []);
  const watts = new Array(Math.ceil(c.manifest.stats.distanceM / 500)).fill(0).map((_, i) => seg.find((x) => x.index === i)?.actualW ?? seg[seg.length - 1].actualW);
  const plan = { segmentM: 500, watts };
  const start = startEpochOf(c);
  const done = ride.records[ride.records.length - 1].s;
  const t = (field: WeatherField, cornering: boolean) => {
    const p = predict(c.route, rider, plan, windEnvironment(new WindModel(c.wind, field, { gusts: false })), {
      startEpoch: start, cornering: { ...DEFAULT_CORNERING, enabled: cornering } });
    const i = Math.min(Math.round(done / c.route.spacingM), c.route.count - 1);
    return p.timeAtSample[i];
  };
  const calm = WeatherField.constant({ u10: 0, tempC: 15 });
  return { windS: t(c.weather, true) - t(calm, true), brakingS: t(c.weather, true) - t(c.weather, false) };
}

function download(name: string, data: BlobPart, type: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([data], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

export function PostRide() {
  const { lastRideId, courseId, settings, go } = useApp();
  const [rides, setRides] = useState<StoredRide[]>([]);
  useEffect(() => { if (courseId) void ridesForCourse(courseId).then(setRides); }, [courseId]);
  const ride = rides.find((r) => r.id === lastRideId) ?? rides[0];
  if (!ride) return <main className="page"><p>Loading ride…</p></main>;
  const s = ride.summary;
  const u = settings.units;
  const m = cache.course?.manifest;
  const marks = m ? [...m.segments.climbs.flatMap((c) => [c.sStart, c.sEnd])] : [];
  const fiveK = Array.from({ length: Math.floor(s.distanceM / 5000) }, (_, i) => (i + 1) * 5000);
  const cmp = ride.plan ? segmentComparison(ride.records, ride.plan.segmentM, ride.plan.watts) : [];
  const zones = timeInPowerZones(ride.records.map((r) => r.powerW), settings.rider.ftpW);
  const base = `${ride.courseName.replace(/\W+/g, "_")}_${new Date(ride.startedAt).toISOString().slice(0, 10)}`;
  const others = rides.filter((r) => r.id !== ride.id).slice(0, 4);
  const costs = timeCosts(ride, settings.rider);
  return (
    <main className="page">
      <header className="pagehead">
        <button onClick={() => go("home")}>← Home</button>
        <h1>Ride analysis</h1>
        <div className="row">
          <button onClick={() => download(`${base}.fit`, toFit(ride.records, s) as BlobPart, "application/vnd.ant.fit")}>Export FIT</button>
          <button onClick={() => download(`${base}.tcx`, toTcx(ride.records, s), "application/vnd.garmin.tcx+xml")}>Export TCX</button>
          <button onClick={() => download(`${base}.gpx`, toGpx(ride.records, ride.courseName), "application/gpx+xml")}>Export GPX</button>
        </div>
      </header>
      <div className="kpis big">
        <span><b>{fmtDuration(s.durationS)}</b>time</span><span><b>{fmtDist(s.distanceM, u)}</b>distance</span><span><b>{fmtSpeed(s.avgSpeedMs, u)}</b>avg speed</span>
        <span><b>{Math.round(s.avgPowerW)} W</b>avg power</span><span><b>{Math.round(s.npW)} W</b>NP</span><span><b>{s.ifactor.toFixed(2)}</b>IF</span>
        <span><b>{Math.round(s.tss)}</b>TSS</span><span><b>{s.vi.toFixed(2)}</b>VI</span><span><b>{Math.round(s.kJ)}</b>kJ</span>
        <span><b>{Math.round(s.minWPrimeBalJ / 1000)} kJ</b>min W′bal</span><span><b>{fmtDuration(s.brakingTimeS)}</b>braking</span>
        {costs && <span><b>{costs.windS >= 0 ? "+" : "−"}{fmtDuration(Math.abs(costs.windS))}</b>wind vs calm</span>}
        {costs && <span><b>+{fmtDuration(costs.brakingS)}</b>lost to braking</span>}
        {s.avgHr && <span><b>{Math.round(s.avgHr)}</b>avg HR</span>}{s.decouplingPct !== undefined && <span><b>{s.decouplingPct.toFixed(1)} %</b>Pa:HR</span>}
      </div>
      <div className="grid2">
        <section className="card">
          <h2>Actual vs planned power</h2>
          {cmp.length ? (
            <svg viewBox="0 0 600 140" className="planchart" role="img" aria-label="Actual vs planned power per segment">
              {cmp.map((c, i) => {
                const w = 600 / cmp.length;
                const max = Math.max(...cmp.map((x) => Math.max(x.actualW, x.plannedW))) * 1.1;
                return (
                  <g key={i}>
                    <rect x={i * w} y={140 - (c.plannedW / max) * 140} width={w * 0.45} height={(c.plannedW / max) * 140} fill="#56B4E9" />
                    <rect x={i * w + w * 0.45} y={140 - (c.actualW / max) * 140} width={w * 0.45} height={(c.actualW / max) * 140} fill="#E69F00" />
                  </g>
                );
              })}
            </svg>
          ) : <p className="muted">No pacing plan was used for this ride.</p>}
          <h2>Time in power zones</h2>
          <table><tbody>{zones.map((t, i) => <tr key={i}><td>Z{i + 1}</td><td className="num">{fmtDuration(t)}</td></tr>)}</tbody></table>
        </section>
        <section className="card">
          <h2>Splits vs earlier attempts</h2>
          <table>
            <thead><tr><th>Mark</th><th className="num">This ride</th>{others.map((o) => <th key={o.id} className="num">{new Date(o.startedAt).toLocaleDateString()}</th>)}</tr></thead>
            <tbody>
              {[...fiveK, ...marks].sort((a, b) => a - b).slice(0, 40).map((mk) => {
                const t = splitTimes(ride.records, [mk])[0];
                return (
                  <tr key={mk}><td>{fmtDist(mk, u)}</td><td className="num">{fmtDuration(t)}</td>
                    {others.map((o) => { const t2 = splitTimes(o.records, [mk])[0]; return <td key={o.id} className="num">{fmtDuration(t2)} <small>{isFinite(t) && isFinite(t2) ? `${t2 - t > 0 ? "+" : ""}${Math.round(t2 - t)}s` : ""}</small></td>; })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <button className="primary" onClick={() => go("home")}>Ride again</button>
        </section>
      </div>
    </main>
  );
}
