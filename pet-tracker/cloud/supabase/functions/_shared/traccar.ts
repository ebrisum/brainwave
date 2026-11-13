/**
 * Traccar position forwarding (forward.json = true) -> our telemetry.
 * Pure functions without imports, so they run under Deno (Edge Functions)
 * and Node (tests: node --test --experimental-strip-types).
 *
 * Traccar posts { position: {...}, device: {...} } for every position it
 * receives. Ready-made trackers report a battery level in percent
 * (attributes.batteryLevel) or only a voltage (attributes.battery).
 */

export const TRACKER_UID_RE = /^[A-Za-z0-9_-]{3,64}$/;

export type TraccarMessage =
  | {
      kind: "position";
      deviceUid: string;
      lat: number;
      lng: number;
      accuracyM: number;
      batteryPct: number | null;
      recordedAt: string;
    }
  /** Alive, but no usable position (no GPS fix indoors, or a repeated old fix). */
  | { kind: "heartbeat"; deviceUid: string; batteryPct: number | null }
  | { kind: "ignore"; reason: string };

/** When a tracker doesn't say how accurate a fix is. */
export const DEFAULT_ACCURACY_M = 25;

const obj = (v: unknown): Record<string, unknown> =>
  v !== null && typeof v === "object" ? (v as Record<string, unknown>) : {};
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Percent from batteryLevel, or estimated from a single-cell Li-ion voltage. */
export function batteryPercent(attributes: Record<string, unknown>): number | null {
  const level = num(attributes.batteryLevel);
  if (level !== null && level >= 0 && level <= 100) return Math.round(level);
  const volts = num(attributes.battery);
  if (volts !== null && volts > 2.5 && volts < 5) {
    return Math.round(Math.min(100, Math.max(0, ((volts - 3.45) / (4.15 - 3.45)) * 100)));
  }
  return null;
}

export function parseTraccarForward(body: unknown, now: number = Date.now()): TraccarMessage {
  const position = obj(obj(body).position);
  const device = obj(obj(body).device);
  const deviceUid = device.uniqueId;
  if (typeof deviceUid !== "string" || !TRACKER_UID_RE.test(deviceUid)) {
    return { kind: "ignore", reason: "missing or invalid device.uniqueId" };
  }
  const attributes = obj(position.attributes);
  const batteryPct = batteryPercent(attributes);

  const lat = num(position.latitude);
  const lng = num(position.longitude);
  const usable =
    position.valid !== false &&
    position.outdated !== true &&
    lat !== null && lng !== null &&
    Math.abs(lat) <= 90 && Math.abs(lng) <= 180 &&
    !(lat === 0 && lng === 0);
  if (!usable) return { kind: "heartbeat", deviceUid, batteryPct };

  const accuracy = num(position.accuracy);
  const hdop = num(attributes.hdop);
  const accuracyM =
    accuracy !== null && accuracy > 0
      ? Math.min(accuracy, 100_000)
      : hdop !== null && hdop > 0
        ? Math.max(5, hdop * 5)
        : DEFAULT_ACCURACY_M;

  const fix = typeof position.fixTime === "string" ? Date.parse(position.fixTime) : NaN;
  const recordedAt = new Date(Number.isFinite(fix) ? Math.min(fix, now) : now).toISOString();

  return { kind: "position", deviceUid, lat: lat!, lng: lng!, accuracyM, batteryPct, recordedAt };
}

/**
 * Fills a tracker command template, e.g. "TIMER,{seconds}#" (the real
 * syntax comes from the tracker's manual). {seconds} and {minutes} are
 * replaced; minutes are rounded up, at least 1.
 */
export function buildCommand(template: string, seconds: number): string {
  const s = Math.max(1, Math.round(seconds));
  return template.replaceAll("{seconds}", String(s)).replaceAll("{minutes}", String(Math.max(1, Math.ceil(s / 60))));
}
