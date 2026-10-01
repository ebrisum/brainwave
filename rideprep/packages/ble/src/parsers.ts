/** Flag-driven parsers for the Bluetooth SIG GATT characteristics we use. All values little-endian. */

class Reader {
  o = 0;
  constructor(private dv: DataView) {}
  get remaining() { return this.dv.byteLength - this.o; }
  u8() { const v = this.dv.getUint8(this.o); this.o += 1; return v; }
  u16() { const v = this.dv.getUint16(this.o, true); this.o += 2; return v; }
  s16() { const v = this.dv.getInt16(this.o, true); this.o += 2; return v; }
  u24() { const v = this.dv.getUint16(this.o, true) | (this.dv.getUint8(this.o + 2) << 16); this.o += 3; return v; }
  u32() { const v = this.dv.getUint32(this.o, true); this.o += 4; return v; }
  skip(n: number) { this.o += n; }
}

export const toDataView = (bytes: ArrayLike<number>): DataView => new DataView(Uint8Array.from(bytes).buffer);

export interface IndoorBikeData {
  speedKmh?: number;
  avgSpeedKmh?: number;
  cadenceRpm?: number;
  avgCadenceRpm?: number;
  totalDistanceM?: number;
  resistanceLevel?: number;
  powerW?: number;
  avgPowerW?: number;
  totalEnergyKcal?: number;
  energyPerHourKcal?: number;
  energyPerMinuteKcal?: number;
  heartRateBpm?: number;
  mets?: number;
  elapsedTimeS?: number;
  remainingTimeS?: number;
}

/** FTMS Indoor Bike Data (0x2AD2). Bit 0 "More Data" is inverted: 0 ⇒ instantaneous speed present. */
export function parseIndoorBikeData(dv: DataView): IndoorBikeData {
  const r = new Reader(dv);
  const f = r.u16();
  const out: IndoorBikeData = {};
  if (!(f & 0x0001)) out.speedKmh = r.u16() / 100;
  if (f & 0x0002) out.avgSpeedKmh = r.u16() / 100;
  if (f & 0x0004) out.cadenceRpm = r.u16() / 2;
  if (f & 0x0008) out.avgCadenceRpm = r.u16() / 2;
  if (f & 0x0010) out.totalDistanceM = r.u24();
  if (f & 0x0020) out.resistanceLevel = r.s16();
  if (f & 0x0040) out.powerW = r.s16();
  if (f & 0x0080) out.avgPowerW = r.s16();
  if (f & 0x0100) {
    out.totalEnergyKcal = r.u16();
    out.energyPerHourKcal = r.u16();
    out.energyPerMinuteKcal = r.u8();
  }
  if (f & 0x0200) out.heartRateBpm = r.u8();
  if (f & 0x0400) out.mets = r.u8() / 10;
  if (f & 0x0800) out.elapsedTimeS = r.u16();
  if (f & 0x1000) out.remainingTimeS = r.u16();
  return out;
}

export interface RevolutionData {
  /** Cumulative revolutions (wraps). */
  revs: number;
  /** Last event time in seconds (wraps at 64 s for 1/1024, 32 s for 1/2048). */
  eventTime: number;
  /** Raw tick counter for wraparound maths. */
  eventTicks: number;
  ticksPerSecond: number;
  revBits: number;
}

export interface CyclingPowerMeasurement {
  powerW: number;
  pedalBalancePct?: number;
  accumulatedTorqueNm?: number;
  wheel?: RevolutionData;
  crank?: RevolutionData;
  accumulatedEnergyKj?: number;
}

/** Cycling Power Measurement (0x2A63). */
export function parseCyclingPower(dv: DataView): CyclingPowerMeasurement {
  const r = new Reader(dv);
  const f = r.u16();
  const out: CyclingPowerMeasurement = { powerW: r.s16() };
  if (f & 0x0001) out.pedalBalancePct = r.u8() / 2;
  if (f & 0x0004) out.accumulatedTorqueNm = r.u16() / 32;
  if (f & 0x0010) {
    const revs = r.u32();
    const t = r.u16();
    out.wheel = { revs, eventTicks: t, eventTime: t / 2048, ticksPerSecond: 2048, revBits: 32 };
  }
  if (f & 0x0020) {
    const revs = r.u16();
    const t = r.u16();
    out.crank = { revs, eventTicks: t, eventTime: t / 1024, ticksPerSecond: 1024, revBits: 16 };
  }
  if (f & 0x0040) r.skip(4); // extreme force magnitudes
  if (f & 0x0080) r.skip(4); // extreme torque magnitudes
  if (f & 0x0100) r.skip(3); // extreme angles
  if (f & 0x0200) r.skip(2); // top dead spot
  if (f & 0x0400) r.skip(2); // bottom dead spot
  if (f & 0x0800 && r.remaining >= 2) out.accumulatedEnergyKj = r.u16();
  return out;
}

export interface HeartRateMeasurement {
  bpm: number;
  contactDetected?: boolean;
  energyExpendedKj?: number;
  /** RR intervals in seconds. */
  rrIntervalsS: number[];
}

/** Heart Rate Measurement (0x2A37). */
export function parseHeartRate(dv: DataView): HeartRateMeasurement {
  const r = new Reader(dv);
  const f = r.u8();
  const bpm = f & 0x01 ? r.u16() : r.u8();
  const out: HeartRateMeasurement = { bpm, rrIntervalsS: [] };
  if (f & 0x04) out.contactDetected = !!(f & 0x02);
  if (f & 0x08) out.energyExpendedKj = r.u16();
  if (f & 0x10) while (r.remaining >= 2) out.rrIntervalsS.push(r.u16() / 1024);
  return out;
}

export interface CscMeasurement {
  wheel?: RevolutionData;
  crank?: RevolutionData;
}

/** CSC Measurement (0x2A5B). Wheel event time is 1/1024 s here (unlike CPS). */
export function parseCsc(dv: DataView): CscMeasurement {
  const r = new Reader(dv);
  const f = r.u8();
  const out: CscMeasurement = {};
  if (f & 0x01) {
    const revs = r.u32();
    const t = r.u16();
    out.wheel = { revs, eventTicks: t, eventTime: t / 1024, ticksPerSecond: 1024, revBits: 32 };
  }
  if (f & 0x02) {
    const revs = r.u16();
    const t = r.u16();
    out.crank = { revs, eventTicks: t, eventTime: t / 1024, ticksPerSecond: 1024, revBits: 16 };
  }
  return out;
}

/**
 * Turns successive cumulative revolution readings into a rate (rpm), handling counter and timer wraparound.
 * Repeated readings with no new event keep the last rate until `staleS` of wall time passes, then report 0.
 */
export class RevolutionRate {
  private last?: RevolutionData;
  private lastRpm = 0;
  private lastEventWall = -Infinity;
  constructor(private staleS = 3) {}

  update(d: RevolutionData, wallTimeS: number): number {
    const prev = this.last;
    this.last = d;
    if (!prev) {
      this.lastEventWall = wallTimeS;
      return this.lastRpm;
    }
    const revMod = d.revBits === 32 ? 2 ** 32 : 65536;
    const dRevs = (d.revs - prev.revs + revMod) % revMod;
    const dTicks = (d.eventTicks - prev.eventTicks + 65536) % 65536;
    if (dRevs > 0 && dTicks > 0) {
      this.lastRpm = (dRevs / (dTicks / d.ticksPerSecond)) * 60;
      this.lastEventWall = wallTimeS;
    } else if (wallTimeS - this.lastEventWall > this.staleS) {
      this.lastRpm = 0;
    }
    return this.lastRpm;
  }
}
