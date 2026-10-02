import { useEffect, useRef, useState } from "react";
import { ChunkRef, poseAt } from "@rideprep/course-format";
import { API, courseFetcher } from "../api";
import { ElevationProfile } from "../components/ElevationProfile";
import { MiniMap } from "../components/MiniMap";
import { cache, getCourse, getQuick, startEpochOf } from "../courseCache";
import { GameWorld } from "../engine/GameWorld";
import { RenderState, World } from "../engine/World";
import { solarPosition } from "../ride/solar";
import { VideoSync } from "../ride/videoSync";
import { CameraMode, useApp } from "../store";
import { compass, fmtDist, fmtDuration, fmtElev, fmtTemp, fmtWind, gradeColor, speedUnit, speedValue } from "../units";

const CAMS: CameraMode[] = ["chase", "cockpit", "side", "drone", "flyover"];

export function Ride() {
  const ref = useRef<HTMLCanvasElement>(null);
  const worldRef = useRef<World>(undefined);
  const { courseId, settings, camera, setCamera, go } = useApp();
  const hud = useApp((s) => s.hud);
  const [ready, setReady] = useState(false);
  const [photorealError, setPhotorealError] = useState<string>();
  const [attribution, setAttribution] = useState("");
  const [fps, setFps] = useState(0);
  const params = new URLSearchParams(location.search);
  const [flySpeed, setFlySpeed] = useState(Number(params.get("fly") ?? 60));
  const flyover = camera === "flyover" && !cache.session?.isStarted;
  const flyRef = useRef({ s: Number(params.get("s") ?? 0), speed: 60 });
  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoActive, setVideoActive] = useState(false);
  useEffect(() => {
    const v = cache.video;
    if (!v || !videoRef.current) return;
    const sync = new VideoSync(v.sync);
    const el = videoRef.current;
    el.src = v.url;
    el.muted = true;
    const t = setInterval(() => {
      const h = useApp.getState().hud;
      if (!h) return;
      setVideoActive(sync.control(el, h.s, h.speedMs, h.paused));
    }, 100);
    return () => clearInterval(t);
  }, []);
  flyRef.current.speed = flySpeed;

  useEffect(() => {
    if (!courseId || !ref.current) return;
    let disposed = false;
    let world: World | undefined;
    let poll: ReturnType<typeof setInterval> | undefined;
    (async () => {
      const course = await getCourse(courseId);
      const quick = await getQuick(courseId);
      if (disposed) return;
      const session = cache.session;
      const o = course.manifest.origin;
      const ev = startEpochOf(course);
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
      world = new World(ref.current!, course, courseFetcher(courseId), quick, settings.quality, { ...settings.rider, line: settings.roadLine },
        useSession ? () => session!.renderState() : flySource);
      worldRef.current = world;
      if (import.meta.env.DEV) Object.assign(window as object, { __rideprepWorld: world, __rideprepSession: session, __THREE: await import("three") });
      world.cameraMode = camera;
      world.enableGhost(!!session?.opts.ghost);
      const pr = params.get("photoreal") ?? settings.photoreal;
      if (pr !== "off") {
        try {
          world.setPhotoreal(pr === "dev" ? { url: `${API}/courses/${courseId}/files/devtiles/tileset.json` }
            : pr === "url" ? { url: settings.tilesUrl } : { apiKey: settings.googleApiKey });
          if (camera === "chase" && !params.get("camera")) { world.cameraMode = "cockpit"; setCamera("cockpit"); }
        } catch (e) {
          setPhotorealError(String(e));
        }
      }
      if (course.manifest.game && settings.gameArt && params.get("game") !== "0") {
        try {
          world.setGame(await GameWorld.create(course.manifest, courseFetcher(courseId), world.renderer.capabilities.getMaxAnisotropy(),
            world.renderer, world.camera));
        } catch (e) {
          console.warn("game art unavailable", e);
        }
      }
      await world.init();
      if (disposed) { world.dispose(); return; }
      world.start();
      if (useSession && !session!.isStarted) session!.start(cache.rideWeather);
      setReady(true);
      if (course.manifest.partial) {
        // Progressive streaming: pick up chunks as the server bakes them
        const f = courseFetcher(courseId);
        poll = setInterval(async () => {
          try {
            const idx = JSON.parse(new TextDecoder().decode(await f("chunks/index.json"))) as { chunks: ChunkRef[] };
            world?.chunks.setChunks(idx.chunks);
            if (idx.chunks.every((c) => c.status === "baked")) clearInterval(poll);
          } catch { /* index not written yet */ }
        }, 5000);
      }
    })().catch((e) => console.error(e));
    const onResize = () => worldRef.current?.resize();
    window.addEventListener("resize", onResize);
    const fpsTimer = setInterval(() => {
      setFps(Math.round(worldRef.current?.fps ?? 0));
      const pr = worldRef.current?.photoreal;
      if (pr) setAttribution(pr.attributions());
    }, 1000);
    return () => {
      disposed = true;
      clearInterval(fpsTimer);
      if (poll) clearInterval(poll);
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
    else go("home");
  };

  return (
    <div className="ride">
      <canvas ref={ref} className="world" style={{ visibility: videoActive ? "hidden" : "visible" }} />
      {cache.video && <video ref={videoRef} className="ridevideo" playsInline style={{ display: videoActive ? "block" : "none" }} />}
      {!ready && <div className="loading">Loading world…</div>}
      {flyover && course && (
        <div className="flybar panel">
          <b>Flyover</b> {fmtDist(flyRef.current.s, u)} · speed ×{flySpeed * 10}
          <input type="range" min="0" max="20" value={flySpeed} onChange={(e) => setFlySpeed(Number(e.target.value))} aria-label="Flyover speed" />
          <button onClick={() => go("home", { camera: "chase" })}>Close</button>
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
      {worldRef.current?.photoreal && (
        <div className="attribution3d">
          <img src="/google-logo.png" alt="Google" onError={(e) => { (e.target as HTMLImageElement).replaceWith(Object.assign(document.createElement("b"), { textContent: "Google" })); }} />
          <span>{attribution}</span>
        </div>
      )}
      {photorealError && <div className="photoreal-error panel">{photorealError}</div>}
      <div className="fps">{fps} fps</div>
    </div>
  );
}

const POWER_ZONES: [number, string, string][] = [
  [0.55, "Z1 Recovery", "#7f8c8d"], [0.75, "Z2 Endurance", "#3b9bd8"], [0.9, "Z3 Tempo", "#2ecc71"], [1.05, "Z4 Threshold", "#f1c40f"],
  [1.2, "Z5 VO₂max", "#e67e22"], [1.5, "Z6 Anaerobic", "#e74c3c"], [99, "Z7 Neuromuscular", "#9b59b6"],
];
const HR_ZONES: [number, string][] = [[0.6, "#7f8c8d"], [0.7, "#3b9bd8"], [0.8, "#2ecc71"], [0.9, "#f39c12"], [99, "#e74c3c"]];

function Hud() {
  const hud = useApp((s) => s.hud)!;
  const { settings } = useApp();
  const course = cache.course!;
  const u = settings.units;
  const seg = course.manifest.segments;
  const L = course.manifest.stats.distanceM;
  const nextClimb = seg.climbs.find((c) => c.sStart > hud.s && c.sStart - hud.s < 5000);
  const onClimb = seg.climbs.find((c) => c.sStart <= hud.s && hud.s < c.sEnd);
  const exposed = upcomingExposure(hud.s, hud.wind.u10, hud.wind.dir10);
  const inBand = hud.targetLow !== undefined ? hud.power3sW >= hud.targetLow && hud.power3sW <= hud.targetHigh! : undefined;
  const rel = hud.power3sW / Math.max(hud.ftpW, 1);
  const zi = POWER_ZONES.findIndex(([hi]) => rel < hi);
  const [, zoneName, zoneColor] = POWER_ZONES[zi];
  const hrRel = hud.hr ? hud.hr / hud.maxHr : 0;
  const hrColor = HR_ZONES.find(([hi]) => hrRel < hi)?.[1] ?? "#e74c3c";
  // Wind relative to the rider: wHead > 0 from ahead, wCross > 0 from the right
  const windAng = (Math.atan2(hud.wind.wCross, hud.wind.wHead) * 180) / Math.PI;
  const windKind = Math.abs(windAng) < 45 ? "headwind" : Math.abs(windAng) > 135 ? "tailwind" : "crosswind";
  const tr = hud.trainer;
  return (
    <div className="hud">
      <div className="panel tl">
        <div className="big num">{fmtDuration(hud.t)}</div>
        <div className="num">{fmtDist(hud.s, u)} · <span className="muted">{fmtDist(Math.max(0, L - hud.s), u)} to go</span></div>
        <div className="num">+{fmtElev(hud.ascentM, u)} · NP {Math.round(hud.npW)} · IF {hud.ifactor.toFixed(2)}</div>
        {hud.laps > 1 && <div>Lap {hud.lap}/{hud.laps}</div>}
      </div>
      <div className="cluster">
        <div className="panel tile">
          <div className="big num">{speedValue(hud.speedMs, u).toFixed(1)}</div><div className="unitlabel">{speedUnit(u)}</div>
        </div>
        <div className={`panel tile power ${inBand === undefined ? "" : inBand ? "ok" : hud.power3sW < hud.targetLow! ? "low" : "high"}`}>
          <div className="huge num">{Math.round(hud.power3sW)}<small> W</small></div>
          <div className="zonebar" aria-label={zoneName}>
            {POWER_ZONES.map(([hi, n, c], i) => <i key={n} style={{ background: c, opacity: i === zi ? 1 : 0.28 }} title={`${n} < ${Math.round(hi * 100)} % FTP`} />)}
          </div>
          <div className="zonelabel" style={{ color: zoneColor }}>{zoneName} · {(hud.power3sW / hud.massKg).toFixed(1)} W/kg</div>
          {hud.targetLow !== undefined && <div className="num small">target {Math.round(hud.targetLow)}–{Math.round(hud.targetHigh!)} W</div>}
          {hud.braking && <div className="braking">BRAKING</div>}
        </div>
        <div className="panel tile">
          <div className="big num" style={{ color: hud.hr ? hrColor : undefined }}>♥ {hud.hr ?? "–"}</div>
          <div className="unitlabel">bpm · <b className="num">{hud.cadence !== undefined ? Math.round(hud.cadence) : "–"}</b> rpm</div>
        </div>
      </div>
      <div className="rightcol">
        <div className="mapbox"><MiniMap route={course.route} s={hud.s} windFromDeg={hud.wind.dir10} /></div>
        <div className="panel windw">
          <svg viewBox="-30 -30 60 60" className="windarrow" aria-label={windKind}>
            <circle r="27" className="ring" />
            <path d="M0,-18 L5,-8 L-5,-8 Z" className="me" />
            <g transform={`rotate(${windAng})`}><line x1="0" y1="-26" x2="0" y2="-2" className="w" /><path d="M0,0 L5,-9 L-5,-9 Z" className="wt" /></g>
          </svg>
          <div>
            <b>{windKind}</b> {fmtWind(hud.wind.uRider, u)}
            <div className="muted small">{fmtWind(hud.wind.u10, u)} {compass(hud.wind.dir10)} · shelter {Math.round((1 - hud.wind.shelter) * 100)} %</div>
            <div className="muted small">{fmtTemp(hud.tempC, u)} (feels {fmtTemp(hud.feelsC, u)})</div>
          </div>
        </div>
        {tr && (
          <div className="panel trainer">
            <div className="label">TRAINER · {tr.mode === "erg" ? "ERG" : tr.mode === "simulation" ? "SIMULATION" : "RESISTANCE"}</div>
            {tr.mode === "erg" ? <div>holding <b className="num">{tr.ergW ?? "–"} W</b></div> : (
              <div className="num">
                <b>{tr.gradePct !== undefined ? `${tr.gradePct.toFixed(1)} %` : "–"}</b> grade
                {tr.windMs !== undefined && <> · {tr.windMs >= 0 ? "head" : "tail"} {Math.abs(tr.windMs).toFixed(1)} m/s</>}
                <div className="muted small">Crr {tr.crr?.toFixed(4) ?? "–"} · Cw {tr.cwKgM?.toFixed(2) ?? "–"} kg/m · difficulty {Math.round(tr.difficulty * 100)} %</div>
              </div>
            )}
            <div className="muted small">power: {hud.powerSource === "powerMeter" ? "power meter" : hud.powerSource ?? "–"} · cadence: {hud.cadenceSource ?? "–"}</div>
          </div>
        )}
      </div>
      <div className="bottom">
        <div className="ticker">
          {onClimb && <span>▲ Climbing: {fmtDist(onClimb.sEnd - hud.s, u)} to the top @ {onClimb.avgGradePct.toFixed(1)} % avg</span>}
          {!onClimb && nextClimb && <span>▸ In {fmtDist(nextClimb.sStart - hud.s, u)}: climb {fmtDist(nextClimb.lengthM, u)} @ {nextClimb.avgGradePct.toFixed(1)} %</span>}
          {exposed && <span>▸ Exposed in {fmtDist(exposed.inM, u)}: {fmtWind(exposed.u, u)} {exposed.kind}</span>}
          {Object.entries(hud.devices).filter(([, v]) => v !== "connected").map(([k, v]) => <span key={k} className="warn">▸ {k} {v}</span>)}
          {hud.warnings.map((w) => <span key={w} className="warn">▸ {w}</span>)}
        </div>
        <div className="profilerow">
          <div className="gradebadge" style={{ background: gradeColor(hud.gradePct), color: Math.abs(hud.gradePct) < 4 ? "#111" : "#fff" }}>
            <span className="num">{hud.gradePct >= 0 ? "" : "−"}{Math.abs(hud.gradePct).toFixed(1)}</span><small>%</small>
          </div>
          <div className="profiles">
            <ElevationProfile route={course.route} climbs={seg.climbs} riderS={hud.s} from={Math.max(0, hud.s - 300)} to={Math.min(L, hud.s + 2000)} height={70} />
            <ElevationProfile route={course.route} riderS={hud.s} height={36} />
          </div>
        </div>
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
