import { useEffect, useRef, useState } from "react";
import { BuildEvent, buildEvents, uploadCourse } from "../api";
import { useApp } from "../store";

const STAGES = ["ingest", "match", "profile", "corridor", "structure", "wind", "weather", "quick", "bake", "export-web", "export-unreal", "validate"];

interface StageRow { status: "waiting" | "running" | "done" | "cached" | "skipped" | "failed"; duration?: number; fraction?: number; note?: string }

export function Upload() {
  const { go } = useApp();
  const [file, setFile] = useState<File>();
  const [name, setName] = useState("");
  const [eventStart, setEventStart] = useState("");
  const [tier, setTier] = useState<"quick" | "full">("full");
  const [weather, setWeather] = useState("climatology");
  const [rows, setRows] = useState<Record<string, StageRow>>({});
  const [warnings, setWarnings] = useState<string[]>([]);
  const [courseId, setCourseId] = useState<string>();
  const [state, setState] = useState<"idle" | "building" | "done" | "error">("idle");
  const [error, setError] = useState<string>();
  const stop = useRef<() => void>(undefined);
  useEffect(() => () => stop.current?.(), []);

  const onEvent = (e: BuildEvent) => {
    if (e.event === "stage_start") setRows((r) => ({ ...r, [e.stage!]: { status: "running" } }));
    else if (e.event === "stage_progress") setRows((r) => ({ ...r, [e.stage!]: { ...r[e.stage!], status: "running", fraction: e.fraction, note: e.message } }));
    else if (e.event === "stage_end") setRows((r) => ({ ...r, [e.stage!]: { status: (e.status as StageRow["status"]) ?? "done", duration: e.duration_s } }));
    else if (e.event === "warning") setWarnings((w) => [...w, e.message!]);
    else if (e.event === "course_id" || (e.event === "done" && e.courseId)) setCourseId(e.courseId);
    else if (e.event === "error") { setError(e.message); setState("error"); }
    else if (e.event === "closed") setState((s) => (s === "error" ? s : "done"));
  };

  const start = async () => {
    if (!file) return;
    setState("building");
    setRows({});
    setWarnings([]);
    try {
      const r = await uploadCourse(file, { name: name || undefined, eventStart: eventStart ? new Date(eventStart).toISOString() : undefined, tier, weather });
      if (r.status === "ready" && r.courseId) {
        setCourseId(r.courseId);
        setState("done");
        return;
      }
      stop.current = buildEvents(r.buildId, onEvent);
    } catch (e) {
      setError(String(e));
      setState("error");
    }
  };

  return (
    <main className="page narrow">
      <header className="pagehead"><button onClick={() => go("library")}>← Library</button><h1>Upload course</h1></header>
      <section className="card form">
        <label>Course file (.gpx, .tcx, .fit)<input type="file" accept=".gpx,.tcx,.fit" onChange={(e) => setFile(e.target.files?.[0])} /></label>
        <label>Name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="From the file if empty" /></label>
        <label>Planned start (drives weather, foliage season, sun)<input type="datetime-local" value={eventStart} onChange={(e) => setEventStart(e.target.value)} /></label>
        <div className="row">
          <label>Quality tier<select value={tier} onChange={(e) => setTier(e.target.value as "quick" | "full")}><option value="full">Full (baked chunks)</option><option value="quick">Quick only</option></select></label>
          <label>Weather<select value={weather} onChange={(e) => setWeather(e.target.value)}>
            <option value="climatology">Climatology (typical)</option><option value="forecast">Forecast (≤16 days)</option>
          </select></label>
        </div>
        <button className="primary" disabled={!file || state === "building"} onClick={start}>{state === "building" ? "Building…" : "Build course"}</button>
      </section>
      {state !== "idle" && (
        <section className="card">
          <h2>Build progress</h2>
          <table className="stages">
            <tbody>
              {STAGES.map((s) => {
                const r = rows[s];
                return (
                  <tr key={s} className={r?.status ?? "waiting"}>
                    <td>{s}</td>
                    <td>{r?.status ?? "waiting"}{r?.status === "running" && r.fraction !== undefined ? ` ${Math.round(r.fraction * 100)} %` : ""}</td>
                    <td className="num">{r?.duration !== undefined ? `${r.duration.toFixed(1)} s` : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {warnings.length > 0 && <details><summary>{warnings.length} warnings</summary><ul>{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></details>}
          {error && <p className="warn">{error}</p>}
          {state === "done" && courseId && <button className="primary" onClick={() => go("briefing", { courseId })}>Open course briefing</button>}
        </section>
      )}
    </main>
  );
}
