import { useEffect, useRef } from "react";
import { CourseProfile, poseAt } from "@rideprep/course-format";

/** Route map with rider dot and a wind arrow (pointing where the wind blows TO). */
export function MiniMap({ route, s, windFromDeg, size = 150 }: { route: CourseProfile; s: number; windFromDeg?: number; size?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = size * dpr;
    cv.height = size * dpr;
    const g = cv.getContext("2d")!;
    g.scale(dpr, dpr);
    g.clearRect(0, 0, size, size);
    let minx = Infinity, maxx = -Infinity, miny = Infinity, maxy = -Infinity;
    for (let i = 0; i < route.count; i += 10) {
      minx = Math.min(minx, route.x[i]); maxx = Math.max(maxx, route.x[i]); miny = Math.min(miny, route.y[i]); maxy = Math.max(maxy, route.y[i]);
    }
    const span = Math.max(maxx - minx, maxy - miny) || 1;
    const pad = 10;
    const tx = (x: number) => pad + ((x - minx) / span) * (size - 2 * pad);
    const ty = (y: number) => size - pad - ((y - miny) / span) * (size - 2 * pad);
    g.strokeStyle = "rgba(255,255,255,0.75)";
    g.lineWidth = 2;
    g.beginPath();
    for (let i = 0; i < route.count; i += 6) (i === 0 ? g.moveTo : g.lineTo).call(g, tx(route.x[i]), ty(route.y[i]));
    g.stroke();
    const p = poseAt(route, s);
    g.fillStyle = "#F0B429";
    g.beginPath(); g.arc(tx(p.x), ty(p.y), 5, 0, Math.PI * 2); g.fill();
    if (windFromDeg !== undefined) {
      const a = ((windFromDeg + 180) * Math.PI) / 180;
      const cx = size - 22, cy = 22, L = 13;
      g.strokeStyle = "#7dd3fc";
      g.lineWidth = 2.5;
      g.beginPath();
      g.moveTo(cx - L * Math.sin(a), cy + L * Math.cos(a));
      g.lineTo(cx + L * Math.sin(a), cy - L * Math.cos(a));
      g.stroke();
      g.beginPath();
      g.arc(cx + L * Math.sin(a), cy - L * Math.cos(a), 3, 0, Math.PI * 2);
      g.fillStyle = "#7dd3fc";
      g.fill();
    }
  }, [route, s, windFromDeg, size]);
  return <canvas ref={ref} style={{ width: size, height: size }} className="minimap" aria-label="Mini map" />;
}
