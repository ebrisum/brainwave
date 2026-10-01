import { useEffect, useState } from "react";
import { addVideoSync, courseFetcher, listVideos, VideoInfo } from "../api";
import { WebBluetoothAdapter } from "@rideprep/ble";
import { cache, getCourse, startEpochOf } from "../courseCache";
import { DeviceKind, RideSession } from "../ride/RideSession";
import { ridesForCourse } from "../ride/recorder";
import { useApp } from "../store";

const ROLES: [DeviceKind, string][] = [["trainer", "Smart trainer (FTMS)"], ["power", "Power meter (CPS)"], ["hr", "Heart rate (HRS)"], ["cadence", "Cadence (CSC)"]];

export function Pairing() {
  const { courseId, settings, go, plan } = useApp();
  const [bt, setBt] = useState<boolean | null>(null);
  const [paired, setPaired] = useState<Partial<Record<DeviceKind, string>>>({});
  const [error, setError] = useState<string>();
  const [erg, setErg] = useState(false);
  const [ghost, setGhost] = useState(false);
  const [hasGhost, setHasGhost] = useState(false);
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [videoName, setVideoName] = useState("");
  const [videoFile, setVideoFile] = useState<File>();
  const [videoMsg, setVideoMsg] = useState<string>();

  useEffect(() => {
    new WebBluetoothAdapter().isAvailable().then(setBt).catch(() => setBt(false));
    if (!courseId) return;
    void ridesForCourse(courseId).then((r) => setHasGhost(r.length > 0));
    void listVideos(courseId).then((v) => { setVideos(v); if (v[0]) setVideoName(v[0].name); });
    void getCourse(courseId).then((course) => {
      cache.session?.stop();
      const ev = course.manifest.eventStart;
      cache.session = new RideSession(course, {
        rider: settings.rider, startEpoch: startEpochOf(course), cornering: settings.corneringRealism,
        gusts: settings.gusts, difficulty: settings.trainerDifficulty, plan,
      }, (h) => useApp.getState().setHud(h), (id) => useApp.getState().go("postride", { lastRideId: id }));
    });
  }, [courseId]); // eslint-disable-line react-hooks/exhaustive-deps

  const pair = async (kind: DeviceKind, virtual: boolean) => {
    setError(undefined);
    const s = cache.session;
    if (!s) return;
    try {
      const dev = await s.pair(kind, RideSession.adapter(virtual ? "virtual" : "web", settings.rider.ftpW));
      setPaired((p) => ({ ...p, [kind]: dev.name }));
    } catch (e) {
      setError(String(e));
    }
  };

  const syncTrack = async (f: File | undefined, offset: number) => {
    if (!f || !courseId) return;
    try {
      const v = await addVideoSync(courseId, f, f.name.replace(/\.[^.]+$/, ""), offset);
      setVideos((all) => [...all.filter((x) => x.name !== v.name), v]);
      setVideoName(v.name);
      setVideoMsg(`Synced ${Math.round(v.coverage * 100)} % of the course (filmed at ${(v.medianSpeedMs * 3.6).toFixed(0)} km/h)`);
    } catch (e) {
      setVideoMsg(String(e));
    }
  };

  const start = async () => {
    const s = cache.session;
    if (!s) return;
    if (cache.video) URL.revokeObjectURL(cache.video.url);
    cache.video = undefined;
    if (videoFile && videoName && courseId) {
      const buf = await courseFetcher(courseId)(`video/${videoName}.json`);
      cache.video = { sync: JSON.parse(new TextDecoder().decode(buf)), url: URL.createObjectURL(videoFile) };
    }
    s.opts.erg = erg;
    if (ghost && courseId) {
      const rides = await ridesForCourse(courseId);
      const best = rides.filter((r) => r.records.length).sort((a, b) => a.summary.durationS - b.summary.durationS)[0];
      s.opts.ghost = best?.records;
    }
    go("ride", { camera: "chase" });
  };

  return (
    <main className="page narrow">
      <header className="pagehead"><button onClick={() => go("briefing")}>← Briefing</button><h1>Pair devices</h1></header>
      {bt === false && (
        <p className="warn">Web Bluetooth is not available in this browser. Use Chrome or Edge on Windows, macOS, Linux or Android
          (Safari and iOS do not support it). You can still ride with the demo rider.</p>
      )}
      <section className="card">
        <table>
          <tbody>
            {ROLES.map(([k, label]) => (
              <tr key={k}>
                <td>{label}</td>
                <td>{paired[k] ? <b>{paired[k]}</b> : <span className="muted">not paired</span>}</td>
                <td className="row">
                  <button disabled={!bt} onClick={() => pair(k, false)}>Pair</button>
                  {(k === "trainer" || k === "power") && <button onClick={() => pair(k, true)}>Demo rider</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {error && <p className="warn">{error}</p>}
        <p className="muted">Power source priority: power meter, then trainer. Cadence: power-meter crank data, CSC, then trainer.</p>
      </section>
      <section className="card form">
        <label className="check"><input type="checkbox" checked={erg} disabled={!plan} onChange={(e) => setErg(e.target.checked)} />ERG mode: the trainer holds the pacing plan’s target power (speed still from physics)</label>
        <label className="check"><input type="checkbox" checked={ghost} disabled={!hasGhost} onChange={(e) => setGhost(e.target.checked)} />Ride against my best attempt (ghost)</label>
        <h2>Video mode (real footage)</h2>
        <p className="muted">Ride along a real video of this course: it plays at your speed. Pick the video file from this device and the
          GPX/FIT recorded while filming (with timestamps). Outside the filmed part you ride in the 3D world.</p>
        <div className="row">
          <label>Video file<input type="file" accept="video/*" onChange={(e) => setVideoFile(e.target.files?.[0])} /></label>
          <label>Synced ride<select value={videoName} onChange={(e) => setVideoName(e.target.value)}>
            <option value="">—</option>
            {videos.map((v) => <option key={v.name} value={v.name}>{v.name} ({Math.round(v.coverage * 100)} %)</option>)}
          </select></label>
        </div>
        <details>
          <summary>Add a synced ride</summary>
          <div className="row">
            <label>Recorded GPX/TCX/FIT<input type="file" accept=".gpx,.tcx,.fit" id="trackfile" /></label>
            <label>Video time at track start (s)<input type="number" step="0.1" defaultValue={0} id="trackoffset" /></label>
            <button onClick={() => syncTrack((document.getElementById("trackfile") as HTMLInputElement).files?.[0],
              Number((document.getElementById("trackoffset") as HTMLInputElement).value))}>Sync</button>
          </div>
        </details>
        {videoMsg && <p className="muted">{videoMsg}</p>}
        <button className="primary" disabled={!paired.trainer && !paired.power} onClick={start}>Start ride</button>
      </section>
    </main>
  );
}
