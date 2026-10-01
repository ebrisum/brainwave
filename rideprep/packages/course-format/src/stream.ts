/**
 * Ride-core → renderer state stream (spec §10.6): WebSocket ws://127.0.0.1:8765, MessagePack-encoded maps, 50 Hz.
 * Unreal (RidePrepRuntime) and the web client (when driven by a local ride core) consume the same schema.
 */
export const STREAM_VERSION = 1;

export interface StreamState {
  type: "state";
  v: typeof STREAM_VERSION;
  /** Sequence number and send time (ms since epoch) for latency checks. */
  seq: number;
  sentAt: number;
  /** Simulated seconds since start. */
  t: number;
  /** Route distance (m). Renderers place the rider with poseAt(s). */
  s: number;
  /** ENU position (m) and compass heading (rad) — convenience; derived from s. */
  pos: [number, number, number];
  heading: number;
  speed: number;
  power: number;
  hr?: number;
  cadence?: number;
  /** Crank angle (rad), integrated from cadence. */
  crank: number;
  /** Lean (rad), positive = leaning right. */
  lean: number;
  braking: boolean;
  gradePct: number;
  wind: { u10: number; dir10: number; uRider: number; dirRider: number; wHead: number; wCross: number; gust: number; shelter: number };
  weather: { tempC: number; rh: number; pMslHpa: number; precipMmH: number; cloudCover: number; visibilityM: number; rho: number };
  sun: { elevationDeg: number; azimuthDeg: number };
  hud: { npW: number; ifactor: number; wkg: number; lap: number; laps: number; ascentM: number; targetW?: number; elapsedS: number; distanceM: number };
  paused: boolean;
  finished: boolean;
}

export type StreamCommand =
  | { type: "pause" }
  | { type: "resume" }
  | { type: "camera"; mode: "chase" | "cockpit" | "first" | "side" | "drone" | "flyover" }
  | { type: "difficulty"; value: number }
  | { type: "end" };

/** Sent once on connect. */
export interface StreamHello { type: "hello"; v: typeof STREAM_VERSION; courseId: string; packageUrl: string; startEpoch: number }
