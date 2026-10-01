import { useEffect, useRef, useState } from "react";
import { poseAt } from "@rideprep/course-format";
import { courseFetcher } from "../api";
import { ElevationProfile } from "../components/ElevationProfile";
import { MiniMap } from "../components/MiniMap";
import { cache, getCourse, getQuick } from "../courseCache";
import { RenderState, World } from "../engine/World";
import { solarPosition } from "../ride/solar";
import { CameraMode, useApp } from "../store";
import { compass, fmtDist, fmtDuration, fmtElev, fmtTemp, fmtWind, speedUnit, speedValue } from "../units";

const CAMS: CameraMode[] = ["chase", "first", "side", "drone", "flyover"];

export function Ride() {
  const ref = useRef<HTMLCanvasElement>(null);
  const worldRef = useRef<World>(undefined);
  const { courseId, settings, camera, setCamera, go } = useApp();
  const hud = useApp((s) => s.hud);
  const [ready, setReady] = useState(false);
  const [fps, setFps] = useState(0);
  const [flySpeed, setFlySpeed] = useState(60);
  const flyover = camera === "flyover" && !cache.session?.isStarted;
  const flyRef = useRef({ s: 0, speed: 60 });
  flyRef.current.speed = flySpeed;

  useEffect(() => {
    if (!courseId || !ref.current) return;
    let disposed = false;
    let world: World | undefined;
    (async () => {
      const course = await getCourse(courseId);
      const quick = await getQuick(courseId);
      if (disposed) return;
      const session = cache.session;
      const o = course.manifest.origin;
      const ev = course.manifest.eventStart ? Date.parse(course.manifest.eventStart) / 1000 : Date.now() / 1000;
      let lastT = performance.now();
      const flySource = (): RenderState => {
        const now = performance.now();
        const dt = (now - lastT) / 1000;
        lastT = now;
        const L = course.route.s[course.route.count - 1];
        flyRef.current.s = (flyRef.current.s + dt * 10 * flyRef.current.speed) % L;
        const w = course.weather.at(flyRef.current.s, ev);
        const sun = solarPosition(new Date(ev * 1000), o.lat, o.lon);
        const to = ((w.dirDeg + 180) * Math.PI) / 180;
        return { s: flyRef.current.s, speed: 10, leanRad: 0, crankRad: now / 300, gradePct: 0, cadence: 90, powerW: 200, windToX: Math.sin(to), windToY: Math.cos(to),
          uRider: w.u10 * 0.6, gust: 1, sunElevationDeg: sun.elevationDeg, sunAzimuthDeg: sun.azimuthDeg, cloud: w.cloudCover, visibilityM: w.visibilityM, rainMmH: w.precipMmH };
      };
      const useSession = session && camera !== "flyover";
      world = new World(ref.current!, course, courseFetcher(courseId), quick, settings.quality, settings.rider,
        useSession ? () => session!.renderState() : flySource);
      worldRef.current = world;
      world.cameraMode = camera;
      world.enableGhost(!!session?.opts.ghost);
      await world.init();
      if (disposed) { world.dispose(); return; }
      world.start();
      if (useSession && !session!.isStarted) session!.start();
      setReady(true);
    })().catch((e) => console.error(e));
    const onResize = () => worldRef.current?.resize();
    window.addEventListener("resize", onResize);
    const fpsTimer = setInterval(() => setFps(Math.round(worldRef.current?.fps ?? 0)), 1000);
    return () => {
      disposed = true;
      clearInterval(fpsTimer);
      window.removeEventListener("resize", onResize);
      worldRef.current?.dispose();
      worldRef.current = undefined;
    };
  }, [courseId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (worldRef.current) { worldRef.current.cameraMode = camera; worldRef.current.rig.reset(); }
  }, [camera]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = cache.session;
      if (e.key === " " || e.key === "p") { e.preventDefault(); if (s) (s.paused ? s.resume() : s.pause()); }
      const n = Number(e.key);
      if (n >= 1 && n <= 5) setCamera(CAMS[n - 1]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setCamera]);

  const course = cache.course;
  const u = settings.units;
  const end = async () => {
    const s = cache.session;
    if (s?.isStarted) await s.finish();
    else go("briefing");
  };

  return (
    <div className="ride">
      <canvas ref={ref} className="world" />
      {!ready && <div className="loading">Loading world…</div>}
      {flyover && course && (
        <div className="hud flybar panel">
          <b>Flyover</b> {fmtDist(flyRef.current.s, u)} · speed ×{flySpeed * 10}
          <input type="range" min="2" max="20" value={flySpeed} onChange={(e) => setFlySpeed(Number(e.target.value))} aria-label="Flyover speed" />
          <button onClick={() => go("briefing", { camera: "chase" })}>Close</button>
        </div>
      )}
      {!flyover && hud && course && <Hud />}
      {hud?.paused && (
        <div className="overlay">
          <div className="panel pause">
            <h2>Paused</h2>
            <label>Trainer difficulty ({Math.round(settings.trainerDifficulty * 100)} %)
              <input type="range" min="0" max="1.5" step="0.05" value={settings.trainerDifficulty}
                onChange={(e) => { const d = Number(e.target.value); useApp.getState().updateSettings({ trainerDifficulty: d }); cache.session?.setDifficulty(d); }} />
            </label>
            <div className="segmented">{CAMS.slice(0, 4).map((c) => <button key={c} className={c === camera ? "on" : ""} onClick={() => setCamera(c)}>{c}</button>)}</div>
            <div className="row">
              <button className="primary" onClick={() => cache.session?.resume()}>Resume</button>
              <button onClick={end}>End ride</button>
            </div>
          </div>
        </div>
      )}
      <div className="fps">{fps} fps</div>
    </div>
  );
}

function Hud() {
  const hud = useApp((s) => s.hud)!;
  const { settings } = useApp();
  const course = cache.course!;
  const u = settings.units;
  const seg = course.manifest.segments;
  const L = course.manifest.stats.distanceM;
  const nextClimb = seg.climbs.find((c) => c.sStart > hud.s && c.sStart - hud.s < 5000);
  const exposed = upcomingExposure(hud.s, hud.wind.u10, hud.wind.dir10);
  const inBand = hud.targetLow !== undefined ? hud.powerW >= hud.targetLow && hud.powerW <= hud.targetHigh! : undefined;
  return (
    <div className="hud">
      <div className="panel tl">
        <div className="big num">{hud.wkg.toFixed(1)}<small> W/kg</small></div>
        <div>NP <b className="num">{Math.round(hud.npW)}</b> · IF <b className="num">{hud.ifactor.toFixed(2)}</b></div>
        <div>Lap {hud.lap}/{hud.laps} · <span className="num">{fmtDuration(hud.t)}</span> · +{fmtElev(hud.ascentM, u)}</div>
      </div>
      <div className={`panel power ${inBand === undefined ? "" : inBand ? "ok" : hud.powerW < hud.targetLow! ? "low" : "high"}`}>
        <div className="huge num">{Math.round(hud.powerW)}<small> W</small></div>
        {hud.targetLow !== undefined && <div className="num">target {Math.round(hud.targetLow)}–{Math.round(hud.targetHigh!)} W</div>}
        {hud.braking && <div className="braking">BRAKING</div>}
      </div>
      <div className="panel tr">
        <div>HR <b className="num">{hud.hr ?? "–"}</b> · CAD <b className="num">{hud.cadence !== undefined ? Math.round(hud.cadence) : "–"}</b></div>
        <div className="big num">{speedValue(hud.speedMs, u).toFixed(1)}<small> {speedUnit(u)}</small></div>
        <div className="num">{fmtDist(hud.s, u)} / {fmtDist(L, u)} · {hud.gradePct.toFixed(1)} %</div>
      </div>
      <div className="mapbox"><MiniMap route={course.route} s={hud.s} windFromDeg={hud.wind.dir10} /></div>
      <div className="panel wind">
        <div className="label">WIND &amp; WEATHER</div>
        <div>true {fmtWind(hud.wind.u10, u)} {compass(hud.wind.dir10)}</div>
        <div>at rider {fmtWind(hud.wind.uRider, u)}</div>
        <div>{hud.wind.wHead >= 0 ? "headwind" : "tailwind"} {fmtWind(Math.abs(hud.wind.wHead), u)} · cross {fmtWind(Math.abs(hud.wind.wCross), u)}</div>
        <div>shelter {Math.round((1 - hud.wind.shelter) * 100)} %</div>
        <div>{fmtTemp(hud.tempC, u)} (feels {fmtTemp(hud.feelsC, u)}) · ρ {hud.rho.toFixed(3)}</div>
      </div>
      <div className="bottom">
        <div className="ticker">
          {nextClimb && <span>▸ In {fmtDist(nextClimb.sStart - hud.s, u)}: climb {fmtDist(nextClimb.lengthM, u)} @ {nextClimb.avgGradePct.toFixed(1)} %</span>}
          {exposed && <span>▸ Exposed in {fmtDist(exposed.inM, u)}: {fmtWind(exposed.u, u)} {exposed.kind}</span>}
          {Object.entries(hud.devices).filter(([, v]) => v !== "connected").map(([k, v]) => <span key={k} className="warn">▸ {k} {v}</span>)}
          {hud.warnings.map((w) => <span key={w} className="warn">▸ {w}</span>)}
        </div>
        <ElevationProfile route={course.route} climbs={seg.climbs} riderS={hud.s} from={Math.max(0, hud.s - 300)} to={Math.min(L, hud.s + 2000)} height={70} />
        <ElevationProfile route={course.route} riderS={hud.s} height={36} />
      </div>
    </div>
  );
}

/** First stretch in the next 2 km where the wind at the rider is notably stronger than here. */
function upcomingExposure(s: number, u10: number, dir: number): { inM: number; u: number; kind: string } | undefined {
  const c = cache.course!;
  if (u10 < 2) return undefined;
  const here = factor(s, dir);
  for (let d = 200; d <= 2000; d += 50) {
    const f = factor(s + d, dir);
    if (f > Math.max(0.55, here * 1.4)) {
      const p = poseAt(c.route, s + d);
      const rel = Math.abs(((dir - (p.headingRad * 180) / Math.PI + 540) % 360) - 180);
      const kind = rel < 45 ? "headwind" : rel > 135 ? "tailwind" : "crosswind";
      return { inM: d, u: u10 * f, kind };
    }
  }
  return undefined;
}

function factor(s: number, dir: number) {
  const f = cache.course!.wind.factors(s, dir);
  return f.fRough * f.shelter * f.topo * f.channel;
}
