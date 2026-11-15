/**
 * A day as a story: at home, out (with how far), and the places the cat
 * stopped for a while. Built from the day's positions and the cat's zones,
 * with the same "inside" rule the alerts use.
 */
import type { HomeZone, TrackPoint } from './backend/types';
import { distanceM } from './geo.ts';

export type TimelineEntry =
  | { kind: 'zone'; zoneName: string; from: string; to: string }
  | { kind: 'out'; from: string; to: string; distanceM: number; farthestM: number }
  | { kind: 'stop'; from: string; to: string; lat: number; lng: number };

/** A stop: at least this long within STOP_RADIUS_M, outside every zone. */
const STOP_MIN_S = 10 * 60;
const STOP_RADIUS_M = 40;
/** Points with worse accuracy than this are ignored (a fix in the wrong garden). */
const MAX_ACCURACY_M = 80;

const zoneOf = (p: TrackPoint, zones: readonly HomeZone[]) =>
  zones.find((z) => distanceM(z.lat, z.lng, p.lat, p.lng) <= z.radiusM + Math.min(p.accuracyM, 30) / 2) ?? null;

export function buildTimeline(track: readonly TrackPoint[], zones: readonly HomeZone[]): TimelineEntry[] {
  const pts = track.filter((p) => p.accuracyM <= MAX_ACCURACY_M);
  if (pts.length === 0) return [];
  const home = zones[0] ?? null;
  const out: TimelineEntry[] = [];

  let i = 0;
  while (i < pts.length) {
    const z = zoneOf(pts[i]!, zones);
    let j = i;
    while (j + 1 < pts.length && (zoneOf(pts[j + 1]!, zones)?.id ?? null) === (z?.id ?? null)) j++;
    const run = pts.slice(i, j + 1);
    const from = run[0]!.at;
    // Each block ends where the next begins, so the day has no gaps.
    const to = j + 1 < pts.length ? pts[j + 1]!.at : run[run.length - 1]!.at;
    if (z) {
      out.push({ kind: 'zone', zoneName: z.name, from, to });
    } else {
      let dist = 0;
      let farthest = 0;
      run.forEach((p, k) => {
        if (k > 0) dist += distanceM(run[k - 1]!.lat, run[k - 1]!.lng, p.lat, p.lng);
        if (home) farthest = Math.max(farthest, distanceM(home.lat, home.lng, p.lat, p.lng) - home.radiusM);
      });
      out.push({ kind: 'out', from, to, distanceM: Math.round(dist), farthestM: Math.max(0, Math.round(farthest)) });
      for (const s of stops(run)) out.push(s);
    }
    i = j + 1;
  }
  return out;
}

function stops(run: readonly TrackPoint[]): TimelineEntry[] {
  const found: TimelineEntry[] = [];
  let a = 0;
  while (a < run.length) {
    let b = a;
    while (b + 1 < run.length && distanceM(run[a]!.lat, run[a]!.lng, run[b + 1]!.lat, run[b + 1]!.lng) <= STOP_RADIUS_M) b++;
    const seconds = (Date.parse(run[b]!.at) - Date.parse(run[a]!.at)) / 1000;
    if (seconds >= STOP_MIN_S) {
      const span = run.slice(a, b + 1);
      found.push({
        kind: 'stop', from: run[a]!.at, to: run[b]!.at,
        lat: span.reduce((s, p) => s + p.lat, 0) / span.length,
        lng: span.reduce((s, p) => s + p.lng, 0) / span.length,
      });
      a = b + 1;
    } else {
      a++;
    }
  }
  return found;
}

/** Start and end of a calendar day in local time, as ISO strings. */
export function dayRange(day: Date): { from: string; to: string } {
  const start = new Date(day);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { from: start.toISOString(), to: end.toISOString() };
}
