import { describe, expect, it } from "vitest";
import {
  airDensity, CALM_FLAT, constantEnvironment, DEFAULT_RIDER, makeCourse, RideSimulator, RiderProfile, steadyStateSpeed,
} from "../src";

// §16.1: rider 75 kg + bike 8 kg, CdA 0.32, Crr 0.0040, η 0.975, ρ 1.225, no wind.
const R: RiderProfile = { ...DEFAULT_RIDER, riderMassKg: 75, bikeMassKg: 8, cda: 0.32, crrBase: 0.004, drivetrainEfficiency: 0.975 };

function within(actual: number, expected: number, rel: number) {
  expect(Math.abs(actual - expected) / expected).toBeLessThanOrEqual(rel);
}

describe("16.1 steady-state speed", () => {
  it("flat, 200 W ≈ 9.43 m/s", () => within(steadyStateSpeed(R, CALM_FLAT, 200), 9.43, 0.005));
  it("8 % grade, 300 W ≈ 4.09 m/s", () => within(steadyStateSpeed(R, { ...CALM_FLAT, grade: 0.08 }, 300), 4.09, 0.005));
  it("flat, 200 W, 5 m/s headwind ≈ 6.59 m/s", () => within(steadyStateSpeed(R, { ...CALM_FLAT, wHead: 5 }, 200), 6.59, 0.005));

  it("the 50 Hz simulator converges to the steady state", () => {
    const course = makeCourse({ spacingM: 5, z: new Array(4001).fill(0) });
    const sim = new RideSimulator(course, R, constantEnvironment(), { startEpoch: 0 });
    for (let i = 0; i < 300 * 50; i++) {
      sim.setPower(200, sim.state.t);
      sim.step();
    }
    within(sim.state.v, 9.43, 0.005);
  });

  it("coasting on −6 % reaches a stable terminal velocity", () => {
    const n = 8001;
    const course = makeCourse({ spacingM: 5, z: Array.from({ length: n }, (_, i) => 3000 - i * 5 * 0.06) });
    const sim = new RideSimulator(course, R, constantEnvironment(), { startEpoch: 0 });
    const vs: number[] = [];
    for (let i = 0; i < 150 * 50; i++) {
      sim.step();
      if (i % 50 === 0) vs.push(sim.state.v);
    }
    const vt = steadyStateSpeed(R, { ...CALM_FLAT, grade: -0.06 }, 0);
    expect(vt).toBeGreaterThan(10);
    within(vs[vs.length - 1], vt, 0.01);
    // Monotonic approach, no overshoot
    for (let i = 1; i < vs.length; i++) expect(vs[i]).toBeGreaterThanOrEqual(vs[i - 1] - 1e-9);
  });

  it("200 → 400 W step response is monotonic with no oscillation", () => {
    const course = makeCourse({ spacingM: 5, z: new Array(20001).fill(0) });
    const sim = new RideSimulator(course, R, constantEnvironment(), { startEpoch: 0 });
    for (let i = 0; i < 200 * 50; i++) { sim.setPower(200); sim.step(); }
    const vs: number[] = [];
    for (let i = 0; i < 200 * 50; i++) { sim.setPower(400); sim.step(); vs.push(sim.state.v); }
    for (let i = 1; i < vs.length; i++) expect(vs[i]).toBeGreaterThanOrEqual(vs[i - 1] - 1e-9);
    expect(vs[vs.length - 1]).toBeLessThanOrEqual(steadyStateSpeed(R, CALM_FLAT, 400) + 1e-3);
  });

  it("holds power 3 s on dropout, then ramps to 0 over 2 s", () => {
    const course = makeCourse({ spacingM: 5, z: new Array(100).fill(0) });
    const sim = new RideSimulator(course, R, constantEnvironment(), { startEpoch: 0 });
    sim.setPower(250, 0);
    expect(sim.effectivePower(2.9)).toBe(250);
    expect(sim.effectivePower(4)).toBeCloseTo(125, 6);
    expect(sim.effectivePower(5.1)).toBe(0);
  });
});

describe("16.2 air density", () => {
  it("20 °C, 1013.25 hPa, RH 0 → 1.204", () => {
    expect(Math.abs(airDensity({ tempC: 20, rh: 0, pMslHpa: 1013.25, elevationM: 0 }) - 1.204)).toBeLessThanOrEqual(0.002);
  });
  it("humid air is less dense", () => {
    const dry = airDensity({ tempC: 25, rh: 0, pMslHpa: 1013.25, elevationM: 0 });
    const wet = airDensity({ tempC: 25, rh: 0.9, pMslHpa: 1013.25, elevationM: 0 });
    expect(wet).toBeLessThan(dry);
  });
  it("altitude lowers density", () => {
    expect(airDensity({ tempC: 15, rh: 0.5, pMslHpa: 1013.25, elevationM: 2000 })).toBeLessThan(
      airDensity({ tempC: 15, rh: 0.5, pMslHpa: 1013.25, elevationM: 0 }),
    );
  });
});
