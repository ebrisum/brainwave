import { describe, expect, it } from "vitest";
import { solarPosition } from "../src/ride/solar";
import { compass, feelsLike, fmtDuration, gradeColor } from "../src/units";

describe("solar position (NOAA)", () => {
  it("summer solstice noon at 52°N, 0°E ≈ 61.4° due south", () => {
    const p = solarPosition(new Date(Date.UTC(2026, 5, 21, 12, 2)), 52, 0);
    expect(p.elevationDeg).toBeCloseTo(61.4, 0);
    expect(Math.abs(p.azimuthDeg - 180)).toBeLessThan(2);
  });
  it("sun is below the horizon at midnight in winter", () => {
    expect(solarPosition(new Date(Date.UTC(2026, 11, 21, 0, 0)), 52, 5).elevationDeg).toBeLessThan(-30);
  });
  it("morning sun is in the east", () => {
    const p = solarPosition(new Date(Date.UTC(2026, 2, 20, 7, 0)), 50, 6);
    expect(p.azimuthDeg).toBeGreaterThan(80);
    expect(p.azimuthDeg).toBeLessThan(130);
  });
});

describe("units", () => {
  it("formats durations", () => {
    expect(fmtDuration(59)).toBe("0:59");
    expect(fmtDuration(3725)).toBe("1:02:05");
  });
  it("compass names", () => {
    expect(compass(247.5)).toBe("WSW");
    expect(compass(-10)).toBe("N");
  });
  it("grade palette is monotone in steepness", () => {
    const cs = [-6, -2, 0, 3, 5, 8, 12].map(gradeColor);
    expect(new Set(cs).size).toBe(7);
  });
  it("feels-like drops with wind", () => {
    expect(feelsLike(15, 0.7, 8)).toBeLessThan(feelsLike(15, 0.7, 0));
  });
});
