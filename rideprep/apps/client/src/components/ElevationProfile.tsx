import { useEffect, useRef } from "react";
import { CourseProfile, Climb } from "@rideprep/course-format";
import { gradeColor } from "../units";

export interface ExposureSeg { s0: number; s1: number; headShare: number; crossShare: number; tailShare: number; shelteredShare: number }

interface Props {
  route: CourseProfile;
  climbs?: Climb[];
  riderS?: number;
  ghostS?: number;
  from?: number;
  to?: number;
  exposure?: ExposureSeg[];
  height?: number;
  onHover?: (s: number | null) => void;
}

/** Elevation profile with colourblind-safe grade colours, climb brackets, rider dot and an optional wind-exposure ribbon. */
export function ElevationProfile({ route, climbs = [], riderS, ghostS, from = 0, to, exposure, height = 160, onHover }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const end = to ?? route.s[route.count - 1];
  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    const W = cv.clientWidth;
    const H = height;
    cv.width = W * dpr;
    cv.height = H * dpr;
    const g = cv.getContext("2d")!;
    g.scale(dpr, dpr);
    g.clearRect(0, 0, W, H);
    const ribbon = exposure ? 12 : 0;
    const top = 14, bottom = H - 16 - ribbon;
    const i0 = Math.max(0, Math.floor(from / route.spacingM));
    const i1 = Math.min(route.count - 1, Math.ceil(end / route.spacingM));
    let zmin = Infinity, zmax = -Infinity;
    for (let i = i0; i <= i1; i++) { zmin = Math.min(zmin, route.z[i]); zmax = Math.max(zmax, route.z[i]); }
    if (zmax - zmin < 20) zmax = zmin + 20;
    const px = (s: number) => ((s - from) / (end - from)) * W;
    const py = (z: number) => bottom - ((z - zmin) / (zmax - zmin)) * (bottom - top);
    // Grade-coloured fill, one column per pixel
    const step = Math.max(1, Math.floor((i1 - i0) / W));
    for (let i = i0; i < i1; i += step) {
      const j = Math.min(i + step, i1);
      const x0 = px(route.s[i]), x1 = px(route.s[j]);
      const gr = (route.z[j] - route.z[i]) / Math.max(route.s[j] - route.s[i], 1) * 100;
      g.fillStyle = gradeColor(gr);
      g.beginPath();
      g.moveTo(x0, bottom);
      g.lineTo(x0, py(route.z[i]));
      g.lineTo(x1, py(route.z[j]));
      g.lineTo(x1, bottom);
      g.closePath();
      g.fill();
    }
    g.strokeStyle = "rgba(255,255,255,0.85)";
    g.lineWidth = 1.2;
    g.beginPath();
    for (let i = i0; i <= i1; i += step) (i === i0 ? g.moveTo : g.lineTo).call(g, px(route.s[i]), py(route.z[i]));
    g.stroke();
    // Climb brackets
    g.font = "11px system-ui, sans-serif";
    g.fillStyle = "rgba(255,255,255,0.9)";
    for (const c of climbs) {
      if (c.sEnd < from || c.sStart > end) continue;
      const x0 = px(c.sStart), x1 = px(c.sEnd);
      g.strokeStyle = "rgba(255,255,255,0.6)";
      g.beginPath(); g.moveTo(x0, top - 6); g.lineTo(x0, top - 2); g.lineTo(x1, top - 2); g.lineTo(x1, top - 6); g.stroke();
      g.fillText(`${(c.lengthM / 1000).toFixed(1)} km @ ${c.avgGradePct.toFixed(1)}%`, Math.max(0, x0), top - 8 + 10);
    }
    // Exposure ribbon: head (vermillion), cross (yellow), tail (blue), sheltered (grey)
    if (exposure) {
      for (const e of exposure) {
        if (e.s1 < from || e.s0 > end) continue;
        const x0 = px(e.s0), x1 = px(e.s1);
        const shares: [number, string][] = [[e.headShare, "#D55E00"], [e.crossShare, "#F0E442"], [e.tailShare, "#0072B2"], [e.shelteredShare, "#6b7280"]];
        const best = shares.reduce((a, b) => (b[0] > a[0] ? b : a));
        g.fillStyle = best[1];
        g.fillRect(x0, H - ribbon - 2, Math.max(1, x1 - x0), ribbon);
      }
    }
    // Axis labels
    g.fillStyle = "rgba(255,255,255,0.7)";
    g.fillText(`${Math.round(zmax)} m`, 4, top + 10);
    g.fillText(`${Math.round(zmin)} m`, 4, bottom - 4);
    g.fillText(`${(from / 1000).toFixed(1)} km`, 4, H - ribbon - 4);
    const label = `${(end / 1000).toFixed(1)} km`;
    g.fillText(label, W - g.measureText(label).width - 4, H - ribbon - 4);
    const dot = (s: number, col: string) => {
      if (s < from || s > end) return;
      const i = Math.min(Math.round(s / route.spacingM), route.count - 1);
      g.fillStyle = col;
      g.beginPath(); g.arc(px(s), py(route.z[i]), 5, 0, Math.PI * 2); g.fill();
      g.strokeStyle = "#000"; g.lineWidth = 1.5; g.stroke();
    };
    if (ghostS !== undefined) dot(ghostS, "rgba(255,255,255,0.6)");
    if (riderS !== undefined) dot(riderS, "#ffffff");
  }, [route, climbs, riderS, ghostS, from, end, exposure, height]);
  return (
    <canvas ref={ref} style={{ width: "100%", height }} aria-label="Elevation profile"
      onMouseMove={(e) => { if (!onHover) return; const r = (e.target as HTMLCanvasElement).getBoundingClientRect(); onHover(from + ((e.clientX - r.left) / r.width) * (end - from)); }}
      onMouseLeave={() => onHover?.(null)} />
  );
}

export function GradeLegend() {
  const items: [string, string][] = [["≤ −4 %", gradeColor(-5)], ["−4…−1.5", gradeColor(-2)], ["flat", gradeColor(0)], ["2–4 %", gradeColor(3)],
    ["4–7 %", gradeColor(5)], ["7–10 %", gradeColor(8)], ["≥ 10 %", gradeColor(12)]];
  return (
    <div className="legend">
      {items.map(([l, c]) => <span key={l}><i style={{ background: c }} />{l}</span>)}
    </div>
  );
}

export function ExposureLegend() {
  return (
    <div className="legend">
      <span><i style={{ background: "#D55E00" }} />headwind</span><span><i style={{ background: "#F0E442" }} />crosswind</span>
      <span><i style={{ background: "#0072B2" }} />tailwind</span><span><i style={{ background: "#6b7280" }} />sheltered</span>
    </div>
  );
}
