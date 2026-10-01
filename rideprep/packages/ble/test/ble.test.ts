import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  backoffMs, encodeCyclingPower, encodeHeartRate, encodeIndoorBikeData, encodeSimulation, lookaheadGrade, ManagedConnection,
  parseControlPointResponse, parseCsc, parseCyclingPower, parseHeartRate, parseIndoorBikeData, RevolutionRate, SensorHub,
  toDataView, TrainerController, VirtualDevice, windResistanceCoefficient,
} from "../src";

const hex = (b: Uint8Array) => Array.from(b, (x) => x.toString(16).padStart(2, "0").toUpperCase()).join(" ");

describe("16.4 FTMS encoding", () => {
  it("simulation parameters wind 3.5, grade 5 %, Crr 0.004, Cw 0.51", () => {
    expect(hex(encodeSimulation({ windSpeedMs: 3.5, gradePct: 5, crr: 0.004, cwKgM: 0.51 }))).toBe("11 AC 0D F4 01 28 33");
  });
  it("negative wind and grade encode as sint16", () => {
    const b = encodeSimulation({ windSpeedMs: -2, gradePct: -3.5, crr: 0.004, cwKgM: 0.51 });
    const dv = new DataView(b.buffer);
    expect(dv.getInt16(1, true)).toBe(-2000);
    expect(dv.getInt16(3, true)).toBe(-350);
  });
  it("Cw = ρ·CdA", () => expect(windResistanceCoefficient(1.225, 0.416)).toBeCloseTo(0.51, 2));
  it("parses control point responses", () => {
    expect(parseControlPointResponse(toDataView([0x80, 0x11, 0x01]))).toEqual({ requestOp: 0x11, result: 1 });
    expect(parseControlPointResponse(toDataView([0x11, 0x01]))).toBeNull();
  });
});

describe("16.4 parsers", () => {
  it("HR 00 8C → 140", () => expect(parseHeartRate(toDataView([0x00, 0x8c])).bpm).toBe(140));
  it("HR 01 8C 00 → 140 (uint16)", () => expect(parseHeartRate(toDataView([0x01, 0x8c, 0x00])).bpm).toBe(140));
  it("HR with RR intervals", () => {
    const d = parseHeartRate(toDataView(encodeHeartRate(120, [0.5, 0.75])));
    expect(d.bpm).toBe(120);
    expect(d.rrIntervalsS).toEqual([0.5, 0.75]);
  });
  it("CPS 00 00 C8 00 → 200 W", () => expect(parseCyclingPower(toDataView([0, 0, 0xc8, 0])).powerW).toBe(200));
  it("CPS negative power is signed", () => expect(parseCyclingPower(toDataView([0, 0, 0xf6, 0xff])).powerW).toBe(-10));
  it("CPS with pedal balance and crank data", () => {
    // flags 0x21: balance + crank. power 250, balance 100 (50 %), revs 1234, time 2048 ticks
    const d = parseCyclingPower(toDataView([0x21, 0x00, 0xfa, 0x00, 100, 0xd2, 0x04, 0x00, 0x08]));
    expect(d.powerW).toBe(250);
    expect(d.pedalBalancePct).toBe(50);
    expect(d.crank?.revs).toBe(1234);
    expect(d.crank?.eventTime).toBe(2);
  });
  it("crank wraparound gives the right cadence", () => {
    const rate = new RevolutionRate();
    const mk = (revs: number, ticks: number) => parseCyclingPower(toDataView(encodeCyclingPower({ powerW: 200, crankRevs: revs, crankEventTicks: ticks }))).crank!;
    rate.update(mk(65535, 65000), 0);
    // 3 revolutions over (65536 - 65000 + 1000) = 1536 ticks = 1.5 s → 120 rpm
    expect(rate.update(mk(2, 1000), 1.5)).toBeCloseTo(120, 6);
  });
  it("repeated event keeps the cadence, then goes stale to 0", () => {
    const rate = new RevolutionRate(3);
    const d = (revs: number, ticks: number) => ({ revs, eventTicks: ticks, eventTime: ticks / 1024, ticksPerSecond: 1024, revBits: 16 });
    rate.update(d(10, 0), 0);
    expect(rate.update(d(11, 683), 0.7)).toBeCloseTo(60 / (683 / 1024), 6);
    expect(rate.update(d(11, 683), 2)).toBeGreaterThan(0);
    expect(rate.update(d(11, 683), 5)).toBe(0);
  });
  it("Indoor Bike Data with speed + cadence + power", () => {
    // flags 0x0044 (bit0=0 → speed present, cadence, power); speed 36.00 km/h, cadence 90 rpm, power 250 W
    const d = parseIndoorBikeData(toDataView([0x44, 0x00, 0x10, 0x0e, 0xb4, 0x00, 0xfa, 0x00]));
    expect(d.speedKmh).toBe(36);
    expect(d.cadenceRpm).toBe(90);
    expect(d.powerW).toBe(250);
  });
  it("Indoor Bike Data with More Data set has no speed and parses later fields", () => {
    const d = parseIndoorBikeData(toDataView([0x51, 0x02, 0x10, 0x27, 0x00, 0x64, 0x00, 0x96]));
    // flags 0x0251: more data, total distance (uint24 = 10000), power 100, HR 150
    expect(d.speedKmh).toBeUndefined();
    expect(d.totalDistanceM).toBe(10000);
    expect(d.powerW).toBe(100);
    expect(d.heartRateBpm).toBe(150);
  });
  it("encoders round-trip", () => {
    const d = parseIndoorBikeData(toDataView(encodeIndoorBikeData({ speedKmh: 32.5, cadenceRpm: 91.5, powerW: 287, heartRateBpm: 151 })));
    expect(d).toMatchObject({ speedKmh: 32.5, cadenceRpm: 91.5, powerW: 287, heartRateBpm: 151 });
  });
  it("CSC wheel + crank", () => {
    const d = parseCsc(toDataView([0x03, 0x10, 0x00, 0x00, 0x00, 0x00, 0x04, 0x05, 0x00, 0x00, 0x08]));
    expect(d.wheel?.revs).toBe(16);
    expect(d.wheel?.eventTime).toBe(1);
    expect(d.crank?.revs).toBe(5);
    expect(d.crank?.eventTime).toBe(2);
  });
});

describe("trainer controller", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("requests control first, then serialises simulation updates", async () => {
    const dev = new VirtualDevice();
    let now = 0;
    const tc = new TrainerController(dev, { now: () => now });
    await tc.start();
    expect(dev.commands.map((c) => c[0])).toEqual([0x00, 0x07]);
    tc.setSimulation({ windSpeedMs: 3.5, gradePct: 5, crr: 0.004, cwKgM: 0.51 });
    await tc.tick(now);
    expect(hex(Uint8Array.from(dev.commands[2]))).toBe("11 AC 0D F4 01 28 33");
    // Tiny change: not sent; rate limit 2/s
    now = 300;
    tc.setSimulation({ windSpeedMs: 3.55, gradePct: 5.05, crr: 0.004, cwKgM: 0.51 });
    await tc.tick(now);
    expect(dev.commands).toHaveLength(3);
    now = 400;
    tc.setSimulation({ windSpeedMs: 3.5, gradePct: 6, crr: 0.004, cwKgM: 0.51 });
    await tc.tick(now);
    expect(dev.commands).toHaveLength(3); // < 500 ms since last
    now = 600;
    await tc.tick(now);
    expect(dev.commands).toHaveLength(4);
    // Keep-alive after 5 s with no change
    now = 5700;
    await tc.tick(now);
    expect(dev.commands).toHaveLength(5);
  });

  it("times out after 1.5 s without a response", async () => {
    const dev = new VirtualDevice();
    dev.write = async () => {}; // never answers
    const tc = new TrainerController(dev);
    const p = tc.send(Uint8Array.of(0x00));
    await vi.advanceTimersByTimeAsync(1500);
    expect(await p).toBe("timeout");
  });

  it("falls back to resistance when 0x11 is not supported", async () => {
    const dev = new VirtualDevice({ rejectSimulation: true });
    const warn = vi.fn();
    const tc = new TrainerController(dev, { now: () => 0, onWarning: warn });
    await tc.start();
    tc.setSimulation({ windSpeedMs: 0, gradePct: 3, crr: 0.004, cwKgM: 0.51 });
    await tc.tick(0);
    expect(tc.mode).toBe("resistance-fallback");
    expect(warn).toHaveBeenCalled();
  });

  it("difficulty scales only positive grades sent, and grade is clamped", () => {
    const tc = new TrainerController(new VirtualDevice(), { difficulty: 0.5, gradeRange: [-10, 15] });
    expect(tc.gradeToSend(8)).toBe(4);
    expect(tc.gradeToSend(-4)).toBe(-4);
    expect(tc.gradeToSend(-30)).toBe(-10);
  });

  it("look-ahead grade averages ahead of the rider", () => {
    const gradeAt = (s: number) => (s >= 100 ? 10 : 0);
    expect(lookaheadGrade(gradeAt, 90, 10, 0.7, 15)).toBeGreaterThan(5); // looks at 97..112 m, mostly the wall
    expect(lookaheadGrade(gradeAt, 0, 10)).toBe(0);
  });
});

describe("sensor hub priorities", () => {
  it("prefers the power meter, falls back to the trainer when stale", () => {
    let now = 0;
    const hub = new SensorHub(() => now);
    hub.onIndoorBikeData(toDataView(encodeIndoorBikeData({ speedKmh: 30, powerW: 240, cadenceRpm: 85 })));
    expect(hub.r.powerSource).toBe("trainer");
    hub.onCyclingPower(toDataView(encodeCyclingPower({ powerW: 250, crankRevs: 1, crankEventTicks: 0 })));
    expect(hub.r.powerW).toBe(250);
    expect(hub.r.powerSource).toBe("powerMeter");
    now = 4000;
    hub.onIndoorBikeData(toDataView(encodeIndoorBikeData({ speedKmh: 30, powerW: 241 })));
    expect(hub.r.powerSource).toBe("trainer");
    expect(hub.r.powerW).toBe(241);
  });
});

describe("reconnect", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());
  it("backoff schedule", () => expect([0, 1, 2, 3, 5, 9].map(backoffMs)).toEqual([1000, 2000, 4000, 8000, 30000, 30000]));
  it("reconnects after a drop", async () => {
    const dev = new VirtualDevice();
    const states: string[] = [];
    const setup = vi.fn(async () => {});
    const mc = new ManagedConnection(dev, setup, (s) => states.push(s));
    await mc.start();
    dev.drop();
    expect(mc.state).toBe("reconnecting");
    await vi.advanceTimersByTimeAsync(1000);
    expect(mc.state).toBe("connected");
    expect(setup).toHaveBeenCalledTimes(2);
    await mc.stop();
  });
});
