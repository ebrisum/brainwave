import { CDA_PRESETS, Position } from "@rideprep/physics";
import { PhotorealSource, useApp, Quality } from "../store";

export function Settings() {
  const { settings: s, updateSettings, updateRider, go } = useApp();
  const r = s.rider;
  const num = (v: string) => (v === "" ? 0 : Number(v));
  return (
    <main className="page narrow">
      <header className="pagehead"><button onClick={() => go("home")}>← Home</button><h1>Rider profile &amp; settings</h1></header>
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
        <label className="check"><input type="checkbox" checked={s.gameArt} onChange={(e) => updateSettings({ gameArt: e.target.checked })} />Game art (regional art kit) when the course has it</label>
        <h2>Real-world view</h2>
        <label>Photoreal source<select value={s.photoreal} onChange={(e) => updateSettings({ photoreal: e.target.value as PhotorealSource })}>
          <option value="off">Off — generated world</option>
          <option value="google">Google Photorealistic 3D Tiles</option>
          <option value="dev">Dev stand-in (package tileset)</option>
          <option value="url">Custom 3D Tiles URL</option>
        </select></label>
        {s.photoreal === "google" && <label>Google Maps Platform API key (Map Tiles API)<input type="password" value={s.googleApiKey} onChange={(e) => updateSettings({ googleApiKey: e.target.value })} /></label>}
        {s.photoreal === "url" && <label>tileset.json URL<input value={s.tilesUrl} onChange={(e) => updateSettings({ tilesUrl: e.target.value })} /></label>}
        <label>Mapillary client token (street photos in the briefing)<input type="password" value={s.mapillaryToken} onChange={(e) => updateSettings({ mapillaryToken: e.target.value })} /></label>
        <p className="muted">Google tiles stream live and are never stored. They look best from a few metres up; at the roadside, trees and walls can look
          smeared. Rural coverage varies. Your key stays in this browser only — restrict it to your domain in the Google Cloud console.</p>
        <p className="muted">Trainer difficulty scales only the grade sent to the trainer; the virtual speed always comes from the full physics.</p>
      </section>
    </main>
  );
}
