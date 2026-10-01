export type Units = "metric" | "imperial";

export const fmtSpeed = (ms: number, u: Units) => (u === "metric" ? `${(ms * 3.6).toFixed(1)} km/h` : `${(ms * 2.23694).toFixed(1)} mph`);
export const speedValue = (ms: number, u: Units) => (u === "metric" ? ms * 3.6 : ms * 2.23694);
export const speedUnit = (u: Units) => (u === "metric" ? "km/h" : "mph");
export const fmtDist = (m: number, u: Units, digits = 1) => (u === "metric" ? `${(m / 1000).toFixed(digits)} km` : `${(m / 1609.344).toFixed(digits)} mi`);
export const fmtElev = (m: number, u: Units) => (u === "metric" ? `${Math.round(m)} m` : `${Math.round(m * 3.28084)} ft`);
export const fmtTemp = (c: number, u: Units) => (u === "metric" ? `${Math.round(c)} °C` : `${Math.round(c * 1.8 + 32)} °F`);
export const fmtWind = (ms: number, u: Units) => (u === "metric" ? `${ms.toFixed(1)} m/s` : `${(ms * 2.23694).toFixed(1)} mph`);

export function fmtDuration(s: number): string {
  if (!isFinite(s)) return "–";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

const DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
export const compass = (deg: number) => DIRS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];

/** Colourblind-safe grade palette (Okabe–Ito based): descents blue, flat grey, climbs yellow → orange → vermillion → dark. */
export function gradeColor(gradePct: number): string {
  if (gradePct <= -4) return "#0072B2";
  if (gradePct <= -1.5) return "#56B4E9";
  if (gradePct < 2) return "#9aa0a6";
  if (gradePct < 4) return "#F0E442";
  if (gradePct < 7) return "#E69F00";
  if (gradePct < 10) return "#D55E00";
  return "#7a1f3d";
}

/** Apparent temperature (Steadman/BoM formula) from T (°C), RH (0–1), wind (m/s). */
export function feelsLike(tC: number, rh: number, wind: number): number {
  const e = rh * 6.105 * Math.exp((17.27 * tC) / (237.7 + tC));
  return tC + 0.33 * e - 0.7 * wind - 4;
}
