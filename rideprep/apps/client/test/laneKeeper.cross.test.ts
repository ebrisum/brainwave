import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { LaneKeeper, RoadLine } from "../src/engine/LaneKeeper";

/** The Unreal lane keeper (RidePrepLaneKeeper.h) must ride exactly the same line as the web one. */
describe("lane keeper: web ↔ Unreal (native harness)", () => {
  const sp = 5;
  const n = 600;
  // Straight, a right-hander (R 25 m), a narrow 3 m stretch, a left hairpin (R 9 m), straight
  const heading = new Float32Array(n);
  const width = new Uint8Array(n).fill(6);
  let h = 0;
  for (let i = 0; i < n; i++) {
    const s = i * sp;
    if (s > 500 && s <= 500 + (Math.PI / 2) * 25) h += sp / 25;
    if (s > 1500 && s <= 1500 + Math.PI * 9) h -= sp / 9;
    heading[i] = ((h % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
    if (s > 1000 && s < 1300) width[i] = 3;
  }
  const x = new Float32Array(n), y = new Float32Array(n), z = new Float32Array(n), s = Float32Array.from({ length: n }, (_, i) => i * sp);
  const route = { spacingM: sp, count: n, s, x, y, z, gradePct: z, headingRad: heading, radiusM: new Float32Array(n).fill(Infinity),
                  crrMultiplier: new Float32Array(n).fill(1), roadWidthM: width };
  const bin = join(tmpdir(), "rp_lane_route.bin");
  const parts = [s, x, y, z, heading].map((a) => Buffer.from(a.buffer));
  writeFileSync(bin, Buffer.concat([...parts, Buffer.from(width.buffer)]));
  const layout = ["s", "x", "y", "z", "headingRad"].map((nm, k) => `${nm}:float32:${k * 4 * n}`).concat(`roadWidthM:uint8:${5 * 4 * n}`);
  // A ride with uneven frame times: fast on the flat, a slow climb (weave), a stop
  const steps: [number, number, number, number][] = [];
  let pos = 0, crank = 0;
  for (let k = 0; k < 4000; k++) {
    const dt = 1 / 60 + ((k * 7919) % 13) / 1300;
    const v = pos < 1200 ? 11 : pos < 1700 ? 1.8 + ((k % 50) / 50) * 0.8 : pos < 2600 ? 9 : 0;
    pos += v * dt;
    crank += (v > 0 ? 75 : 0) / 60 * 2 * Math.PI * dt;
    steps.push([dt, pos, v, crank]);
  }

  for (const line of ["keepRight", "racing"] as RoadLine[]) {
    it(`same offsets, yaw and lean (${line})`, () => {
      const exe = join(tmpdir(), "rp_lane_keeper");
      try {
        execFileSync("g++", ["-std=c++17", "-O2", "-o", exe, join(__dirname, "../../unreal/Tests/lane_keeper.cpp")]);
      } catch {
        return; // no compiler on this machine
      }
      const input = steps.map((p) => p.map((v) => v.toPrecision(17)).join(" ")).join("\n");
      const out = execFileSync(exe, [bin, String(n), String(sp), line, ...layout], { input }).toString().trim().split("\n");
      const k = new LaneKeeper(route, line);
      expect(out.length).toBe(steps.length);
      let maxD = 0;
      steps.forEach(([dt, sNow, v, cr], i) => {
        k.update(dt, sNow, v, cr);
        const [o, yw, ln] = out[i].split(" ").map(Number);
        maxD = Math.max(maxD, Math.abs(o - k.offset), Math.abs(yw - k.yaw), Math.abs(ln - k.lean));
      });
      expect(maxD).toBeLessThan(1e-6);
    });
  }
});
