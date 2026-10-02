import { describe, expect, it } from "vitest";
import { LaneKeeper } from "../src/engine/LaneKeeper";

/** A route of 5 m samples: straight north, then a 90° bend of radius R (right if dir = 1), then straight again. */
function route(widthM: number, dir: 1 | -1, R = 20) {
  const sp = 5;
  const n = 200;
  const bendStart = 400;
  const bendLen = (Math.PI / 2) * R;
  const heading = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const s = i * sp;
    const t = Math.min(1, Math.max(0, (s - bendStart) / bendLen));
    heading[i] = (((dir * t * Math.PI) / 2 + 2 * Math.PI) % (2 * Math.PI));
  }
  const z = new Float32Array(n);
  return {
    spacingM: sp, count: n, s: Float32Array.from({ length: n }, (_, i) => i * sp), x: z, y: z, z, gradePct: z, headingRad: heading,
    radiusM: new Float32Array(n).fill(Infinity), crrMultiplier: new Float32Array(n).fill(1), roadWidthM: new Uint8Array(n).fill(widthM),
  };
}

function ride(k: LaneKeeper, s0: number, s1: number, v = 9) {
  const out: { s: number; off: number; yaw: number; lean: number }[] = [];
  const dt = 1 / 60;
  for (let s = s0; s <= s1; s += v * dt) {
    k.update(dt, s, v, s * 2);
    out.push({ s, off: k.offset, yaw: k.yaw, lean: k.lean });
  }
  return out;
}

describe("lane keeper", () => {
  it("keeps right about 1 m from the edge on a two-lane road, never over the centre line", () => {
    const k = new LaneKeeper(route(6, -1), "keepRight");
    const tr = ride(k, 0, 900);
    expect(tr[10].off).toBeCloseTo(2, 1); // 6 m road: 1 m from the right edge
    for (const p of tr) {
      expect(p.off).toBeGreaterThan(0.25);
      expect(p.off).toBeLessThan(2.55);
    }
  });

  it("drifts toward the lane centre on a left-hander and tighter to the edge on a right-hander", () => {
    const left = ride(new LaneKeeper(route(6, -1), "keepRight"), 0, 900);
    const right = ride(new LaneKeeper(route(6, 1), "keepRight"), 0, 900);
    const at = (tr: typeof left, s: number) => tr.reduce((a, b) => (Math.abs(b.s - s) < Math.abs(a.s - s) ? b : a)).off;
    expect(at(left, 415)).toBeLessThan(1.8);
    expect(at(right, 415)).toBeGreaterThan(2.1);
  });

  it("moves smoothly: bounded lateral speed, yaw and lean", () => {
    const tr = ride(new LaneKeeper(route(6, -1, 12), "racing"), 0, 900);
    for (let i = 1; i < tr.length; i++) {
      const vLat = (tr[i].off - tr[i - 1].off) / (1 / 60);
      expect(Math.abs(vLat)).toBeLessThan(1.7);
      expect(Math.abs(tr[i].yaw)).toBeLessThanOrEqual(0.12 + 1e-9);
      expect(Math.abs(tr[i].lean)).toBeLessThan(0.13);
    }
  });

  it("racing line uses the inside of the bend on closed roads", () => {
    const tr = ride(new LaneKeeper(route(8, -1), "racing"), 0, 900);
    const apex = tr.reduce((a, b) => (Math.abs(b.s - 420) < Math.abs(a.s - 420) ? b : a));
    expect(apex.off).toBeLessThan(-1.5); // left-hander: inside is left of the centre line
  });

  it("rides the middle of a single-lane road", () => {
    const tr = ride(new LaneKeeper(route(3, 1), "keepRight"), 0, 300);
    expect(Math.abs(tr[tr.length - 1].off)).toBeLessThan(0.05);
  });
});
