/** "At Home" / "Out · 230 m from Home": where a cat is, for lists and headers. */
import type { Cat, CatEvent } from './backend/types';
// .ts extension so the node test runner can load this file too.
import { formatDistance } from './geo.ts';

export interface PlaceLine {
  /** Short: "At Home" or "Out". */
  title: string;
  /** Longer: "At Home" or "Out · 230 m from Home". */
  line: string;
  /** Distance part only, for a second line: "230 m from Home". */
  detail: string | null;
  inside: boolean;
}

export function placeLine(cat: Pick<Cat, 'place'>): PlaceLine | null {
  const p = cat.place;
  if (!p) return null;
  if (p.zoneName) return { title: `At ${p.zoneName}`, line: `At ${p.zoneName}`, detail: null, inside: true };
  if (p.nearestZoneName && p.nearestZoneM !== null) {
    const detail = `${formatDistance(p.nearestZoneM)} from ${p.nearestZoneName}`;
    return { title: 'Out', line: `Out · ${detail}`, detail, inside: false };
  }
  return null;
}

export type TodayEntry =
  | { kind: 'event'; id: string; transition: 'enter' | 'exit'; zoneName: string; at: string }
  | { kind: 'away'; id: string; zoneName: string; minutes: number; ongoing: boolean };

/**
 * Today's zone changes, oldest first, with "out for 1 h 28 min" between
 * leaving a zone and coming back (or until now while still out).
 */
export function todayStory(events: readonly CatEvent[], now: number = Date.now()): TodayEntry[] {
  const midnight = new Date(now);
  midnight.setHours(0, 0, 0, 0);
  const today = events
    .filter((e) => Date.parse(e.at) >= midnight.getTime() && Date.parse(e.at) <= now)
    .sort((a, b) => Date.parse(a.at) - Date.parse(b.at));

  const out: TodayEntry[] = [];
  today.forEach((e, i) => {
    out.push({ kind: 'event', id: e.id, transition: e.transition, zoneName: e.zoneName, at: e.at });
    if (e.transition !== 'exit') return;
    const back = today.slice(i + 1).find((n) => n.transition === 'enter' && n.zoneName === e.zoneName);
    const end = back ? Date.parse(back.at) : now;
    const minutes = Math.max(1, Math.round((end - Date.parse(e.at)) / 60_000));
    out.push({ kind: 'away', id: `${e.id}-away`, zoneName: e.zoneName, minutes, ongoing: !back });
  });
  return out;
}
