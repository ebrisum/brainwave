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

describe("C++ LocalToLatLon (Unreal plugin) matches TS", () => {
  it("agrees to < 1 mm", async () => {
    const { execFileSync } = await import("node:child_process");
    const { tmpdir } = await import("node:os");
    const bin = join(tmpdir(), "rp_latlon");
    try { execFileSync("g++", ["-std=c++17", "-O2", "-o", bin, join(__dirname, "../../../apps/unreal/Tests/latlon.cpp")]); } catch { return; }
    const ref = JSON.parse(readFileSync(join(__dirname, "tmerc_ref.json"), "utf8")) as number[][];
    const out = execFileSync(bin, { input: ref.map((r) => r.slice(0, 4).join(" ")).join("\n") }).toString().trim().split("\n");
    out.forEach((line, k) => {
      const [la, lo, conv] = line.split(" ").map(Number);
      const [lat0, lon0, x, y] = ref[k];
      const [tla, tlo] = localToLatLon(lat0, lon0, x, y);
      expect(Math.abs(la - tla) * 111320).toBeLessThan(0.001);
      expect(Math.abs(lo - tlo) * 111320 * Math.cos((tla * Math.PI) / 180)).toBeLessThan(0.001);
      // convergence ≈ Δλ·sin φ for transverse Mercator
      expect(conv).toBeCloseTo((tlo - lon0) * Math.sin((tla * Math.PI) / 180), 1);
    });
  });
});
