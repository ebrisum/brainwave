/** Time and duration formatting shared by the cat and edit screens. */
import { locale, t } from './i18n/core.ts';

export const hhmm = (min: number) => `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;

export const fmtDuration = (s: number) =>
  s < 3600
    ? t('{m} min', { m: Math.round(s / 60) })
    : t('{h} h {m} min', { h: Math.floor(s / 3600), m: Math.round((s % 3600) / 60) });

/** "14:05" in the app's language. */
export const clock = (iso: string | number | Date) =>
  new Date(iso).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' });

/** "Sat 14 Nov" */
export const dayLabel = (d: Date) => d.toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' });

/** Parses "HH:MM" into minutes after midnight, or null when it is not a valid time. */
export function parseHHMM(text: string | null): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(text?.trim() ?? '');
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  return h < 24 && min < 60 ? h * 60 + min : null;
}

export function deviceTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Amsterdam';
  } catch {
    return 'Europe/Amsterdam';
  }
}

export const minuteOfDate = (d: Date) => d.getHours() * 60 + d.getMinutes();

export function dateAtMinute(min: number): Date {
  const d = new Date();
  d.setHours(Math.floor(min / 60), min % 60, 0, 0);
  return d;
}

/** "12 Nov" (same year) or "12 Nov 2027", for end dates. */
export function shortDate(iso: string): string {
  const d = new Date(iso);
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString(locale(), { day: 'numeric', month: 'short', ...(sameYear ? {} : { year: 'numeric' }) });
}
