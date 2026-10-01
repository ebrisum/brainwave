import { DEG } from "../constants";
import { OrnsteinUhlenbeck, Rng } from "../random";
import { WindFactors, WindLayers } from "./layers";
import { turbulenceIntensity, z0FromFRough } from "./profile";
import { WeatherField, WeatherState } from "./weather";

export interface WindAtRider {
  /** Weather-model 10 m wind, m/s, and FROM-direction, degrees. */
  u10: number;
  dir10: number;
  /** Wind speed at rider height after all corrections and gusts, m/s. */
  uRider: number;
  dirRider: number;
  /** Positive = headwind. */
  wHead: number;
  /** Positive = wind from the rider's right. */
  wCross: number;
  gust: number;
  factors: WindFactors;
  weather: WeatherState;
}

/**
 * Head/cross components for a FROM-direction (deg) and a compass heading (rad).
 * Wind from straight ahead (dir = heading) is a pure headwind.
 */
export function windComponents(u: number, dirFromDeg: number, headingRad: number): { wHead: number; wCross: number } {
  const rel = dirFromDeg * DEG - headingRad;
  return { wHead: u * Math.cos(rel), wCross: u * Math.sin(rel) };
}

export interface WindModelOptions {
  seed?: number;
  gusts?: boolean;
  gustTauS?: number;
  dirSigmaDeg?: number;
  dirTauS?: number;
}

/** Runtime wind at the rider (WIND_MODEL.md §5): lookup + interpolation + OU gusts. */
export class WindModel {
  private gustOu: OrnsteinUhlenbeck;
  private dirOu: OrnsteinUhlenbeck;
  private gustsOn: boolean;
  private f: WindFactors = { fRough: 1, shelter: 1, topo: 1, channel: 1 };

  constructor(public layers: WindLayers, public weather: WeatherField, opts: WindModelOptions = {}) {
    const rng = new Rng(opts.seed ?? 1);
    this.gustOu = new OrnsteinUhlenbeck(0, 0.15, opts.gustTauS ?? 6, rng);
    this.dirOu = new OrnsteinUhlenbeck(0, opts.dirSigmaDeg ?? 8, opts.dirTauS ?? 10, rng);
    this.gustsOn = opts.gusts ?? true;
  }

  /** Mean (gust-free) wind; used by the predictor. */
  mean(s: number, tEpoch: number, headingRad: number): WindAtRider {
    return this.compute(s, tEpoch, headingRad, 1, 0);
  }

  /** Advance the gust processes by dt and return wind at the rider. */
  step(s: number, tEpoch: number, headingRad: number, dt: number): WindAtRider {
    if (!this.gustsOn) return this.mean(s, tEpoch, headingRad);
    const w = this.weather.at(s, tEpoch);
    const f = this.layers.factors(s, w.dirDeg, this.f);
    const z0 = z0FromFRough(f.fRough);
    this.gustOu.sigma = turbulenceIntensity(z0);
    const x = this.gustOu.step(dt);
    const delta = this.dirOu.step(dt);
    let gust = Math.max(0, 1 + x);
    if (w.u10 > 0.1 && w.gust10 > 0) gust = Math.min(gust, w.gust10 / w.u10);
    return this.compute(s, tEpoch, headingRad, gust, delta, w);
  }

  private compute(s: number, tEpoch: number, headingRad: number, gust: number, deltaDeg: number, w?: WeatherState): WindAtRider {
    const weather = w ?? this.weather.at(s, tEpoch);
    const f = { ...this.layers.factors(s, weather.dirDeg) };
    const uRider = weather.u10 * f.fRough * f.shelter * f.topo * f.channel * gust;
    const dirRider = weather.dirDeg + deltaDeg;
    const { wHead, wCross } = windComponents(uRider, dirRider, headingRad);
    return { u10: weather.u10, dir10: weather.dirDeg, uRider, dirRider, wHead, wCross, gust, factors: f, weather };
  }
}
