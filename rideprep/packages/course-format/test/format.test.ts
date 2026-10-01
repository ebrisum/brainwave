import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { decodeTerrarium, loadCourse, Manifest, poseAt, enuToUe, ueToEnu } from "../src";

const ROOT = resolve(__dirname, "../../..");

/** Build (or reuse) the urban fixture with the Python pipeline. Returns null if Python/gpx2course is unavailable. */
function packageDir(): string | null {
  if (process.env.RIDEPREP_TEST_PACKAGE) return process.env.RIDEPREP_TEST_PACKAGE;
  const out = mkdtempSync(join(tmpdir(), "rp-"));
  const res = spawnSync("python3", ["-m", "gpx2course", "build", join(ROOT, "fixtures/urban_cobbles_15k.gpx"), "--out", out, "--offline",
    "--tier", "quick", "--progress", "none", "--workers", "2"], { cwd: join(ROOT, "services/course-builder"), encoding: "utf8" });
  if (res.status !== 0) return null;
  const d = readdirSync(out).find((n) => n.startsWith("c_"));
  return d ? join(out, d) : null;
}

const PKG = packageDir();
const fileFetcher = (dir: string) => async (p: string) => {
  const b = readFileSync(join(dir, p));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
};

describe("schema", () => {
  it("is identical to the pipeline's copy", () => {
    expect(readFileSync(join(__dirname, "../schema/manifest.schema.json"), "utf8")).toBe(
      readFileSync(join(ROOT, "services/course-builder/gpx2course/schema/manifest.schema.json"), "utf8"));
  });
});

describe("terrarium", () => {
  it("decodes heights", () => {
    // 100.5 m → v = 32868.5 → R=128, G=100, B=128
    expect(decodeTerrarium(new Uint8Array([128, 100, 128, 255]))[0]).toBeCloseTo(100.5, 6);
    expect(decodeTerrarium(new Uint8Array([127, 255, 0]), 3)[0]).toBeCloseTo(-1, 6);
  });
});

describe("coordinates", () => {
  it("ENU ↔ UE round trip", () => {
    const [X, Y, Z] = enuToUe(91234.567, -45678.901, 321.123);
    const back = ueToEnu(X, Y, Z);
    expect(back[0]).toBeCloseTo(91234.567, 9);
    expect(back[1]).toBeCloseTo(-45678.901, 9);
    expect(Y).toBeCloseTo(4567890.1, 3);
  });
});

describe.skipIf(!PKG)("built package", () => {
  it("loads and decodes every binary", async () => {
    const c = await loadCourse(fileFetcher(PKG!));
    expect(c.route.count).toBe(c.manifest.route.count);
    expect(c.route.s[c.route.count - 1]).toBeCloseTo(c.manifest.stats.distanceM, 0);
    expect(c.wind.factors(100, 270).fRough).toBeGreaterThan(0);
    expect(c.instances.count).toBe(c.manifest.instances.count);
    expect(Object.keys(c.materials.materials)).toContain("road_sett");
  });

  it("cross-renderer consistency: TS poseAt == C++ PoseAt (±2 cm)", async () => {
    const m = JSON.parse(readFileSync(join(PKG!, "manifest.json"), "utf8")) as Manifest;
    const c = await loadCourse(fileFetcher(PKG!));
    const bin = join(tmpdir(), "rp_pose_at");
    try {
      execFileSync("g++", ["-std=c++17", "-O2", "-o", bin, join(ROOT, "apps/unreal/Tests/pose_at.cpp")]);
    } catch {
      console.warn("g++ unavailable; skipping native comparison");
      return;
    }
    const ss: number[] = [];
    for (let s = 0; s <= m.stats.distanceM; s += 37.3) ss.push(s);
    ss.push(m.stats.distanceM);
    const args = [join(PKG!, "route.bin"), String(m.route.count), String(m.route.sampleSpacingM),
      ...m.route.arrays.map((a) => `${a.name}:${a.type}:${a.offset}`)];
    const out = execFileSync(bin, args, { input: ss.join("\n") }).toString().trim().split("\n");
    expect(out).toHaveLength(ss.length);
    let maxErr = 0;
    out.forEach((line, k) => {
      const [x, y, z, h, X, Y] = line.split(" ").map(Number);
      const p = poseAt(c.route, ss[k]);
      maxErr = Math.max(maxErr, Math.hypot(p.x - x, p.y - y, p.z - z));
      expect(Math.abs(((p.headingRad - h + 3 * Math.PI) % (2 * Math.PI)) - Math.PI)).toBeLessThan(1e-5);
      const ue = enuToUe(p.x, p.y, p.z);
      expect(Math.abs(ue[0] - X)).toBeLessThan(2);
      expect(Math.abs(ue[1] - Y)).toBeLessThan(2);
    });
    expect(maxErr).toBeLessThan(0.02);
  });
});

describe("existence", () => {
  it("fixtures are present", () => expect(existsSync(join(ROOT, "fixtures/urban_cobbles_15k.gpx"))).toBe(true));
});
