/** One 1 Hz ride record (spec §12). */
export interface RideRecord {
  /** Epoch milliseconds. */
  t: number;
  s: number;
  lat: number;
  lon: number;
  ele: number;
  powerW: number;
  hrBpm?: number;
  rrS?: number[];
  cadenceRpm?: number;
  speedMs: number;
  trainerSpeedMs?: number;
  gradePct: number;
  windSpeed10: number;
  windDirDeg: number;
  uRider: number;
  wHead: number;
  wCross: number;
  shelter: number;
  tempC: number;
  rho: number;
  crrEff: number;
  targetPowerW?: number;
  braking: boolean;
}

export interface RideSummary {
  startTime: number;
  durationS: number;
  distanceM: number;
  avgPowerW: number;
  npW: number;
  ifactor: number;
  tss: number;
  vi: number;
  kJ: number;
  avgHr?: number;
  maxHr?: number;
  avgCadence?: number;
  avgSpeedMs: number;
  ascentM: number;
  minWPrimeBalJ: number;
  brakingTimeS: number;
  decouplingPct?: number;
}
