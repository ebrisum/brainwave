import { useEffect, useMemo, useState } from "react";
import { LoadedCourse } from "@rideprep/course-format";
import { ClimatologyJson } from "@rideprep/physics";
import { refreshWeather } from "../api";
import { AnalysisResult, runAnalysis } from "../analysis/run";
import { ElevationProfile, ExposureLegend, GradeLegend } from "../components/ElevationProfile";
import { WindRose } from "../components/WindRose";
import { cache, getCourse, startEpochOf } from "../courseCache";
import { useApp } from "../store";
import { compass, fmtDist, fmtDuration, fmtElev, fmtSpeed, fmtTemp } from "../units";

export function Briefing() {
  const { courseId, settings, go, scenario } = useApp();
  const [course, setCourse] = useState<LoadedCourse>();
  const [analysis, setAnalysis] = useState<AnalysisResult | undefined>(cache.analysis);
  const [error, setError] = useState<string>();
  const [ifTarget, setIfTarget] = useState(0.8);
  const [busy, setBusy] = useState(false);
  const [manual, setManual] = useState({ u10: 8, dirDeg: 270, tempC: 15, precipMmH: 0 });
  const u = settings.units;

  useEffect(() => {
    if (!courseId) return;
    getCourse(courseId).then(setCourse).catch((e) => setError(String(e)));
  }, [courseId]);

  const startEpoch = useMemo(() => (course ? startEpochOf(course) : Date.now() / 1000), [course]);

  const analyse = (optimizeFor = scenario) => {
    if (!course) return;
    setBusy(true);
    runAnalysis(course, settings.rider, { powerW: settings.rider.ftpW * ifTarget, startEpoch, optimizeFor, ifTarget })
      .then((a) => { cache.analysis = a; setAnalysis(a); })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false));
  };
  useEffect(() => { if (course && !analysis) analyse(); }, [course]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <main className="page"><p className="warn">{error}</p><button onClick={() => go("library")}>Back</button></main>;
  if (!course) return <main className="page"><p>Loading course…</p></main>;
  const m = course.manifest;
  const seg = m.segments;
  const clim = course.climatology as ClimatologyJson;
  const sel = analysis?.scenarios.find((s) => s.name === scenario) ?? analysis?.scenarios[0];
  const plan = analysis?.plan;
  const tech = seg.corners.filter((c) => c.vMaxDryKmh < 35);

  const applyManual = async () => {
    setBusy(true);
    try {
      const w = await refreshWeather(m.courseId, { weather: "manual", manual: { ...manual, gust10: manual.u10 * 1.5, rh: 0.75, pMslHpa: 1013 } });
      course.weatherJson = w;
      cache.analysis = undefined;
      useApp.setState({ scenario: "weather" });
      analyse("weather");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="page">
      <header className="pagehead">
        <button onClick={() => go("library")}>← Library</button>
        <h1>{m.name}</h1>
        <div className="row">
          <button onClick={() => go("ride", { camera: "flyover" })}>Fly over</button>
          <button className="primary" onClick={() => go("pairing", { plan: plan ? { segmentM: plan.segmentM, watts: plan.watts } : undefined })}>Ride this course</button>
        </div>
      </header>
      <div className="kpis big">
        <span><b>{fmtDist(m.stats.distanceM, u)}</b>distance</span>
        <span><b>{fmtElev(m.stats.ascentM, u)}</b>ascent</span>
        <span><b>{m.stats.maxGradePct.toFixed(1)} %</b>max grade</span>
        <span><b>{seg.climbs.length}</b>climbs</span>
        <span><b>{tech.length}</b>technical corners</span>
        <span><b>{m.stats.laps}</b>laps</span>
        {m.eventStart && <span><b>{new Date(m.eventStart).toLocaleDateString()}</b>event</span>}
      </div>
      <section className="card">
        <ElevationProfile route={course.route} climbs={seg.climbs} exposure={sel?.exposure} height={190} />
        <div className="row spread"><GradeLegend /><ExposureLegend /></div>
      </section>

      <div className="grid2">
        <section className="card">
          <h2>Weather scenarios</h2>
          <div className="segmented">
            {analysis?.scenarios.map((s) => (
              <button key={s.name} className={s.name === sel?.name ? "on" : ""} onClick={() => useApp.setState({ scenario: s.name })}>{s.label}</button>
            ))}
          </div>
          {busy && <p className="muted">Running predictions…</p>}
          {analysis && (
            <table>
              <thead><tr><th>Scenario</th><th>Wind</th><th className="num">Time @ {Math.round(settings.rider.ftpW * ifTarget)} W</th><th className="num">Avg</th><th className="num">Braking</th></tr></thead>
              <tbody>
                {analysis.scenarios.map((s) => (
                  <tr key={s.name} className={s.name === sel?.name ? "sel" : ""}>
                    <td>{s.label}</td><td>{s.u10.toFixed(1)} m/s {compass(s.dirDeg)}</td><td className="num">{fmtDuration(s.totalTimeS)}</td>
                    <td className="num">{fmtSpeed(s.avgSpeed, u)}</td><td className="num">{fmtDuration(s.brakingTimeS)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <details>
            <summary>Manual scenario (“what if it’s 35 km/h from the north-west?”)</summary>
            <div className="row form">
              <label>Wind (m/s)<input type="number" value={manual.u10} onChange={(e) => setManual({ ...manual, u10: Number(e.target.value) })} /></label>
              <label>From (°)<input type="number" value={manual.dirDeg} onChange={(e) => setManual({ ...manual, dirDeg: Number(e.target.value) })} /></label>
              <label>Temp (°C)<input type="number" value={manual.tempC} onChange={(e) => setManual({ ...manual, tempC: Number(e.target.value) })} /></label>
              <label>Rain (mm/h)<input type="number" value={manual.precipMmH} onChange={(e) => setManual({ ...manual, precipMmH: Number(e.target.value) })} /></label>
              <button onClick={applyManual} disabled={busy}>Apply</button>
            </div>
          </details>
          <p className="muted">Weather: {course.weatherJson.mode} ({course.weatherJson.source}). Typical: {fmtTemp(clim.tempC.p50, u)}, rain chance {Math.round(clim.rainProbability * 100)} %.</p>
        </section>
        <section className="card center">
          <h2>Wind rose</h2>
          <WindRose freq={clim.windRose.freq} speedBins={clim.windRose.speedBinsMs} highlightDeg={clim.modalDirDeg} />
          <p className="muted">{clim.source === "generic-fallback" ? "Generic climatology (weather provider unavailable)" : `${clim.years?.[0]}–${clim.years?.[1]} around ${clim.window.monthDayCentre}`}</p>
        </section>
      </div>

      <div className="grid2">
        <section className="card">
          <h2>Climbs</h2>
          <table>
            <thead><tr><th>Start</th><th className="num">Length</th><th className="num">Avg</th><th className="num">Max</th><th className="num">Gain</th><th>Cat</th><th className="num">Time ({sel?.label ?? "–"})</th></tr></thead>
            <tbody>
              {seg.climbs.map((c, i) => (
                <tr key={c.id}><td>{fmtDist(c.sStart, u)}</td><td className="num">{fmtDist(c.lengthM, u, 2)}</td><td className="num">{c.avgGradePct.toFixed(1)} %</td>
                  <td className="num">{c.maxGradePct.toFixed(1)} %</td><td className="num">{fmtElev(c.gainM, u)}</td><td>{c.category}</td>
                  <td className="num">{sel ? fmtDuration(sel.climbTimes[i]) : "–"}</td></tr>
              ))}
              {seg.climbs.length === 0 && <tr><td colSpan={7} className="muted">No climbs ≥ 500 m at ≥ 3 %.</td></tr>}
            </tbody>
          </table>
          <h2>Technical corners</h2>
          <table>
            <thead><tr><th>At</th><th>Turn</th><th className="num">Radius</th><th className="num">Max dry / wet</th></tr></thead>
            <tbody>
              {seg.corners.slice(0, 40).map((c) => (
                <tr key={c.id}><td>{fmtDist(c.s, u, 2)}</td><td>{c.hairpin ? "hairpin " : ""}{c.direction} {Math.abs(c.turnDeg)}°</td>
                  <td className="num">{c.radiusM.toFixed(0)} m</td><td className="num">{c.vMaxDryKmh.toFixed(0)} / {c.vMaxWetKmh.toFixed(0)} km/h</td></tr>
              ))}
            </tbody>
          </table>
          <h2>Surfaces</h2>
          <table>
            <tbody>{seg.surfaceRuns.filter((r) => r.surface !== "asphalt").slice(0, 30).map((r, i) => (
              <tr key={i}><td>{fmtDist(r.sStart, u, 2)}–{fmtDist(r.sEnd, u, 2)}</td><td>{r.surface}</td><td className="num">Crr ×{r.crrMultiplier}</td></tr>
            ))}</tbody>
          </table>
        </section>
        <section className="card">
          <h2>Pacing plan</h2>
          <div className="row form">
            <label>Target IF<input type="number" step="0.01" min="0.5" max="1.1" value={ifTarget} onChange={(e) => setIfTarget(Number(e.target.value))} /></label>
            <button onClick={() => analyse(scenario)} disabled={busy}>Optimise for {sel?.label ?? "scenario"}</button>
          </div>
          {plan && (
            <>
              <p>Constant {Math.round(settings.rider.ftpW * ifTarget)} W: <b>{fmtDuration(plan.baselineS)}</b> → optimised plan: <b>{fmtDuration(plan.totalTimeS)}</b>{" "}
                ({fmtDuration(plan.baselineS - plan.totalTimeS)} faster at NP {Math.round(plan.npW)} W).</p>
              <PlanChart watts={plan.watts} target={settings.rider.ftpW * ifTarget} />
              <table>
                <thead><tr><th>Section</th><th className="num">Target</th></tr></thead>
                <tbody>
                  {groupPlan(plan.watts, plan.segmentM, 5000).map((g) => (
                    <tr key={g.s0}><td>{fmtDist(g.s0, u)}–{fmtDist(g.s1, u)}</td><td className="num">{Math.round(g.w)} W</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          <h2>Points of interest</h2>
          <ul className="pois">{seg.pois.slice(0, 30).map((p, i) => <li key={i}>{fmtDist(p.s, u, 2)} · {p.name || p.type} <span className="muted">({p.type})</span></li>)}</ul>
        </section>
      </div>
      <footer className="attribution">{m.attribution.join(" · ")}</footer>
    </main>
  );
}

function groupPlan(w: number[], segM: number, groupM: number) {
  const out: { s0: number; s1: number; w: number }[] = [];
  const k = Math.round(groupM / segM);
  for (let i = 0; i < w.length; i += k) {
    const part = w.slice(i, i + k);
    out.push({ s0: i * segM, s1: (i + part.length) * segM, w: part.reduce((a, b) => a + b, 0) / part.length });
  }
  return out;
}

function PlanChart({ watts, target }: { watts: number[]; target: number }) {
  const W = 600, H = 120;
  const max = Math.max(...watts, target) * 1.05;
  const min = Math.min(...watts, target) * 0.9;
  const y = (v: number) => H - ((v - min) / (max - min)) * H;
  const bw = W / watts.length;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="planchart" role="img" aria-label="Target power per 500 m">
      {watts.map((v, i) => <rect key={i} x={i * bw} y={y(v)} width={Math.max(bw - 0.5, 0.5)} height={H - y(v)} fill={v > target ? "#E69F00" : "#56B4E9"} />)}
      <line x1={0} x2={W} y1={y(target)} y2={y(target)} stroke="#fff" strokeDasharray="4 4" />
    </svg>
  );
}
