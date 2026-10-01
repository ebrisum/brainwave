import { RiderProfile, WeatherJson } from "@rideprep/physics";

/** Messages between the main thread and the physics worker. Same fields as the ride-core WebSocket state (apps/ride-core). */
export interface InitMsg {
  type: "init";
  route: { spacingM: number; count: number; s: Float32Array; x: Float32Array; y: Float32Array; z: Float32Array; gradePct: Float32Array; headingRad: Float32Array; radiusM: Float32Array; crrMultiplier: Float32Array };
  wind: { data: Uint8Array; count: number; spacingM: number; bins: number; layers: string[] };
  weather: WeatherJson;
  rider: RiderProfile;
  startEpoch: number;
  cornering: boolean;
  gusts: boolean;
  seed: number;
  startS?: number;
}

export type ToWorker =
  | InitMsg
  | { type: "power"; watts: number }
  | { type: "pause" }
  | { type: "resume" }
  | { type: "weather"; weather: WeatherJson };

export interface PhysicsState {
  type: "state";
  t: number;
  wall: number;
  s: number;
  v: number;
  powerW: number;
  braking: boolean;
  brakingTimeS: number;
  leanRad: number;
  gradePct: number;
  crrEff: number;
  rho: number;
  tempC: number;
  wet: boolean;
  finished: boolean;
  wind: { u10: number; dir10: number; uRider: number; dirRider: number; wHead: number; wCross: number; gust: number; shelter: number; fRough: number };
  weather: { rh: number; cloudCover: number; visibilityM: number; precipMmH: number; pMslHpa: number };
}
