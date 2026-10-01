import { CDA_PRESETS, Position } from "@rideprep/physics";
import { useApp, Quality } from "../store";

export function Settings() {
  const { settings: s, updateSettings, updateRider, go } = useApp();
  const r = s.rider;
  const num = (v: string) => (v === "" ? 0 : Number(v));
  return (
    <main className="page narrow">
      <header className="pagehead"><button onClick={() => go("library")}>← Library</button><h1>Rider profile &amp; settings</h1></header>
      <section className="card form grid2">
        <h2>Rider</h2>
        <label>Rider mass (kg)<input type="number" value={r.riderMassKg} onChange={(e) => updateRider({ riderMassKg: num(e.target.value) })} /></label>
        <label>Bike + kit (kg)<input type="number" value={r.bikeMassKg} onChange={(e) => updateRider({ bikeMassKg: num(e.target.value) })} /></label>
        <label>FTP (W)<input type="number" value={r.ftpW} onChange={(e) => updateRider({ ftpW: num(e.target.value) })} /></label>
        <label>W′ (J)<input type="number" value={r.wPrimeJ} onChange={(e) => updateRider({ wPrimeJ: num(e.target.value) })} /></label>
        <label>Max HR (bpm)<input type="number" value={r.maxHr} onChange={(e) => updateRider({ maxHr: num(e.target.value) })} /></label>
        <label>Position<select value={r.position} onChange={(e) => updateRider({ position: e.target.value as Position })}>
          {(Object.keys(CDA_PRESETS) as Position[]).map((p) => <option key={p} value={p}>{p} (CdA {CDA_PRESETS[p]})</option>)}
        </select></label>
        <label>CdA (m²)<input type="number" step="0.005" value={r.cda} onChange={(e) => updateRider({ cda: num(e.target.value) })} /></label>
        <label>Tyre Crr<input type="number" step="0.0005" value={r.crrBase} onChange={(e) => updateRider({ crrBase: num(e.target.value) })} /></label>
        <label>Jersey colour<input type="color" value={r.jersey} onChange={(e) => updateRider({ jersey: e.target.value })} /></label>
        <label>Bike<select value={r.bike} onChange={(e) => updateRider({ bike: e.target.value as "road" | "tt" })}><option value="road">Road</option><option value="tt">TT</option></select></label>
      </section>
      <section className="card form grid2">
        <h2>App</h2>
        <label>Units<select value={s.units} onChange={(e) => updateSettings({ units: e.target.value as "metric" | "imperial" })}><option value="metric">Metric</option><option value="imperial">Imperial</option></select></label>
        <label>Graphics quality<select value={s.quality} onChange={(e) => updateSettings({ quality: e.target.value as Quality })}>
          {["low", "medium", "high", "ultra"].map((q) => <option key={q}>{q}</option>)}</select></label>
        <label>Trainer difficulty ({Math.round(s.trainerDifficulty * 100)} %)<input type="range" min="0" max="1.5" step="0.05" value={s.trainerDifficulty} onChange={(e) => updateSettings({ trainerDifficulty: num(e.target.value) })} /></label>
        <label className="check"><input type="checkbox" checked={s.corneringRealism} onChange={(e) => updateSettings({ corneringRealism: e.target.checked })} />Cornering realism (auto-brake)</label>
        <label className="check"><input type="checkbox" checked={s.gusts} onChange={(e) => updateSettings({ gusts: e.target.checked })} />Gusts</label>
        <p className="muted">Trainer difficulty scales only the grade sent to the trainer; the virtual speed always comes from the full physics.</p>
      </section>
    </main>
  );
}
