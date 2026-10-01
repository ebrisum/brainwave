import { describe, expect, it } from "vitest";
import {
  basicScenarios, ClimatologyJson, constantEnvironment, DEFAULT_RIDER, makeCourse, optimizePacing, predict,
  steadyStateSpeed, CALM_FLAT, WindLayers, worstCaseScenario, splitsEvery,
} from "../src";

/** A synthetic 180 km course: rolling hills with some climbs and a few hairpins. */
function longCourse(km = 180) {
  const n = Math.round((km * 1000) / 5) + 1;
  const z: number[] = [];
  const heading: number[] = [];
  const radius: number[] = [];
  for (let i = 0; i < n; i++) {
    const s = i * 5;
    z.push(100 + 60 * Math.sin(s / 4000) + 25 * Math.sin(s / 900));
    heading.push((s / 20000) % (2 * Math.PI));
    radius.push(i % 4000 < 6 ? 15 : Infinity);
  }
  return makeCourse({ spacingM: 5, z, headingRad: heading, radiusM: radius });
}

describe("predictor", () => {
  it("flat course time matches the steady state", () => {
    const course = makeCourse({ spacingM: 5, z: new Array(2001).fill(0) });
    const p = predict(course, DEFAULT_RIDER, 200, constantEnvironment(), { startEpoch: 0, startSpeed: steadyStateSpeed(DEFAULT_RIDER, CALM_FLAT, 200) });
    const expected = 10000 / steadyStateSpeed(DEFAULT_RIDER, CALM_FLAT, 200);
    expect(Math.abs(p.totalTimeS - expected) / expected).toBeLessThan(0.01);
    expect(splitsEvery(p, course, 5000)).toHaveLength(2);
  });

  it("brakes for hairpins and loses time doing so", () => {
    const n = 2001;
    const radius = new Array(n).fill(Infinity);
    for (let i = 1000; i < 1004; i++) radius[i] = 10;
    const z = Array.from({ length: n }, (_, i) => 500 - i * 5 * 0.05);
    const straight = makeCourse({ spacingM: 5, z });
    const hairpin = makeCourse({ spacingM: 5, z, radiusM: radius });
    const a = predict(straight, DEFAULT_RIDER, 150, constantEnvironment(), { startEpoch: 0 });
    const b = predict(hairpin, DEFAULT_RIDER, 150, constantEnvironment(), { startEpoch: 0 });
    expect(b.brakingTimeS).toBeGreaterThan(0);
    expect(b.totalTimeS).toBeGreaterThan(a.totalTimeS);
  });

  it("predicts 180 km in under 1 s", () => {
    const course = longCourse();
    const t0 = performance.now();
    const p = predict(course, DEFAULT_RIDER, 220, constantEnvironment(), { startEpoch: 0 });
    expect(performance.now() - t0).toBeLessThan(1000);
    expect(p.totalTimeS).toBeGreaterThan(3600 * 4);
  });
});

describe("optimizer", () => {
  it("puts more power on climbs, respects bounds and NP, beats constant power, within 10 s on 180 km", () => {
    const course = longCourse();
    const env = constantEnvironment();
    const t0 = performance.now();
    const plan = optimizePacing(course, DEFAULT_RIDER, env, { startEpoch: 0, targetNpW: 220, minWPrimeFrac: 0.2 });
    expect(performance.now() - t0).toBeLessThan(10000);
    expect(plan.timeSavedS).toBeGreaterThan(0);
    expect(plan.npW).toBeLessThanOrEqual(220 * 1.01);
    for (const w of plan.watts) {
      expect(w).toBeGreaterThanOrEqual(220 * 0.8 - 1e-6);
      expect(w).toBeLessThanOrEqual(220 * 1.15 + 1e-6);
    }
    // Correlation between segment grade and power is positive.
    const grades = plan.watts.map((_, i) => course.z[Math.min((i + 1) * 100, course.count - 1)] - course.z[i * 100]);
    const mean = (a: number[]) => a.reduce((x, y) => x + y, 0) / a.length;
    const mg = mean(grades);
    const mw = mean(plan.watts);
    const cov = grades.reduce((acc, g, i) => acc + (g - mg) * (plan.watts[i] - mw), 0);
    expect(cov).toBeGreaterThan(0);
  });
});

describe("scenarios", () => {
  const clim: ClimatologyJson = {
    source: "test", years: [2010, 2024], window: { monthDayCentre: "09-19", dayRange: 15, hourRange: 2, localHour: 8 },
    windRose: { dirBins: 16, speedBinsMs: [0, 2, 4, 6, 8, 10], freq: [] },
    windSpeedPercentiles: { p50: 4, p75: 6, p90: 8 }, gustRatio: 1.6, modalDirDeg: 247.5, prevailingDirDeg: 247.5,
    tempC: { p10: 10, p50: 15, p90: 20 }, rhMedian: 0.75, pMslMedianHpa: 1015, rainProbability: 0.2,
  };
  it("builds calm / most likely / windy", () => {
    const s = basicScenarios(clim);
    expect(s.map((x) => x.name)).toEqual(["calm", "mostLikely", "windy"]);
    expect(s[2].weather.u10).toBe(8);
  });
  it("worst case is a headwind for an out-and-back-free straight course heading north", () => {
    const course = makeCourse({ spacingM: 5, z: new Array(2001).fill(0) });
    const wc = worstCaseScenario(clim, course, DEFAULT_RIDER, WindLayers.uniform(1001), 200, 0);
    expect(wc.weather.dirDeg).toBe(0);
  });
});
