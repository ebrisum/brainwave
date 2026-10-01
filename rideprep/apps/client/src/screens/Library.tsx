import { useEffect, useState } from "react";
import { CourseListItem, listCourses } from "../api";
import { useApp } from "../store";
import { fmtDist, fmtElev } from "../units";

export function Library() {
  const { go, settings } = useApp();
  const [items, setItems] = useState<CourseListItem[] | null>(null);
  const [error, setError] = useState<string>();
  useEffect(() => {
    listCourses().then(setItems).catch((e) => setError(String(e)));
  }, []);
  const u = settings.units;
  return (
    <main className="page">
      <header className="pagehead">
        <h1>RidePrep</h1>
        <div className="row">
          <button onClick={() => go("settings")}>Rider &amp; settings</button>
          <button className="primary" onClick={() => go("upload")}>Upload course</button>
        </div>
      </header>
      <p className="muted">Ride the real course indoors: terrain, surfaces, corners, and wind that behaves like on race day.</p>
      {error && <p className="warn">Cannot reach the course builder API ({error}). Start it with <code>docker compose up</code>.</p>}
      {items && items.length === 0 && <div className="empty"><p>No courses yet.</p><button className="primary" onClick={() => go("upload")}>Upload a GPX, TCX or FIT file</button></div>}
      <div className="cards">
        {items?.map((c) => (
          <button key={c.courseId} className="card course" onClick={() => go("briefing", { courseId: c.courseId })}>
            <h3>{c.name}</h3>
            <div className="kpis">
              <span><b>{fmtDist(c.stats.distanceM, u)}</b>distance</span>
              <span><b>{fmtElev(c.stats.ascentM, u)}</b>ascent</span>
              <span><b>{c.climbs}</b>climbs</span>
              <span><b>{c.stats.laps}</b>laps</span>
            </div>
            <small className="muted">{c.eventStart ? `Event ${new Date(c.eventStart).toLocaleString()}` : "No event date"} · {c.tier} tier</small>
          </button>
        ))}
      </div>
    </main>
  );
}
