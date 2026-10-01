/**
 * BLE peripheral emulating a smart trainer (FTMS), a power meter (CPS) and a heart-rate strap (HRS) with a scripted
 * rider. Accepts and logs FTMS 0x11 simulation commands. Needs Linux/macOS with a BLE adapter (@abandonware/bleno).
 * Usage: pnpm --filter @rideprep/ble-emulator start [--ftp 250] [--name "RidePrep Emu"]
 */
import { parseArgs } from "node:util";
import { demoRider } from "@rideprep/ble";
import { EmulatorCore } from "./core";

const { values } = parseArgs({ options: { ftp: { type: "string", default: "250" }, name: { type: "string", default: "RidePrep Emu" }, hz: { type: "string", default: "4" } } });
const rider = demoRider(Number(values.ftp));
const core = new EmulatorCore({ power: rider.power, hr: rider.heartRate, cadence: rider.cadence });

type Bleno = {
  on(ev: string, cb: (...a: unknown[]) => void): void; startAdvertising(name: string, uuids: string[]): void; setServices(s: unknown[]): void;
  PrimaryService: new (o: unknown) => unknown; Characteristic: new (o: unknown) => unknown & { RESULT_SUCCESS: number };
};
const bleno = (await import("@abandonware/bleno" as string)).default as Bleno;
const { PrimaryService, Characteristic } = bleno;
const subs: Record<string, ((d: Buffer) => void) | undefined> = {};
const notifyChar = (uuid: string, key: string) => new Characteristic({
  uuid, properties: ["notify"],
  onSubscribe: (_max: number, cb: (d: Buffer) => void) => { subs[key] = cb; },
  onUnsubscribe: () => { subs[key] = undefined; },
});
const readChar = (uuid: string, value: number[]) => new Characteristic({ uuid, properties: ["read"], value: Buffer.from(value) });
const controlPoint = new Characteristic({
  uuid: "2AD9", properties: ["write", "indicate"],
  onSubscribe: (_m: number, cb: (d: Buffer) => void) => { subs.cp = cb; },
  onWriteRequest: (data: Buffer, _off: number, _wr: boolean, cb: (r: number) => void) => {
    const res = core.controlPoint(new Uint8Array(data));
    const last = core.log[core.log.length - 1];
    console.log(`[FTMS] op 0x${last.op.toString(16).padStart(2, "0")} ${JSON.stringify(last.decoded ?? {})} → result ${res[2]}`);
    cb(0);
    setTimeout(() => subs.cp?.(Buffer.from(res)), 5);
  },
});
const ftmsFeature = [0x02, 0x40, 0x00, 0x00, 0x0c, 0x20, 0x00, 0x00]; // cadence+power data; power & simulation targets
bleno.on("stateChange", (state: unknown) => {
  if (state === "poweredOn") bleno.startAdvertising(values.name!, ["1826", "1818", "180D"]);
});
bleno.on("advertisingStart", () => {
  bleno.setServices([
    new PrimaryService({ uuid: "1826", characteristics: [readChar("2ACC", ftmsFeature), notifyChar("2AD2", "ibd"), controlPoint,
      readChar("2AD8", [0, 0, 0xd0, 0x07, 1, 0]), notifyChar("2ADA", "status")] }),
    new PrimaryService({ uuid: "1818", characteristics: [notifyChar("2A63", "cps"), readChar("2A65", [0x08, 0, 0, 0])] }),
    new PrimaryService({ uuid: "180D", characteristics: [notifyChar("2A37", "hr")] }),
  ]);
  console.log(`Advertising "${values.name}" (FTMS, CPS, HRS)`);
});
const dt = 1 / Number(values.hz);
setInterval(() => {
  const n = core.tick(dt);
  subs.ibd?.(Buffer.from(n.indoorBikeData));
  subs.cps?.(Buffer.from(n.cyclingPower));
  subs.hr?.(Buffer.from(n.heartRate));
}, dt * 1000);
