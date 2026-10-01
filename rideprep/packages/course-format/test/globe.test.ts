import { describe, expect, it } from "vitest";
import { applyAnchor, geodeticToEcef, globeAnchor, localToLatLon } from "../src";

describe("ECEF → course frame anchor", () => {
  const o = { lat: 50.43, lon: 5.93 };
  const R = 6371000;
  it("is exact at the anchor and accurate nearby (only Earth-curvature drop remains)", () => {
    const N = 47.2;
    const a = globeAnchor(o.lat, o.lon, 35000, -12000, 320, N);
    for (const [dx, dy, dz] of [[0, 0, 0], [800, 0, 5], [0, -1500, -20], [1414, 1414, 40], [-3000, 1000, 0]]) {
      const x = 35000 + dx, y = -12000 + dy, z = 320 + dz;
      const [lat, lon] = localToLatLon(o.lat, o.lon, x, y);
      const p = applyAnchor(a, geodeticToEcef(lat, lon, z + N));
      const d = Math.hypot(dx, dy);
      expect(Math.hypot(p[0] - x, p[1] - y)).toBeLessThan(0.01 + d * 2e-6);
      expect(p[2] - z).toBeCloseTo(-(d * d) / (2 * R), 1); // tangent-plane drop
    }
  });
  it("maps up to up", () => {
    const a = globeAnchor(o.lat, o.lon, 0, 0, 100);
    const [lat, lon] = localToLatLon(o.lat, o.lon, 0, 0);
    const p0 = applyAnchor(a, geodeticToEcef(lat, lon, 100));
    const p1 = applyAnchor(a, geodeticToEcef(lat, lon, 150));
    expect(p1[2] - p0[2]).toBeCloseTo(50, 6);
    expect(Math.hypot(p1[0] - p0[0], p1[1] - p0[1])).toBeLessThan(1e-6);
  });
});
