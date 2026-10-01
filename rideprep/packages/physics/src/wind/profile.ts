/** Logarithmic wind profile utilities (WIND_MODEL.md §2). */

export const Z0_REF = 0.03;
export const BLEND_HEIGHT_M = 60;
export const RIDER_HEIGHT_M = 1.2;
export const Z0_CAP = 0.3;

/** ESA WorldCover class → aerodynamic roughness length z0 (m). Cropland depends on month. */
export function worldCoverZ0(cls: number, month = 7): number {
  switch (cls) {
    case 80: return 0.0002;
    case 70: return 0.001;
    case 60: return 0.005;
    case 100: return 0.01;
    case 30: return 0.03;
    case 90: return 0.05;
    case 40: return cropZ0(month);
    case 20: return 0.2;
    case 50: return 0.7;
    case 10:
    case 95: return 1.0;
    default: return Z0_REF;
  }
}

/** Cropland z0: 0.05 in winter (Jan) to 0.15 in summer (Jul), cosine interpolation by month (1–12). */
export function cropZ0(month: number): number {
  const phase = Math.cos(((month - 7) / 12) * 2 * Math.PI); // 1 in July, -1 in January
  return 0.1 + 0.05 * phase;
}

/**
 * Ratio U_rider / U10 for an upwind effective roughness z0Eff.
 * U60 = U10·ln(60/z0_ref)/ln(10/z0_ref); U_rider = U60·ln(z_r/z0)/ln(60/z0).
 */
export function fRough(z0Eff: number, zr = RIDER_HEIGHT_M): number {
  const z0 = Math.min(Math.max(z0Eff, 1e-5), Z0_CAP);
  const up = Math.log(BLEND_HEIGHT_M / Z0_REF) / Math.log(10 / Z0_REF);
  return (up * Math.log(zr / z0)) / Math.log(BLEND_HEIGHT_M / z0);
}

/** Inverse of fRough: the z0 that produces a given factor (bisection on log z0). */
export function z0FromFRough(f: number): number {
  let lo = Math.log(1e-5);
  let hi = Math.log(Z0_CAP);
  // fRough decreases monotonically with z0.
  for (let i = 0; i < 50; i++) {
    const mid = (lo + hi) / 2;
    if (fRough(Math.exp(mid)) > f) lo = mid;
    else hi = mid;
  }
  return Math.exp((lo + hi) / 2);
}

/** Weighted geometric mean of z0 values: exp(Σ w ln z0 / Σ w). */
export function effectiveZ0(z0s: ArrayLike<number>, weights: ArrayLike<number>): number {
  let num = 0;
  let den = 0;
  for (let i = 0; i < z0s.length; i++) {
    num += weights[i] * Math.log(z0s[i]);
    den += weights[i];
  }
  if (den === 0) return Z0_REF;
  return Math.min(Math.exp(num / den), Z0_CAP);
}

/** Turbulence intensity ≈ 1/ln(z_r/z0), clamped to [0.08, 0.35]. */
export function turbulenceIntensity(z0: number, zr = RIDER_HEIGHT_M): number {
  const ti = 1 / Math.log(zr / Math.max(z0, 1e-5));
  return Math.min(Math.max(ti, 0.08), 0.35);
}
