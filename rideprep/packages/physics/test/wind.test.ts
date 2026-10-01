import { describe, expect, it } from "vitest";
import {
  cropZ0, effectiveZ0, fRough, isLeafOn, porosityFor, shelterFactor, shelterFactorForHit, turbulenceIntensity,
  WeatherField, WindLayers, WindModel, windComponents, z0FromFRough,
} from "../src";

describe("16.3 wind profile", () => {
  const u = (z0: number) => 10 * fRough(z0);
  it("z0 0.03 → 6.35 m/s", () => expect(Math.abs(u(0.03) - 6.35) / 6.35).toBeLessThan(0.01));
  it("z0 0.0002 → 9.0 m/s", () => expect(Math.abs(u(0.0002) - 9.0) / 9.0).toBeLessThan(0.01));
  it("z0 0.30 → 3.4 m/s", () => expect(Math.abs(u(0.3) - 3.4) / 3.4).toBeLessThan(0.01));
  it("z0 above the cap is clamped", () => expect(u(1.0)).toBeCloseTo(u(0.3), 9));
  it("inverse round-trips", () => expect(z0FromFRough(fRough(0.07))).toBeCloseTo(0.07, 4));
  it("effective z0 is a weighted geometric mean", () => {
    expect(effectiveZ0([0.01, 1], [1, 1])).toBeCloseTo(0.1, 9);
    expect(effectiveZ0([0.03], [1])).toBeCloseTo(0.03, 9);
  });
  it("cropland z0 is seasonal", () => {
    expect(cropZ0(7)).toBeCloseTo(0.15, 9);
    expect(cropZ0(1)).toBeCloseTo(0.05, 9);
  });
  it("turbulence intensity is clamped", () => {
    expect(turbulenceIntensity(0.0002)).toBeCloseTo(1 / Math.log(6000), 9);
    expect(turbulenceIntensity(1)).toBe(0.35);
  });
});

describe("shelter", () => {
  it("no shelter far behind", () => expect(shelterFactorForHit({ distanceM: 1000, heightM: 10, porosity: 0.3 })).toBe(1));
  it("solid wall gives u_min close behind", () => {
    const r = shelterFactorForHit({ distanceM: 30, heightM: 10, porosity: 0 });
    expect(r).toBeCloseTo(1 - 0.85 * 1.0, 6);
  });
  it("strongest shelter wins", () => {
    expect(shelterFactor([{ distanceM: 30, heightM: 10, porosity: 0.6 }, { distanceM: 30, heightM: 10, porosity: 0 }])).toBeCloseTo(0.15, 6);
  });
  it("leaf season around 52°N", () => {
    expect(isLeafOn(7, 1, 52)).toBe(true);
    expect(isLeafOn(1, 15, 52)).toBe(false);
    expect(isLeafOn(7, 1, -35)).toBe(false);
  });
});

describe("wind components", () => {
  it("wind from straight ahead is a headwind", () => {
    const c = windComponents(5, 0, 0);
    expect(c.wHead).toBeCloseTo(5, 9);
    expect(c.wCross).toBeCloseTo(0, 9);
  });
  it("wind from behind is a tailwind", () => expect(windComponents(5, 180, 0).wHead).toBeCloseTo(-5, 9));
  it("wind from the west while heading north is a pure crosswind from the left", () => {
    const c = windComponents(5, 270, 0);
    expect(c.wHead).toBeCloseTo(0, 9);
    expect(c.wCross).toBeCloseTo(-5, 9);
  });
});

describe("16.5 wind shelter sanity", () => {
  // U10 = 8 m/s from 270°, rider heading north. Each case is a single-sample layer set.
  const weather = WeatherField.constant({ u10: 8, dirDeg: 270, gust10: 12 });
  const leafOn = isLeafOn(7, 1, 52);
  const leafOff = isLeafOn(1, 15, 52);
  const uAt = (fR: number, shelter: number) => {
    const model = new WindModel(WindLayers.uniform(2, { fRough: fR, shelter }), weather, { gusts: false });
    return model.mean(0, 0, 0).uRider;
  };
  const row = (phi: number) => shelterFactorForHit({ distanceM: 30, heightM: 15, porosity: phi });
  const cases = {
    dike: uAt(fRough(0.0002), 1),
    polder: uAt(fRough(0.03), 1),
    treeRowSummer: uAt(fRough(0.05), row(porosityFor("deciduous", leafOn))),
    treeRowJanuary: uAt(fRough(0.05), row(porosityFor("deciduous", leafOff))),
    street: uAt(fRough(0.3), shelterFactorForHit({ distanceM: 12, heightM: 9, porosity: porosityFor("building", true) })),
  };
  it("dike ≈ 7 m/s", () => expect(cases.dike).toBeGreaterThan(6.5));
  it("polder ≈ 5 m/s", () => expect(Math.abs(cases.polder - 5)).toBeLessThan(0.3));
  it("ordering dike > polder > January row > summer row > street", () => {
    expect(cases.dike).toBeGreaterThan(cases.polder);
    expect(cases.polder).toBeGreaterThan(cases.treeRowJanuary);
    expect(cases.treeRowJanuary).toBeGreaterThan(cases.treeRowSummer);
    expect(cases.treeRowSummer).toBeGreaterThan(cases.street);
  });
});

describe("gusts", () => {
  it("are reproducible from a seed and capped by the gust value", () => {
    const layers = WindLayers.uniform(10);
    const weather = WeatherField.constant({ u10: 6, dirDeg: 0, gust10: 8 });
    const run = (seed: number) => {
      const m = new WindModel(layers, weather, { seed });
      const out: number[] = [];
      for (let i = 0; i < 2000; i++) out.push(m.step(0, 0, 0, 0.02).gust);
      return out;
    };
    const a = run(42);
    expect(run(42)).toEqual(a);
    expect(run(43)).not.toEqual(a);
    expect(Math.max(...a)).toBeLessThanOrEqual(8 / 6 + 1e-9);
  });
});
