import { describe, expect, it } from "vitest";
import { encodeSimulation, encodeSetTargetPower, parseCyclingPower, parseIndoorBikeData, RevolutionRate, toDataView } from "@rideprep/ble";
import { EmulatorCore } from "../src/core";

const core = () => new EmulatorCore({ power: () => 220, hr: () => 135, cadence: () => 90 }, () => 0);

describe("emulator core", () => {
  it("requires Request Control before other commands", () => {
    const c = core();
    expect(Array.from(c.controlPoint(encodeSimulation({ windSpeedMs: 1, gradePct: 2, crr: 0.004, cwKgM: 0.51 })))).toEqual([0x80, 0x11, 0x05]);
    expect(Array.from(c.controlPoint(Uint8Array.of(0x00)))).toEqual([0x80, 0x00, 0x01]);
  });
  it("accepts and logs 0x11 with decoded parameters", () => {
    const c = core();
    c.controlPoint(Uint8Array.of(0x00));
    c.controlPoint(encodeSimulation({ windSpeedMs: 3.5, gradePct: 5, crr: 0.004, cwKgM: 0.51 }));
    const e = c.log[c.log.length - 1];
    expect(e.op).toBe(0x11);
    expect(e.decoded).toEqual({ windSpeedMs: 3.5, gradePct: 5, crr: 0.004, cwKgM: 0.51 });
  });
  it("holds ERG target power", () => {
    const c = core();
    c.controlPoint(Uint8Array.of(0x00));
    c.controlPoint(encodeSetTargetPower(300));
    expect(parseCyclingPower(toDataView(c.tick(0.25).cyclingPower)).powerW).toBe(300);
    expect(parseIndoorBikeData(toDataView(c.tick(0.25).indoorBikeData)).powerW).toBe(300);
  });
  it("crank data gives the scripted cadence", () => {
    const c = core();
    const rate = new RevolutionRate();
    let rpm = 0;
    for (let k = 0; k < 60; k++) rpm = rate.update(parseCyclingPower(toDataView(c.tick(0.25).cyclingPower)).crank!, k * 0.25);
    expect(rpm).toBeGreaterThan(87);
    expect(rpm).toBeLessThan(93);
  });
  it("unsupported op codes return 0x02", () => {
    const c = core();
    c.controlPoint(Uint8Array.of(0x00));
    expect(c.controlPoint(Uint8Array.of(0x13))[2]).toBe(0x02);
  });
});
