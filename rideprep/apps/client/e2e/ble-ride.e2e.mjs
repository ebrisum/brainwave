// End-to-end: pair an emulated smart trainer, HR strap and power meter through the app's real Web Bluetooth code,
// start a ride at the foot of a climb and record what the trainer is told (grade, wind, Crr, Cw) vs the course.
//   node e2e/ble-ride.e2e.mjs <outDir> [startKm] [rideSeconds] [baseUrl]
import { chromium } from "playwright-core";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const [out = "e2e-out", startKm = "45.2", rideS = "90", base = "http://localhost:5173", view = "Cockpit"] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const here = dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM ?? "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.addInitScript({ content: readFileSync(join(here, "webbluetooth-mock.js"), "utf8") });
await page.goto(`${base}/?start=${startKm}`);
await page.waitForSelector("text=Smart trainer");
await page.waitForTimeout(3000);
// Pair the three devices (the mock answers the chooser with the matching device)
const rows = page.locator(".devices li");
for (const i of [0, 2, 1]) {
  await rows.nth(i).getByRole("button", { name: "Connect" }).click();
  await rows.nth(i).locator(".pill.ok").waitFor({ timeout: 15000 });
}
await page.waitForTimeout(2500);
await page.screenshot({ path: join(out, "1_setup_devices.png") });
await page.getByRole("button", { name: view, exact: true }).click();
await page.getByRole("button", { name: /Start ride/ }).click();
await page.waitForFunction(() => window.__rideprepSession?.isStarted, null, { timeout: 120000 });
const samples = [];
const t0 = Date.now();
let shot = 0;
while (Date.now() - t0 < Number(rideS) * 1000) {
  await page.waitForTimeout(1000);
  const s = await page.evaluate(() => {
    const x = window.__rideprepSession, b = window.__ble;
    const st = x?.curr;
    const last = [...b.log].reverse().find((e) => e.op === 0x11);
    return st && { t: performance.now() / 1000, s: st.s, gradePct: st.gradePct, v: st.v, powerW: x.hub.r.powerW, hr: x.hub.r.heartRateBpm,
      cadence: x.hub.r.cadenceRpm, powerSource: x.hub.r.powerSource, wHead: st.wind.wHead, crrEff: st.crrEff,
      sentGrade: last?.gradePct, sentWind: last?.windMs, sentCrr: last?.crr, sentCw: last?.cw, trainerKmh: b.speedKmh, mode: x.trainer?.mode };
  });
  if (s) samples.push(s);
  if (Date.now() - t0 > (shot + 1) * (Number(rideS) * 1000) / 4) {
    shot++;
    await page.screenshot({ path: join(out, `2_ride_${shot}.png`) });
  }
}
const log = await page.evaluate(() => window.__ble.log);
writeFileSync(join(out, "ble_ride.json"), JSON.stringify({ samples, log, errors }, null, 1));
const sims = log.filter((e) => e.op === 0x11);
console.log(JSON.stringify({
  controlRequested: log.some((e) => e.op === 0x00), started: log.some((e) => e.op === 0x07), simCommands: sims.length,
  gradeSent: sims.length ? [Math.min(...sims.map((e) => e.gradePct)), Math.max(...sims.map((e) => e.gradePct))] : null,
  distanceM: samples.length ? [samples[0].s, samples[samples.length - 1].s] : null, errors,
}));
await browser.close();
