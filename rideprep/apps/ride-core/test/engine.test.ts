import { decode, encode } from "@msgpack/msgpack";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import WebSocket from "ws";
import { StreamState } from "@rideprep/course-format";
import { DEFAULT_RIDER } from "@rideprep/physics";
import { loadPackage } from "../src/course";
import { RideEngine } from "../src/engine";
import { serve } from "../src/server";

const ROOT = resolve(__dirname, "../../..");

function pkg(): string | null {
  if (process.env.RIDEPREP_TEST_PACKAGE) return process.env.RIDEPREP_TEST_PACKAGE;
  const out = mkdtempSync(join(tmpdir(), "rc-"));
  const r = spawnSync("python3", ["-m", "gpx2course", "build", join(ROOT, "fixtures/urban_cobbles_15k.gpx"), "--out", out, "--offline", "--tier", "quick",
    "--targets", "web", "--progress", "none", "--workers", "2"], { cwd: join(ROOT, "services/course-builder"), encoding: "utf8" });
  if (r.status !== 0) return null;
  const d = readdirSync(out).find((n) => n.startsWith("c_"));
  return d ? join(out, d) : null;
}

const PKG = pkg();

describe.skipIf(!PKG)("ride core", () => {
  it("streams MessagePack state at ~50 Hz with low latency, controls a virtual trainer and obeys pause", async () => {
    const course = await loadPackage(PKG!);
    const engine = new RideEngine(course, { rider: DEFAULT_RIDER, startEpoch: Date.parse("2026-06-01T08:00:00Z") / 1000, seed: 7 });
    const dev = await engine.pair("trainer", RideEngine.virtual(250));
    expect(dev.name).toContain("Virtual");
    const port = 18765 + Math.floor(Math.random() * 1000);
    const wss = serve(engine, { port, packageUrl: PKG! });
    engine.start();
    const ws = new WebSocket(`ws://127.0.0.1:${port}`);
    const states: StreamState[] = [];
    const lat: number[] = [];
    let hello: { courseId: string } | undefined;
    ws.on("message", (d: Buffer) => {
      const m = decode(d) as StreamState | { type: "hello"; courseId: string };
      if (m.type === "hello") hello = m;
      else { states.push(m); lat.push(Date.now() - m.sentAt); }
    });
    await new Promise((r) => setTimeout(r, 3000));
    expect(hello?.courseId).toBe(course.manifest.courseId);
    const n = states.length;
    expect(n).toBeGreaterThan(120); // ~150 in 3 s
    expect(n).toBeLessThan(180);
    expect(states[n - 1].s).toBeGreaterThan(states[0].s);
    expect(states[n - 1].power).toBeGreaterThan(100);
    lat.sort((a, b) => a - b);
    expect(lat[Math.floor(lat.length * 0.95)]).toBeLessThanOrEqual(20);
    // Trainer received FTMS simulation commands
    const cmds = (engine.trainer as unknown as { log: { bytes: number[] }[] }).log.map((l) => l.bytes[0]);
    expect(cmds).toContain(0x11);
    // Pause over the socket
    ws.send(encode({ type: "pause" }));
    await new Promise((r) => setTimeout(r, 300));
    const s0 = states[states.length - 1].s;
    await new Promise((r) => setTimeout(r, 500));
    expect(states[states.length - 1].paused).toBe(true);
    expect(states[states.length - 1].s).toBeCloseTo(s0, 6);
    const fit = await engine.finish();
    expect(fit.length).toBeGreaterThan(100);
    ws.close();
    wss.close();
  }, 30000);
});
