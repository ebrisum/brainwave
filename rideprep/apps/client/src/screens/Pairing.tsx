import { useEffect, useState } from "react";
import { WebBluetoothAdapter } from "@rideprep/ble";
import { cache, getCourse } from "../courseCache";
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

  useEffect(() => {
    new WebBluetoothAdapter().isAvailable().then(setBt).catch(() => setBt(false));
    if (!courseId) return;
    void ridesForCourse(courseId).then((r) => setHasGhost(r.length > 0));
    void getCourse(courseId).then((course) => {
      cache.session?.stop();
      const ev = course.manifest.eventStart;
      cache.session = new RideSession(course, {
        rider: settings.rider, startEpoch: ev ? Date.parse(ev) / 1000 : Date.now() / 1000, cornering: settings.corneringRealism,
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

  const start = async () => {
    const s = cache.session;
    if (!s) return;
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
        <button className="primary" disabled={!paired.trainer && !paired.power} onClick={start}>Start ride</button>
      </section>
    </main>
  );
}
