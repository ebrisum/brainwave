import { CourseProfile } from "./course";
import { windEnvironment } from "./environment";
import { predict, PowerPlan } from "./predictor";
import { RiderProfile } from "./rider";
import { WindLayers } from "./wind/layers";
import { WindModel } from "./wind/runtime";
import { WeatherField, WeatherState } from "./wind/weather";

/** climatology.json (produced by the `weather` stage). */
export interface ClimatologyJson {
  source: string;
  years: [number, number];
  window: { monthDayCentre: string; dayRange: number; hourRange: number; localHour: number };
  windRose: { dirBins: number; speedBinsMs: number[]; freq: number[][] };
  windSpeedPercentiles: { p50: number; p75: number; p90: number };
  gustRatio: number;
  modalDirDeg: number;
  prevailingDirDeg: number;
  tempC: { p10: number; p50: number; p90: number };
  rhMedian: number;
  pMslMedianHpa: number;
  rainProbability: number;
}

export type ScenarioName = "calm" | "mostLikely" | "windy" | "worstCase";

export interface Scenario {
  name: ScenarioName;
  label: string;
  weather: Partial<WeatherState>;
}

/** Calm / Most likely / Windy presets straight from climatology (worst case needs the predictor). */
export function basicScenarios(c: ClimatologyJson): Scenario[] {
  const base = { tempC: c.tempC.p50, rh: c.rhMedian, pMslHpa: c.pMslMedianHpa, precipMmH: 0 };
  return [
    { name: "calm", label: "Calm", weather: { ...base, u10: 1, dirDeg: c.modalDirDeg, gust10: 1.5 } },
    {
      name: "mostLikely", label: "Most likely",
      weather: { ...base, u10: c.windSpeedPercentiles.p50, dirDeg: c.modalDirDeg, gust10: c.windSpeedPercentiles.p50 * c.gustRatio },
    },
    {
      name: "windy", label: "Windy",
      weather: { ...base, u10: c.windSpeedPercentiles.p90, dirDeg: c.modalDirDeg, gust10: c.windSpeedPercentiles.p90 * c.gustRatio },
    },
  ];
}

/** The direction (of 16 bins) that maximises predicted time at P75 wind speed. */
export function worstCaseScenario(
  c: ClimatologyJson, course: CourseProfile, rider: RiderProfile, layers: WindLayers, plan: PowerPlan, startEpoch: number,
): Scenario & { timesByDir: number[] } {
  const u = c.windSpeedPercentiles.p75;
  const base = { tempC: c.tempC.p50, rh: c.rhMedian, pMslHpa: c.pMslMedianHpa, precipMmH: 0, u10: u, gust10: u * c.gustRatio };
  const timesByDir: number[] = [];
  let best = 0;
  for (let d = 0; d < 16; d++) {
    const field = WeatherField.constant({ ...base, dirDeg: d * 22.5 }, "scenario");
    const env = windEnvironment(new WindModel(layers, field, { gusts: false }));
    const t = predict(course, rider, plan, env, { startEpoch }).totalTimeS;
    timesByDir.push(t);
    if (t > timesByDir[best]) best = d;
  }
  return { name: "worstCase", label: "Worst case", weather: { ...base, dirDeg: best * 22.5 }, timesByDir };
}

export function allScenarios(
  c: ClimatologyJson, course: CourseProfile, rider: RiderProfile, layers: WindLayers, plan: PowerPlan, startEpoch: number,
): Scenario[] {
  const wc = worstCaseScenario(c, course, rider, layers, plan, startEpoch);
  return [...basicScenarios(c), { name: wc.name, label: wc.label, weather: wc.weather }];
}

export interface ExposureSegment {
  s0: number;
  s1: number;
  headShare: number;
  crossShare: number;
  tailShare: number;
  shelteredShare: number;
  avgURider: number;
}

/** Per-segment head/cross/tail/sheltered shares for a (constant) weather state. */
export function routeExposure(course: CourseProfile, layers: WindLayers, w: Partial<WeatherState>, segmentM = 500): ExposureSegment[] {
  const model = new WindModel(layers, WeatherField.constant(w), { gusts: false });
  const out: ExposureSegment[] = [];
  const L = course.s[course.count - 1];
  for (let s0 = 0; s0 < L; s0 += segmentM) {
    const s1 = Math.min(L, s0 + segmentM);
    let head = 0, cross = 0, tail = 0, shel = 0, sum = 0, n = 0;
    for (let i = Math.floor(s0 / course.spacingM); i < Math.min(course.count, Math.ceil(s1 / course.spacingM)); i++) {
      const ww = model.mean(course.s[i], 0, course.headingRad[i]);
      n++;
      sum += ww.uRider;
      if (ww.factors.shelter < 0.6) shel++;
      else if (Math.abs(ww.wCross) > Math.abs(ww.wHead)) cross++;
      else if (ww.wHead > 0) head++;
      else tail++;
    }
    const k = n || 1;
    out.push({ s0, s1, headShare: head / k, crossShare: cross / k, tailShare: tail / k, shelteredShare: shel / k, avgURider: sum / k });
  }
  return out;
}
