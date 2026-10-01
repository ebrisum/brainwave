/// <reference lib="webworker" />
import {
  basicScenarios, ClimatologyJson, CourseProfile, optimizePacing, predict, routeExposure, RiderProfile, splitsEvery, splitTime, WeatherField,
  WeatherJson, WindLayers, WindLayerName, WindModel, windEnvironment, worstCaseScenario, Scenario,
} from "@rideprep/physics";

export interface AnalysisRequest {
  route: CourseProfile;
  wind: { data: Uint8Array; count: number; spacingM: number; bins: number; layers: string[] };
  weather: WeatherJson;
  climatology: ClimatologyJson;
  rider: RiderProfile;
  startEpoch: number;
  powerW: number;
  climbs: { sStart: number; sEnd: number }[];
  laps: { sStart: number; sEnd: number }[];
  optimizeFor: string;
  ifTarget: number;
}

export interface ScenarioResult {
  name: string; label: string; u10: number; dirDeg: number; totalTimeS: number; avgSpeed: number; kJ: number; brakingTimeS: number;
  climbTimes: number[]; lapTimes: number[]; splits5k: number[];
  exposure: { s0: number; s1: number; headShare: number; crossShare: number; tailShare: number; shelteredShare: number; avgURider: number }[];
}

export interface AnalysisResult {
  scenarios: ScenarioResult[];
  plan: { segmentM: number; watts: number[]; totalTimeS: number; baselineS: number; npW: number; scenario: string };
  elapsedMs: number;
}

const ctx = self as unknown as DedicatedWorkerGlobalScope;

ctx.onmessage = (e: MessageEvent<AnalysisRequest>) => {
  const t0 = performance.now();
  const q = e.data;
  const layers = new WindLayers(q.wind.data, q.wind.count, q.wind.spacingM, q.wind.bins, q.wind.layers as WindLayerName[]);
  const scen: Scenario[] = [
    { name: "calm", label: "Weather file", weather: {} } as unknown as Scenario,
    ...basicScenarios(q.climatology),
    worstCaseScenario(q.climatology, q.route, q.rider, layers, q.powerW, q.startEpoch),
  ];
  const results: ScenarioResult[] = [];
  const fields: Record<string, WeatherField> = {};
  scen.forEach((sc, k) => {
    const name = k === 0 ? "weather" : sc.name;
    const field = k === 0 ? new WeatherField(q.weather) : WeatherField.constant(sc.weather, "scenario");
    fields[name] = field;
    const env = windEnvironment(new WindModel(layers, field, { gusts: false }));
    const p = predict(q.route, q.rider, q.powerW, env, { startEpoch: q.startEpoch });
    const w0 = field.at(0, q.startEpoch);
    results.push({
      name, label: k === 0 ? `${q.weather.mode[0].toUpperCase()}${q.weather.mode.slice(1)}` : sc.label, u10: w0.u10, dirDeg: w0.dirDeg,
      totalTimeS: p.totalTimeS, avgSpeed: p.avgSpeed, kJ: p.kJ, brakingTimeS: p.brakingTimeS,
      climbTimes: q.climbs.map((c) => splitTime(p, q.route, c.sStart, c.sEnd)),
      lapTimes: q.laps.map((l) => splitTime(p, q.route, l.sStart, l.sEnd)),
      splits5k: splitsEvery(p, q.route, 5000).map((x) => x.timeS),
      exposure: routeExposure(q.route, layers, w0, 500),
    });
  });
  const field = fields[q.optimizeFor] ?? fields.weather;
  const env = windEnvironment(new WindModel(layers, field, { gusts: false }));
  const plan = optimizePacing(q.route, q.rider, env, { startEpoch: q.startEpoch, targetNpW: q.ifTarget * q.rider.ftpW, minWPrimeFrac: 0.2 });
  const res: AnalysisResult = {
    scenarios: results,
    plan: { segmentM: plan.segmentM, watts: plan.watts, totalTimeS: plan.prediction.totalTimeS, baselineS: plan.baseline.totalTimeS, npW: plan.npW,
            scenario: q.optimizeFor },
    elapsedMs: performance.now() - t0,
  };
  ctx.postMessage(res);
};
