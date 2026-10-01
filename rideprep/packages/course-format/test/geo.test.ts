import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { localToLatLon } from "../src";

describe("local frame → WGS84", () => {
  const ref = JSON.parse(readFileSync(join(__dirname, "tmerc_ref.json"), "utf8")) as number[][];
  it("matches PROJ tmerc to < 1 cm within ±120 km", () => {
    for (const [lat0, lon0, x, y, lat, lon] of ref) {
      const [la, lo] = localToLatLon(lat0, lon0, x, y);
      const dy = (la - lat) * 111320;
      const dx = (lo - lon) * 111320 * Math.cos((lat * Math.PI) / 180);
      expect(Math.hypot(dx, dy)).toBeLessThan(0.01);
    }
  });
});
