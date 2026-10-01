import { R_DRY, R_VAPOUR } from "./constants";

/** Station pressure (hPa) from mean-sea-level pressure (hPa), elevation (m) and temperature (K). */
export function stationPressure(pMslHpa: number, elevationM: number, tempK: number): number {
  const h = elevationM;
  return pMslHpa * Math.pow(1 - (0.0065 * h) / (tempK + 0.0065 * h), 5.257);
}

/** Saturation vapour pressure (hPa), Tetens formula, T in °C. */
export function saturationVapourPressure(tempC: number): number {
  return 6.1078 * Math.pow(10, (7.5 * tempC) / (tempC + 237.3));
}

export interface AirState {
  tempC: number;
  /** Relative humidity, 0..1. */
  rh: number;
  /** Mean-sea-level pressure, hPa. */
  pMslHpa: number;
  /** Elevation of the rider, m. */
  elevationM: number;
}

/** Moist air density (kg/m³), PHYSICS.md §air density. */
export function airDensity({ tempC, rh, pMslHpa, elevationM }: AirState): number {
  const T = tempC + 273.15;
  const pStation = stationPressure(pMslHpa, elevationM, T) * 100;
  const pv = Math.min(Math.max(rh, 0), 1) * saturationVapourPressure(tempC) * 100;
  const pd = pStation - pv;
  return pd / (R_DRY * T) + pv / (R_VAPOUR * T);
}
