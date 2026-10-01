import { Decoder, Stream } from "@garmin/fitsdk";
import { describe, expect, it } from "vitest";
import {
  aerobicDecoupling, bestAverage, normalizedPower, RideRecord, segmentComparison, splitTimes, summarize, timeInHrZones, timeInPowerZones,
  toFit, toGpx, toTcx, trainingStressScore, wPrimeBalance,
} from "../src";

const ride = (n: number, p: (i: number) => number, hr = (i: number) => 140): RideRecord[] =>
  Array.from({ length: n }, (_, i) => ({
    t: Date.UTC(2026, 8, 20, 8) + i * 1000, s: i * 9, lat: 52 + i * 1e-5, lon: 5, ele: 10 + (i % 100 === 0 ? 2 : 0), powerW: p(i),
    hrBpm: hr(i), cadenceRpm: 90, speedMs: 9, gradePct: 0, windSpeed10: 5, windDirDeg: 270, uRider: 3, wHead: 1.2, wCross: 2, shelter: 0.8,
    tempC: 18, rho: 1.2, crrEff: 0.004, braking: i % 500 === 0,
  }));

describe("power metrics", () => {
  it("NP of constant power equals the power", () => expect(normalizedPower(new Array(3600).fill(250))).toBeCloseTo(250, 6));
  it("NP exceeds average for variable power", () => {
    const p = Array.from({ length: 3600 }, (_, i) => (Math.floor(i / 60) % 2 ? 350 : 150));
    expect(normalizedPower(p)).toBeGreaterThan(260);
  });
  it("1 h at FTP is 100 TSS", () => expect(trainingStressScore(3600, 250, 250)).toBeCloseTo(100, 6));
  it("W′ depletes above CP and recovers below", () => {
    const p = [...new Array(60).fill(400), ...new Array(600).fill(100)];
    const w = wPrimeBalance(p, 250, 20000);
    expect(w[59]).toBeCloseTo(20000 - 150 * 60, 6);
    expect(w[659]).toBeGreaterThan(w[59]);
    expect(w[659]).toBeLessThanOrEqual(20000);
  });
  it("zones sum to duration", () => {
    const p = Array.from({ length: 1000 }, (_, i) => i / 2);
    expect(timeInPowerZones(p, 250).reduce((a, b) => a + b)).toBe(1000);
    expect(timeInHrZones(new Array(100).fill(171), 190)[4]).toBe(100);
  });
  it("decoupling detects HR drift", () => {
    const p = new Array(3600).fill(220);
    const hr = Array.from({ length: 3600 }, (_, i) => 140 + (i / 3600) * 14);
    expect(aerobicDecoupling(p, hr)).toBeGreaterThan(3);
  });
  it("best average", () => expect(bestAverage([100, 300, 300, 100], 2)).toBe(300));
});

describe("summary and comparisons", () => {
  const recs = ride(1800, () => 250);
  it("summarizes", () => {
    const s = summarize(recs, 250, 20000);
    expect(s.npW).toBeCloseTo(250, 3);
    expect(s.tss).toBeCloseTo(50, 0);
    expect(s.durationS).toBe(1800);
    expect(s.brakingTimeS).toBe(4);
  });
  it("segments and splits", () => {
    const seg = segmentComparison(recs, 500, [240, 260]);
    expect(seg[0].plannedW).toBe(240);
    const sp = splitTimes(recs, [900, 4500]);
    expect(sp[0]).toBeCloseTo(100, 6);
  });
});

describe("exports", () => {
  const recs = ride(120, (i) => 200 + i);
  const s = summarize(recs, 250, 20000);
  it("GPX has power, hr and cadence", () => {
    const g = toGpx(recs, "Test & ride");
    expect(g).toContain("<power>200</power>");
    expect(g).toContain("<gpxtpx:hr>140</gpxtpx:hr>");
    expect(g).toContain("Test &amp; ride");
  });
  it("TCX has watts", () => expect(toTcx(recs, s)).toContain("<ns3:Watts>319</ns3:Watts>"));
  it("FIT decodes with records and developer fields", () => {
    const bytes = toFit(recs, s);
    const stream = Stream.fromByteArray(Array.from(bytes));
    expect(Decoder.isFIT(stream)).toBe(true);
    const dec = new Decoder(stream);
    expect(dec.checkIntegrity()).toBe(true);
    const { messages, errors } = dec.read();
    expect(errors).toHaveLength(0);
    expect(messages.recordMesgs!).toHaveLength(120);
    expect(messages.recordMesgs![10].power).toBe(210);
    expect(messages.sessionMesgs![0].normalizedPower).toBeGreaterThan(200);
    const dev = messages.recordMesgs![0].developerFields;
    expect(dev).toBeDefined();
    expect(Object.values(dev as Record<string, number>).map((v) => Math.round(v * 100) / 100)).toEqual([3, 1.2, 0.8, 1.2]);
  });
});
