import { useEffect, useMemo, useRef, useState } from "react";
import { LoadedCourse } from "@rideprep/course-format";
import { WebBluetoothAdapter } from "@rideprep/ble";
import { basicScenarios, ClimatologyJson, CDA_PRESETS, WeatherField, WeatherJson } from "@rideprep/physics";
import { API, CourseListItem, courseFetcher, listCourses } from "../api";
import { cache, getCourse, startEpochOf } from "../courseCache";
import { DeviceKind, RideSession } from "../ride/RideSession";
import { ridesForCourse } from "../ride/recorder";
import { CameraMode, useApp } from "../store";
import { compass, fmtDist, fmtElev, fmtTemp } from "../units";

/** Ride conditions chosen on the start screen; applied to the ride physics (and the trainer) at start. */
export type ConditionsPreset = "raceday" | "calm" | "mostLikely" | "windy" | "custom";
export interface CustomConditions { windKmh: number; dirDeg: number; tempC: number; rainMmH: number; cloud: number; startTime: string }

const DEVICES: { kind: DeviceKind; label: string; hint: string; icon: string }[] = [
  { kind: "trainer", label: "Smart trainer", hint: "FTMS · resistance follows gradient & wind", icon: "⚙" },
  { kind: "power", label: "Power meter", hint: "Cycling Power · preferred power source", icon: "⚡" },
  { kind: "hr", label: "Heart rate", hint: "Chest strap or watch broadcast", icon: "♥" },
  { kind: "cadence", label: "Cadence", hint: "Crank sensor (CSC)", icon: "↻" },
];
const RAIN = [{ v: 0, l: "Dry" }, { v: 0.8, l: "Drizzle" }, { v: 3, l: "Rain" }, { v: 8, l: "Downpour" }];
const TYRES = [{ v: 0.0032, l: "Race tubeless" }, { v: 0.004, l: "Training clincher" }, { v: 0.0055, l: "4-season / gravel" }];

export function Home() {
  const { go, settings, updateSettings, updateRider, courseId, plan } = useApp();
  const u = settings.units;
  const r = settings.rider;
  const [courses, setCourses] = useState<CourseListItem[] | null>(null);
  const [apiError, setApiError] = useState<string>();
  const [course, setCourse] = useState<LoadedCourse>();
  const [hero, setHero] = useState<string>();
  const [bt, setBt] = useState<boolean | null>(null);
  const [paired, setPaired] = useState<Partial<Record<DeviceKind, string>>>({});
  const [connecting, setConnecting] = useState<DeviceKind>();
  const [pairError, setPairError] = useState<string>();
  const [live, setLive] = useState<{ powerW?: number; hr?: number; cad?: number; kmh?: number; src?: string }>({});
  const [preset, setPreset] = useState<ConditionsPreset>("raceday");
  const [custom, setCustom] = useState<CustomConditions>({ windKmh: 15, dirDeg: 250, tempC: 22, rainMmH: 0, cloud: 0.3, startTime: "" });
  const [mode, setMode] = useState<"free" | "erg" | "ghost">("free");
  const [hasGhost, setHasGhost] = useState(false);
  const [camera, setCam] = useState<CameraMode>("chase");
  const [startAt, setStartAt] = useState<string>(new URLSearchParams(location.search).get("start") ?? "0");

  useEffect(() => {
    new WebBluetoothAdapter().isAvailable().then(setBt).catch(() => setBt(false));
    listCourses().then((c) => {
      setCourses(c);
      if (!useApp.getState().courseId && c[0]) useApp.setState({ courseId: c[0].courseId });
    }).catch((e) => setApiError(String(e)));
  }, []);

  // Selected course → load it, make the session (devices pair into it), hero image, ghost availability
  useEffect(() => {
    if (!courseId) return;
    let alive = true;
    setCourse(undefined);
    setHero(undefined);
    setPaired({});
    void getCourse(courseId).then(async (c) => {
      if (!alive) return;
      setCourse(c);
      cache.session?.stop();
      cache.session = new RideSession(c, {
        rider: settings.rider, startEpoch: startEpochOf(c), cornering: settings.corneringRealism, gusts: settings.gusts,
        difficulty: settings.trainerDifficulty, plan,
      }, (h) => useApp.getState().setHud(h), (id) => useApp.getState().go("postride", { lastRideId: id }));
      const ev = new Date((startEpochOf(c) + courseUtcOffsetS(c)) * 1000);
      setCustom((cc) => ({ ...cc, startTime: `${String(ev.getUTCHours()).padStart(2, "0")}:${String(ev.getUTCMinutes()).padStart(2, "0")}` }));
      if (c.manifest.game) {
        try {
          const idx = JSON.parse(new TextDecoder().decode(await courseFetcher(courseId)(c.manifest.game.index))) as { shots?: string[] };
          if (alive && idx.shots?.length) setHero(`${API}/courses/${courseId}/files/${idx.shots[0]}`);
        } catch { /* no hero */ }
      }
      setHasGhost((await ridesForCourse(courseId)).length > 0);
    });
    return () => { alive = false; };
  }, [courseId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Live readouts from paired devices (also confirms the sensors before riding)
  useEffect(() => {
    const t = setInterval(() => {
      const h = cache.session?.hub.r;
      if (!h) return;
      setLive({ powerW: h.powerW, hr: h.heartRateBpm, cad: h.cadenceRpm, kmh: h.trainerSpeedKmh, src: h.powerSource });
    }, 400);
    return () => clearInterval(t);
  }, []);

  const pair = async (kind: DeviceKind, virtual: boolean) => {
    setPairError(undefined);
    const s = cache.session;
    if (!s) return;
    setConnecting(kind);
    try {
      const dev = await s.pair(kind, RideSession.adapter(virtual ? "virtual" : "web", r.ftpW));
      setPaired((p) => ({ ...p, [kind]: dev.name }));
    } catch (e) {
      const msg = String(e);
      if (!/cancel/i.test(msg)) setPairError(msg.replace(/^\w*Error: /, ""));
    } finally {
      setConnecting(undefined);
    }
  };

  const clim = course?.climatology as ClimatologyJson | undefined;
  const presets = useMemo(() => (clim ? basicScenarios(clim) : []), [clim]);
  const conditions = useMemo(() => describe(preset, custom, presets, course, u), [preset, custom, presets, course, u]);

  const start = () => {
    const s = cache.session;
    if (!s || !course) return;
    const w = rideWeather(preset, custom, presets, course);
    s.opts.rider = { ...settings.rider };
    s.opts.difficulty = settings.trainerDifficulty;
    s.setDifficulty(settings.trainerDifficulty);
    s.opts.gusts = settings.gusts;
    s.opts.startEpoch = startEpochFor(course, custom.startTime);
    s.opts.erg = mode === "erg" && !!plan;
    const km = Number(startAt);
    s.opts.startS = Number.isFinite(km) && km > 0 ? Math.min(km * 1000, course.manifest.stats.distanceM - 100) : undefined;
    cache.rideWeather = w;
    const go2 = async () => {
      if (mode === "ghost" && courseId) {
        const rides = await ridesForCourse(courseId);
        const best = rides.filter((x) => x.records.length).sort((a, b) => a.summary.durationS - b.summary.durationS)[0];
        s.opts.ghost = best?.records;
      }
      go("ride", { camera });
    };
    void go2();
  };

  const canStart = !!course && (!!paired.trainer || !!paired.power);
  const m = course?.manifest;
  return (
    <main className="home">
      <header className="topbar">
        <div className="brand">Ride<b>Prep</b></div>
        <nav className="row">
          <button onClick={() => go("upload")}>Upload course</button>
          <button onClick={() => go("settings")}>Settings</button>
        </nav>
      </header>

      <section className="hero" style={hero ? { backgroundImage: `linear-gradient(180deg, rgba(8,10,12,0.05) 30%, rgba(8,10,12,0.92)), url(${hero})` } : undefined}>
        <div className="hero-text">
          {m ? (
            <>
              <h1>{m.name}</h1>
              <div className="hero-stats">
                <span><b>{fmtDist(m.stats.distanceM, u)}</b>distance</span>
                <span><b>{fmtElev(m.stats.ascentM, u)}</b>climbing</span>
                <span><b>{m.stats.maxGradePct.toFixed(0)} %</b>steepest</span>
                <span><b>{m.segments.climbs.length}</b>climbs</span>
                {m.eventStart && <span><b>{new Date(m.eventStart).toLocaleDateString()}</b>race day</span>}
              </div>
              <div className="row">
                <button onClick={() => go("briefing")}>Course analysis &amp; pacing</button>
                <button onClick={() => go("ride", { camera: "flyover" })}>Fly over</button>
              </div>
            </>
          ) : <h1>{apiError ? "Course builder offline" : "Loading course…"}</h1>}
        </div>
      </section>

      {apiError && <p className="warn wrap">Cannot reach the course builder API ({apiError}). Start it with <code>docker compose up</code>.</p>}
      <section className="strip">
        {courses?.map((c) => (
          <button key={c.courseId} className={`coursechip ${c.courseId === courseId ? "on" : ""}`} onClick={() => useApp.setState({ courseId: c.courseId })}>
            <b>{c.name}</b>
            <small>{fmtDist(c.stats.distanceM, u)} · {fmtElev(c.stats.ascentM, u)}</small>
          </button>
        ))}
        <button className="coursechip add" onClick={() => go("upload")}><b>+ New course</b><small>GPX · TCX · FIT</small></button>
      </section>

      <div className="setup">
        <section className="panel">
          <h2><i>1</i>Rider</h2>
          <div className="fields">
            <label>Rider weight<span className="unit"><input type="number" min={35} max={150} step={0.5} value={r.riderMassKg} onChange={(e) => updateRider({ riderMassKg: num(e.target.value, r.riderMassKg) })} />kg</span></label>
            <label>FTP<span className="unit"><input type="number" min={80} max={600} step={5} value={r.ftpW} onChange={(e) => updateRider({ ftpW: num(e.target.value, r.ftpW) })} />W</span></label>
            <label>Max heart rate<span className="unit"><input type="number" min={120} max={230} value={r.maxHr} onChange={(e) => updateRider({ maxHr: num(e.target.value, r.maxHr) })} />bpm</span></label>
            <label>Bike weight<span className="unit"><input type="number" min={5} max={20} step={0.1} value={r.bikeMassKg} onChange={(e) => updateRider({ bikeMassKg: num(e.target.value, r.bikeMassKg) })} />kg</span></label>
          </div>
          <div className="choice">
            <span>Bike &amp; position</span>
            <div className="segmented">
              {([["road", "hoods", "Road · hoods"], ["road", "drops", "Road · drops"], ["tt", "aero", "TT · aero bars"]] as const).map(([bike, pos, l]) => (
                <button key={pos} className={r.position === pos ? "on" : ""} onClick={() => updateRider({ bike, position: pos, cda: CDA_PRESETS[pos] })}>{l}</button>
              ))}
            </div>
          </div>
          <div className="choice">
            <span>Tyres</span>
            <div className="segmented">
              {TYRES.map((t) => <button key={t.v} className={Math.abs(r.crrBase - t.v) < 1e-5 ? "on" : ""} onClick={() => updateRider({ crrBase: t.v })}>{t.l}</button>)}
            </div>
          </div>
          <div className="row spread kit">
            <label className="color">Kit colour<input type="color" value={r.jersey} onChange={(e) => updateRider({ jersey: e.target.value })} /></label>
            <span className="muted">{(r.ftpW / r.riderMassKg).toFixed(2)} W/kg FTP · CdA {r.cda.toFixed(2)} m²</span>
          </div>
        </section>

        <section className="panel">
          <h2><i>2</i>Devices</h2>
          {bt === false && <p className="note">This browser has no Web Bluetooth — use Chrome or Edge on Windows, macOS, Linux or Android. You can still ride with the demo rider.</p>}
          <ul className="devices">
            {DEVICES.map((d) => {
              const on = !!paired[d.kind];
              const value = deviceValue(d.kind, live);
              return (
                <li key={d.kind} className={on ? "on" : ""}>
                  <span className="icon">{d.icon}</span>
                  <span className="what"><b>{d.label}</b><small>{on ? paired[d.kind] : d.hint}</small></span>
                  <span className="value">{on && value}</span>
                  <span className="actions">
                    {on ? <span className="pill ok">connected</span> : connecting === d.kind ? <span className="pill">searching…</span> : (
                      <>
                        <button disabled={!bt} onClick={() => pair(d.kind, false)}>Connect</button>
                        {(d.kind === "trainer" || d.kind === "power") && <button className="ghost" onClick={() => pair(d.kind, true)}>Demo</button>}
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
          {pairError && <p className="warn">{pairError}</p>}
          <p className="muted small">Power: power meter first, then trainer. The trainer gets the road gradient, headwind, rolling resistance
            and your air drag several times a second, so climbs get heavier, descents lighter and headwinds harder.</p>
        </section>

        <section className="panel">
          <h2><i>3</i>Conditions</h2>
          <div className="segmented">
            {([["raceday", "Race day"], ["calm", "Calm"], ["mostLikely", "Typical"], ["windy", "Windy"], ["custom", "Custom"]] as const).map(([k, l]) => (
              <button key={k} className={preset === k ? "on" : ""} onClick={() => setPreset(k)}>{l}</button>
            ))}
          </div>
          <p className="conditions">{conditions}</p>
          {preset === "custom" && (
            <div className="custom">
              <WindDial dirDeg={custom.dirDeg} kmh={custom.windKmh} onDir={(d) => setCustom({ ...custom, dirDeg: d })} />
              <div className="sliders">
                <label>Wind <b>{Math.round(custom.windKmh)} km/h</b> from {compass(custom.dirDeg)}
                  <input type="range" min={0} max={60} step={1} value={custom.windKmh} onChange={(e) => setCustom({ ...custom, windKmh: Number(e.target.value) })} /></label>
                <label>Temperature <b>{fmtTemp(custom.tempC, u)}</b>
                  <input type="range" min={-5} max={40} step={1} value={custom.tempC} onChange={(e) => setCustom({ ...custom, tempC: Number(e.target.value) })} /></label>
                <label>Sky <b>{custom.cloud < 0.25 ? "sunny" : custom.cloud < 0.7 ? "partly cloudy" : "overcast"}</b>
                  <input type="range" min={0} max={1} step={0.05} value={custom.cloud} onChange={(e) => setCustom({ ...custom, cloud: Number(e.target.value) })} /></label>
                <div className="segmented">
                  {RAIN.map((x) => <button key={x.v} className={custom.rainMmH === x.v ? "on" : ""} onClick={() => setCustom({ ...custom, rainMmH: x.v })}>{x.l}</button>)}
                </div>
              </div>
            </div>
          )}
          <div className="row">
            <label className="inline">Start time<input type="time" value={custom.startTime} onChange={(e) => setCustom({ ...custom, startTime: e.target.value })} /></label>
            <label className="check"><input type="checkbox" checked={settings.gusts} onChange={(e) => updateSettings({ gusts: e.target.checked })} />Gusts</label>
          </div>
        </section>

        <section className="panel">
          <h2><i>4</i>Ride</h2>
          <div className="modes">
            <button className={mode === "free" ? "on" : ""} onClick={() => setMode("free")}><b>Free ride</b><small>You ride, the trainer simulates the road</small></button>
            <button className={mode === "erg" ? "on" : ""} disabled={!plan} onClick={() => setMode("erg")}><b>Pacing plan</b><small>{plan ? "Trainer holds the plan’s target power" : "Make a plan in Course analysis"}</small></button>
            <button className={mode === "ghost" ? "on" : ""} disabled={!hasGhost} onClick={() => setMode("ghost")}><b>Race my ghost</b><small>{hasGhost ? "Against your best ride here" : "Ride once to unlock"}</small></button>
          </div>
          <label className="slider">Trainer difficulty <b>{Math.round(settings.trainerDifficulty * 100)} %</b>
            <input type="range" min={0} max={1.5} step={0.05} value={settings.trainerDifficulty} onChange={(e) => updateSettings({ trainerDifficulty: Number(e.target.value) })} />
            <small className="muted">Scales only the climbs you feel; speed and time always use the real gradient.</small></label>
          <label className="inline">Start at
            <select value={startAt} onChange={(e) => setStartAt(e.target.value)}>
              <option value="0">Course start</option>
              {course?.manifest.segments.climbs.map((c, i) => (
                <option key={c.id} value={String(Math.max(0, c.sStart - 300) / 1000)}>
                  Climb {i + 1}: {fmtDist(c.lengthM, u, 1)} at {c.avgGradePct.toFixed(1)} % (km {(c.sStart / 1000).toFixed(1)})</option>
              ))}
              {startAt !== "0" && !course?.manifest.segments.climbs.some((c) => String(Math.max(0, c.sStart - 300) / 1000) === startAt) &&
                <option value={startAt}>km {startAt}</option>}
            </select></label>
          <div className="choice">
            <span>View</span>
            <div className="segmented">
              {([["chase", "Chase"], ["cockpit", "Cockpit"], ["side", "Side"], ["drone", "Drone"]] as const).map(([k, l]) => (
                <button key={k} className={camera === k ? "on" : ""} onClick={() => setCam(k)}>{l}</button>
              ))}
            </div>
          </div>
          <label className="check"><input type="checkbox" checked={settings.corneringRealism} onChange={(e) => updateSettings({ corneringRealism: e.target.checked })} />Brake for sharp corners</label>
          <button className="link" onClick={() => go("pairing")}>Video mode (ride real footage)…</button>
        </section>
      </div>

      <footer className="startbar">
        <div>
          <b>{course?.manifest.name ?? "—"}</b>
          <span className="muted"> · {mode === "free" ? "Free ride" : mode === "erg" ? "Pacing plan (ERG)" : "Ghost race"} · {conditions}</span>
        </div>
        <div className="row">
          {!paired.trainer && !paired.power && <button onClick={async () => { await pair("trainer", true); }}>Quick start with demo rider</button>}
          <button className="primary big" disabled={!canStart} onClick={start}>Start ride ▸</button>
        </div>
      </footer>
    </main>
  );
}

function num(v: string, fallback: number): number {
  const x = Number(v);
  return Number.isFinite(x) && x > 0 ? x : fallback;
}

function deviceValue(kind: DeviceKind, l: { powerW?: number; hr?: number; cad?: number; kmh?: number; src?: string }): string {
  if (kind === "trainer") return l.kmh !== undefined ? `${Math.round(l.powerW ?? 0)} W · ${l.kmh.toFixed(1)} km/h` : "";
  if (kind === "power") return l.powerW !== undefined ? `${Math.round(l.powerW)} W` : "";
  if (kind === "hr") return l.hr ? `${l.hr} bpm` : "";
  return l.cad !== undefined ? `${Math.round(l.cad)} rpm` : "";
}

/** UTC offset of the course's local time (from the event start's ISO offset; else the browser's). */
function courseUtcOffsetS(c: LoadedCourse): number {
  const ev = c.manifest.eventStart ?? "";
  const m = ev.match(/([+-])(\d\d):?(\d\d)$/);
  if (m) return (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 3600 + Number(m[3]) * 60);
  if (/Z$/.test(ev)) return 0;
  return -new Date(startEpochOf(c) * 1000).getTimezoneOffset() * 60;
}

/** Start epoch for a local "HH:MM" on the course's start date (course local time). */
function startEpochFor(c: LoadedCourse, hhmm: string): number {
  const base = startEpochOf(c);
  if (!/^\d\d:\d\d$/.test(hhmm)) return base;
  const off = courseUtcOffsetS(c);
  const local = new Date((base + off) * 1000);
  const [h, m] = hhmm.split(":").map(Number);
  return Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate(), h, m) / 1000 - off;
}

/** WeatherJson for the ride: the course's race-day field, a climatology preset, or the custom conditions. */
export function rideWeather(p: ConditionsPreset, c: CustomConditions, presets: ReturnType<typeof basicScenarios>, course: LoadedCourse): WeatherJson | undefined {
  if (p === "raceday") return undefined; // session default: the package's weather field
  if (p === "custom") {
    const u10 = c.windKmh / 3.6;
    return WeatherField.constant({ u10, dirDeg: c.dirDeg, gust10: u10 * 1.5, tempC: c.tempC, rh: c.rainMmH > 0 ? 0.92 : 0.65, pMslHpa: 1013,
      precipMmH: c.rainMmH, cloudCover: c.rainMmH > 0 ? Math.max(c.cloud, 0.85) : c.cloud, visibilityM: c.rainMmH > 3 ? 4000 : 25000 }, "manual").json;
  }
  const s = presets.find((x) => x.name === p);
  const clim = course.climatology as ClimatologyJson;
  return s ? WeatherField.constant({ cloudCover: 0.4, visibilityM: 20000, ...s.weather, tempC: s.weather.tempC ?? clim.tempC.p50 }, "scenario").json : undefined;
}

function describe(p: ConditionsPreset, c: CustomConditions, presets: ReturnType<typeof basicScenarios>, course: LoadedCourse | undefined, u: "metric" | "imperial"): string {
  if (!course) return "";
  const wind = (ms: number, dir: number) => `${Math.round(ms * 3.6)} km/h from ${compass(dir)}`;
  if (p === "custom") return `${wind(c.windKmh / 3.6, c.dirDeg)} · ${fmtTemp(c.tempC, u)} · ${RAIN.find((x) => x.v === c.rainMmH)?.l.toLowerCase() ?? "dry"}`;
  if (p === "raceday") {
    const w = course.weather.at(0, startEpochOf(course));
    return `${course.weatherJson.mode === "forecast" ? "Forecast" : course.weatherJson.mode === "historical" ? "Historical" : "Typical race day"}: ${wind(w.u10, w.dirDeg)} · ${fmtTemp(w.tempC, u)}${w.precipMmH > 0.2 ? " · rain" : ""}`;
  }
  const s = presets.find((x) => x.name === p);
  return s ? `${wind(s.weather.u10 ?? 0, s.weather.dirDeg ?? 0)} · ${fmtTemp(s.weather.tempC ?? 15, u)} (from climatology)` : "";
}

/** Compass dial: click a direction the wind blows FROM. */
function WindDial({ dirDeg, kmh, onDir }: { dirDeg: number; kmh: number; onDir: (d: number) => void }) {
  const ref = useRef<SVGSVGElement>(null);
  const click = (e: React.MouseEvent) => {
    const b = ref.current!.getBoundingClientRect();
    const x = e.clientX - (b.left + b.width / 2), y = e.clientY - (b.top + b.height / 2);
    const d = (Math.atan2(x, -y) * 180) / Math.PI;
    onDir(Math.round(((d + 360) % 360) / 22.5) * 22.5 % 360);
  };
  const a = (dirDeg * Math.PI) / 180;
  const len = 18 + Math.min(kmh, 60) * 0.45;
  // Arrow points the way the wind blows (from dirDeg toward the centre and beyond)
  const fx = 60 + Math.sin(a) * 46, fy = 60 - Math.cos(a) * 46;
  const tx = 60 + Math.sin(a) * (46 - len * 1.6), ty = 60 - Math.cos(a) * (46 - len * 1.6);
  return (
    <svg ref={ref} className="winddial" viewBox="0 0 120 120" onClick={click} role="img" aria-label={`Wind from ${compass(dirDeg)}`}>
      <circle cx="60" cy="60" r="52" className="ring" />
      {["N", "E", "S", "W"].map((l, i) => (
        <text key={l} x={60 + Math.sin((i * Math.PI) / 2) * 42} y={64 - Math.cos((i * Math.PI) / 2) * 42} textAnchor="middle">{l}</text>
      ))}
      <defs><marker id="ah" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 z" className="tip" /></marker></defs>
      <line x1={fx} y1={fy} x2={tx} y2={ty} className="arrow" markerEnd="url(#ah)" />
      <circle cx={fx} cy={fy} r="4" className="from" />
    </svg>
  );
}
