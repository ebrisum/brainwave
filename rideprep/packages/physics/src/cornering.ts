import { G } from "./constants";

export interface CorneringParams {
  enabled: boolean;
  aLatDry: number;
  aLatWet: number;
  aBrakeDry: number;
  aBrakeWet: number;
  lookAheadM: number;
}

export const DEFAULT_CORNERING: CorneringParams = {
  enabled: true,
  aLatDry: 0.55 * G,
  aLatWet: 0.35 * G,
  aBrakeDry: 0.5 * G,
  aBrakeWet: 0.3 * G,
  lookAheadM: 200,
};

/** Maximum corner speed (m/s) for a radius (m). Infinite radius → Infinity. */
export function cornerSpeedLimit(radiusM: number, wet: boolean, p: CorneringParams = DEFAULT_CORNERING): number {
  if (!isFinite(radiusM) || radiusM <= 0) return Infinity;
  return Math.sqrt((wet ? p.aLatWet : p.aLatDry) * radiusM);
}

/** Rider lean angle (rad) for speed and radius. */
export function leanAngle(v: number, radiusM: number): number {
  if (!isFinite(radiusM) || radiusM <= 0) return 0;
  return Math.atan((v * v) / (G * radiusM));
}

/**
 * Decide whether braking is needed now. `ahead` yields (distanceAhead, vMax) pairs for upcoming samples.
 * Brake when the speed after braking at a_brake over the remaining distance would still exceed vMax.
 */
export function needsBraking(
  v: number,
  ahead: Iterable<[number, number]>,
  wet: boolean,
  p: CorneringParams = DEFAULT_CORNERING,
): boolean {
  if (!p.enabled) return false;
  const aBrake = wet ? p.aBrakeWet : p.aBrakeDry;
  const margin = 0.1;
  for (const [d, vMax] of ahead) {
    if (v <= vMax + margin) continue;
    const dNeeded = (v * v - vMax * vMax) / (2 * aBrake);
    if (dNeeded >= d) return true;
  }
  return false;
}
