export type Position = "hoods" | "drops" | "aero";

export const CDA_PRESETS: Record<Position, number> = { hoods: 0.34, drops: 0.3, aero: 0.24 };

export interface RiderProfile {
  riderMassKg: number;
  bikeMassKg: number;
  /** Base CdA, m². */
  cda: number;
  /** Optional CdA(yaw) table: [yawDeg, cda] pairs, ascending, symmetric in |yaw|. */
  cdaYaw?: [number, number][];
  crrBase: number;
  drivetrainEfficiency: number;
  /** Total wheel moment of inertia, kg·m². */
  wheelInertia: number;
  wheelRadiusM: number;
  ftpW: number;
  wPrimeJ: number;
  maxHr?: number;
}

export const DEFAULT_RIDER: RiderProfile = {
  riderMassKg: 75,
  bikeMassKg: 8.5,
  cda: CDA_PRESETS.drops,
  crrBase: 0.004,
  drivetrainEfficiency: 0.975,
  wheelInertia: 0.14,
  wheelRadiusM: 0.335,
  ftpW: 280,
  wPrimeJ: 20000,
};

export function totalMass(r: RiderProfile): number {
  return r.riderMassKg + r.bikeMassKg;
}

/** Effective translational mass including wheel rotational inertia. */
export function effectiveMass(r: RiderProfile): number {
  return totalMass(r) + r.wheelInertia / (r.wheelRadiusM * r.wheelRadiusM);
}

/** CdA at yaw angle β (radians). Falls back to the base CdA without a table. */
export function cdaAtYaw(r: RiderProfile, yawRad: number): number {
  const t = r.cdaYaw;
  if (!t || t.length === 0) return r.cda;
  const y = Math.abs(yawRad) * (180 / Math.PI);
  if (y <= t[0][0]) return t[0][1];
  for (let i = 1; i < t.length; i++) {
    if (y <= t[i][0]) {
      const [y0, c0] = t[i - 1];
      const [y1, c1] = t[i];
      return c0 + ((c1 - c0) * (y - y0)) / (y1 - y0);
    }
  }
  return t[t.length - 1][1];
}
