/** Weather field sampled along the route (every ~5 km) and in time (hourly). */

export interface WeatherState {
  u10: number;
  /** Meteorological direction the wind blows FROM, degrees. */
  dirDeg: number;
  gust10: number;
  tempC: number;
  rh: number;
  pMslHpa: number;
  precipMmH: number;
  cloudCover: number;
  visibilityM: number;
}

export type WeatherVar = keyof WeatherState;

/** JSON shape of weather.json (see course-format schema). */
export interface WeatherJson {
  mode: "forecast" | "historical" | "climatology" | "manual" | "scenario";
  source: string;
  /** Route distances of the sample points, m. */
  s: number[];
  /** Epoch seconds of the hourly samples. */
  t: number[];
  /** values[var][sIndex][tIndex] */
  values: Partial<Record<WeatherVar, number[][]>>;
}

const DEFAULTS: WeatherState = {
  u10: 0, dirDeg: 270, gust10: 0, tempC: 15, rh: 0.7, pMslHpa: 1013.25, precipMmH: 0, cloudCover: 0.5, visibilityM: 20000,
};

function bracket(arr: number[], v: number): [number, number, number] {
  if (arr.length <= 1 || v <= arr[0]) return [0, 0, 0];
  const last = arr.length - 1;
  if (v >= arr[last]) return [last, last, 0];
  let lo = 0;
  let hi = last;
  while (hi - lo > 1) {
    const m = (lo + hi) >> 1;
    if (arr[m] <= v) lo = m;
    else hi = m;
  }
  return [lo, hi, (v - arr[lo]) / (arr[hi] - arr[lo])];
}

export class WeatherField {
  constructor(public readonly json: WeatherJson) {}

  /** A uniform field (e.g. a manual scenario or a test). */
  static constant(state: Partial<WeatherState>, mode: WeatherJson["mode"] = "manual"): WeatherField {
    const full = { ...DEFAULTS, ...state };
    const values: WeatherJson["values"] = {};
    for (const k of Object.keys(full) as WeatherVar[]) values[k] = [[full[k]]];
    return new WeatherField({ mode, source: "manual", s: [0], t: [0], values });
  }

  /** Bilinear interpolation in (s, t). Wind direction is interpolated as a vector. */
  at(s: number, tEpoch: number): WeatherState {
    const [si0, si1, sf] = bracket(this.json.s, s);
    const [ti0, ti1, tf] = bracket(this.json.t, tEpoch);
    const get = (k: WeatherVar): number | undefined => {
      const v = this.json.values[k];
      if (!v) return undefined;
      const a = v[si0][ti0] + (v[si0][ti1] - v[si0][ti0]) * tf;
      const b = v[si1][ti0] + (v[si1][ti1] - v[si1][ti0]) * tf;
      return a + (b - a) * sf;
    };
    const out = { ...DEFAULTS };
    for (const k of Object.keys(DEFAULTS) as WeatherVar[]) {
      if (k === "dirDeg" || k === "u10") continue;
      const v = get(k);
      if (v !== undefined) out[k] = v;
    }
    // Vector interpolation for wind.
    const u = this.json.values.u10;
    const d = this.json.values.dirDeg;
    if (u && d) {
      let ex = 0;
      let ny = 0;
      const corners: [number, number, number][] = [
        [si0, ti0, (1 - sf) * (1 - tf)], [si0, ti1, (1 - sf) * tf], [si1, ti0, sf * (1 - tf)], [si1, ti1, sf * tf],
      ];
      let speed = 0;
      for (const [i, j, w] of corners) {
        const rad = (d[i][j] * Math.PI) / 180;
        ex += w * Math.sin(rad);
        ny += w * Math.cos(rad);
        speed += w * u[i][j];
      }
      out.u10 = speed;
      out.dirDeg = ((Math.atan2(ex, ny) * 180) / Math.PI + 360) % 360;
    }
    if (out.gust10 < out.u10) out.gust10 = out.u10 * 1.5;
    return out;
  }
}
