/**
 * Push text per language, from the alert's kind and facts (meta). The
 * database's English title/body stays the fallback for unknown kinds.
 */
export type Lang = "en" | "nl";

export interface AlertRow {
  kind: string;
  title: string;
  body: string;
  meta?: { zone?: string | null; battery?: number | null; last_seen_at?: string | null } | null;
}

const TEXT: Record<Lang, Record<string, [string, string]>> = {
  en: {
    zone_exit: ["{name} left {zone}", "Tap to see where {name} is now."],
    zone_enter: ["{name} is back in {zone}", "All good, {name} came home."],
    low_battery: ["{name}'s collar battery is low", "Battery at {pct}%. Charge it soon."],
    lost_mode: ["Lost mode on for {name}", "Positions update as often as possible. Open the app to follow live."],
    tracker_silent: ["{name}'s collar is silent", "No check-in for a while. Open the app to see the last position."],
    found: ["{name} is found", "Lost mode is off again."],
  },
  nl: {
    zone_exit: ["{name} is {zone} uit", "Tik om te zien waar {name} nu is."],
    zone_enter: ["{name} is terug in {zone}", "Alles goed, {name} is thuisgekomen."],
    low_battery: ["Batterij van de halsband van {name} is bijna leeg", "Batterij op {pct}%. Laad hem snel op."],
    lost_mode: ["Vermist-modus aan voor {name}", "Posities worden zo vaak mogelijk bijgewerkt. Open de app om live te volgen."],
    tracker_silent: ["De halsband van {name} is stil", "Al een tijd geen contact. Open de app voor de laatste positie."],
    found: ["{name} is gevonden", "Vermist-modus staat weer uit."],
  },
};

const fill = (s: string, p: Record<string, string>) => s.replace(/\{(\w+)\}/g, (m, k) => p[k] ?? m);

export function pushText(row: AlertRow, catName: string, lang: Lang): { title: string; body: string } {
  const t = TEXT[lang]?.[row.kind];
  if (!t) return { title: row.title, body: row.body };
  const zone = row.meta?.zone ?? (lang === "nl" ? "een zone" : "a zone");
  const p = { name: catName, zone, pct: row.meta?.battery != null ? String(row.meta.battery) : "?" };
  if (row.kind === "low_battery" && row.meta?.battery == null) return { title: fill(t[0], p), body: row.body };
  return { title: fill(t[0], p), body: fill(t[1], p) };
}
