/** FTMS Fitness Machine Control Point (0x2AD9) encoders and response parsing. */

export const OP = {
  requestControl: 0x00,
  reset: 0x01,
  setTargetResistance: 0x04,
  setTargetPower: 0x05,
  startOrResume: 0x07,
  stopOrPause: 0x08,
  setIndoorBikeSimulation: 0x11,
  response: 0x80,
} as const;

export const RESULT = {
  success: 0x01,
  notSupported: 0x02,
  invalidParameter: 0x03,
  failed: 0x04,
  controlNotPermitted: 0x05,
} as const;

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

export const encodeRequestControl = (): Uint8Array => Uint8Array.of(OP.requestControl);
export const encodeReset = (): Uint8Array => Uint8Array.of(OP.reset);
export const encodeStartOrResume = (): Uint8Array => Uint8Array.of(OP.startOrResume);

/** Set Target Power (ERG), sint16 in 1 W. */
export function encodeSetTargetPower(watts: number): Uint8Array {
  const b = new Uint8Array(3);
  const dv = new DataView(b.buffer);
  b[0] = OP.setTargetPower;
  dv.setInt16(1, clamp(Math.round(watts), -32768, 32767), true);
  return b;
}

/** Set Target Resistance Level, uint8 with 0.1 resolution (FTMS v1.0). */
export function encodeSetTargetResistance(level: number): Uint8Array {
  return Uint8Array.of(OP.setTargetResistance, clamp(Math.round(level * 10), 0, 255));
}

export interface SimulationParams {
  /** Wind speed, m/s, positive = headwind. */
  windSpeedMs: number;
  /** Grade in percent. */
  gradePct: number;
  /** Rolling resistance coefficient (dimensionless). */
  crr: number;
  /** Wind resistance coefficient Cw = CdA·ρ, kg/m. */
  cwKgM: number;
}

/** Set Indoor Bike Simulation Parameters: wind sint16 0.001 m/s, grade sint16 0.01 %, Crr uint8 0.0001, Cw uint8 0.01 kg/m. */
export function encodeSimulation(p: SimulationParams): Uint8Array {
  const b = new Uint8Array(7);
  const dv = new DataView(b.buffer);
  b[0] = OP.setIndoorBikeSimulation;
  dv.setInt16(1, clamp(Math.round(p.windSpeedMs * 1000), -32768, 32767), true);
  dv.setInt16(3, clamp(Math.round(p.gradePct * 100), -32768, 32767), true);
  b[5] = clamp(Math.round(p.crr * 10000), 0, 255);
  b[6] = clamp(Math.round(p.cwKgM * 100), 0, 255);
  return b;
}

/** FTMS wind resistance coefficient from air density and CdA. */
export const windResistanceCoefficient = (rho: number, cda: number): number => rho * cda;

export interface ControlPointResponse {
  requestOp: number;
  result: number;
}

export function parseControlPointResponse(dv: DataView): ControlPointResponse | null {
  if (dv.byteLength < 3 || dv.getUint8(0) !== OP.response) return null;
  return { requestOp: dv.getUint8(1), result: dv.getUint8(2) };
}

export interface SupportedRange {
  min: number;
  max: number;
  increment: number;
}

/** Supported Power Range (0x2AD8): sint16 min, sint16 max, uint16 increment (W). */
export function parseSupportedPowerRange(dv: DataView): SupportedRange {
  return { min: dv.getInt16(0, true), max: dv.getInt16(2, true), increment: dv.getUint16(4, true) };
}

/** Supported Resistance Level Range (0x2AD6): sint16 ×0.1 min, max, uint16 ×0.1 increment. */
export function parseSupportedResistanceRange(dv: DataView): SupportedRange {
  return { min: dv.getInt16(0, true) / 10, max: dv.getInt16(2, true) / 10, increment: dv.getUint16(4, true) / 10 };
}

/** FTMS Feature (0x2ACC): two uint32 bitfields. */
export function parseFtmsFeature(dv: DataView): { machine: number; targets: number; supportsSimulation: boolean; supportsPower: boolean; supportsResistance: boolean } {
  const machine = dv.getUint32(0, true);
  const targets = dv.getUint32(4, true);
  return {
    machine, targets,
    supportsResistance: !!(targets & (1 << 2)),
    supportsPower: !!(targets & (1 << 3)),
    supportsSimulation: !!(targets & (1 << 13)),
  };
}
