#!/usr/bin/env node
import { writeFile, mkdir } from "node:fs/promises";
import { parseArgs } from "node:util";
import { DEFAULT_RIDER } from "@rideprep/physics";
import { loadPackage } from "./course";
import { RideEngine } from "./engine";
import { NobleAdapter } from "./noble";
import { serve } from "./server";

const { values } = parseArgs({
  options: {
    package: { type: "string", short: "p" },
    port: { type: "string", default: "8765" },
    virtual: { type: "boolean", default: false },
    ftp: { type: "string", default: String(DEFAULT_RIDER.ftpW) },
    mass: { type: "string", default: String(DEFAULT_RIDER.riderMassKg) },
    cda: { type: "string", default: String(DEFAULT_RIDER.cda) },
    "event-start": { type: "string" },
    out: { type: "string", default: "./rides" },
  },
});

if (!values.package) {
  console.error("usage: ride-core --package <dir|http url> [--virtual] [--ftp 280] [--port 8765]");
  process.exit(2);
}

const course = await loadPackage(values.package);
const ev = values["event-start"] ?? course.manifest.eventStart;
const engine = new RideEngine(course, {
  rider: { ...DEFAULT_RIDER, ftpW: Number(values.ftp), riderMassKg: Number(values.mass), cda: Number(values.cda) },
  startEpoch: ev ? Date.parse(ev) / 1000 : Date.now() / 1000,
});
if (values.virtual) {
  await engine.pair("trainer", RideEngine.virtual(Number(values.ftp)));
} else {
  const ble = new NobleAdapter();
  if (!(await ble.isAvailable())) {
    console.error("Bluetooth unavailable (install @abandonware/noble and check adapter permissions), or use --virtual");
    process.exit(1);
  }
  console.log("Scanning for a smart trainer (FTMS)…");
  await engine.pair("trainer", ble);
  try { await engine.pair("hr", ble); } catch { console.log("No heart-rate strap found; continuing"); }
}
serve(engine, { port: Number(values.port), packageUrl: values.package, onCommand: async (c) => {
  if (c.type === "end") {
    const fit = await engine.finish();
    await mkdir(values.out!, { recursive: true });
    const f = `${values.out}/${course.manifest.courseId}_${engine.startedAt}.fit`;
    await writeFile(f, fit);
    console.log(`Saved ${f}`);
    process.exit(0);
  }
} });
engine.start();
console.log(`ride-core: ${course.manifest.name} — ws://127.0.0.1:${values.port} (MessagePack, 50 Hz)`);
