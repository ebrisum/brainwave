import { CDA_PRESETS, DEFAULT_RIDER, Position, RiderProfile } from "@rideprep/physics";
import { create } from "zustand";
import { Units } from "./units";

export type Screen = "home" | "library" | "upload" | "briefing" | "pairing" | "ride" | "postride" | "settings";
export type Quality = "low" | "medium" | "high" | "ultra";
export type CameraMode = "chase" | "cockpit" | "side" | "drone" | "flyover";
export type PhotorealSource = "off" | "google" | "dev" | "url";

export interface Settings {
  units: Units;
  rider: RiderProfile & { position: Position; maxHr: number; jersey: string; bike: "road" | "tt" };
  quality: Quality;
  trainerDifficulty: number;
  corneringRealism: boolean;
  gusts: boolean;
  /** Real-world view from 3D tiles. "dev" uses the package's local stand-in tileset (no key). */
  photoreal: PhotorealSource;
  googleApiKey: string;
  tilesUrl: string;
  mapillaryToken: string;
  /** Use the course's game-art layer (Blender art kit) when the package has one. */
  gameArt: boolean;
}

/** Live values the HUD shows; written by the ride session ~10×/s, never by React render. */
export interface HudState {
  t: number; s: number; speedMs: number; powerW: number; npW: number; ifactor: number; hr?: number; cadence?: number; ascentM: number;
  lap: number; laps: number; wkg: number; targetLow?: number; targetHigh?: number; braking: boolean;
  wind: { u10: number; dir10: number; uRider: number; wHead: number; wCross: number; shelter: number; gust: number };
  tempC: number; feelsC: number; rho: number; gradePct: number; devices: Record<string, string>; paused: boolean; finished: boolean;
  warnings: string[]; trainerMode?: string;
  /** 3 s average power (what the big number shows). */
  power3sW: number;
  ftpW: number; maxHr: number;
  /** Last command sent to the smart trainer. */
  trainer?: { mode: string; gradePct?: number; windMs?: number; crr?: number; cwKgM?: number; ergW?: number; difficulty: number };
  /** Which sources feed power and cadence. */
  powerSource?: string; cadenceSource?: string;
}

const STORAGE_KEY = "rideprep.settings.v1";
const defaults: Settings = {
  units: "metric",
  rider: { ...DEFAULT_RIDER, position: "drops", maxHr: 190, jersey: "#f0b429", bike: "road" },
  quality: "high",
  trainerDifficulty: 1,
  corneringRealism: true,
  gusts: true,
  photoreal: "off",
  googleApiKey: "",
  tilesUrl: "",
  mapillaryToken: "",
  gameArt: true,
};

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const s = JSON.parse(raw);
      return { ...defaults, ...s, rider: { ...defaults.rider, ...s.rider } };
    }
  } catch {
    /* private mode or corrupt: defaults */
  }
  return defaults;
}

export interface AppState {
  screen: Screen;
  courseId?: string;
  buildId?: string;
  settings: Settings;
  hud?: HudState;
  camera: CameraMode;
  lastRideId?: string;
  scenario: string;
  plan?: { segmentM: number; watts: number[] };
  go(screen: Screen, patch?: Partial<AppState>): void;
  updateSettings(p: Partial<Settings>): void;
  updateRider(p: Partial<Settings["rider"]>): void;
  setHud(h: HudState): void;
  setCamera(c: CameraMode): void;
}

export const useApp = create<AppState>((set, get) => ({
  screen: "home",
  settings: loadSettings(),
  camera: "chase",
  scenario: "weather",
  go: (screen, patch) => set({ screen, ...patch }),
  updateSettings: (p) => {
    const settings = { ...get().settings, ...p };
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(settings)); } catch { /* ignore */ }
    set({ settings });
  },
  updateRider: (p) => {
    const rider = { ...get().settings.rider, ...p };
    if (p.position) rider.cda = CDA_PRESETS[p.position];
    get().updateSettings({ rider });
  },
  setHud: (hud) => set({ hud }),
  setCamera: (camera) => set({ camera }),
}));
