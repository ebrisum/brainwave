/** Encoders for sensor notifications — used by the virtual device adapter and the BLE emulator. */

export function encodeIndoorBikeData(d: { speedKmh: number; cadenceRpm?: number; powerW?: number; heartRateBpm?: number }): Uint8Array {
  let flags = 0; // bit0 = 0 → speed present
  const parts: number[] = [];
  const u16 = (v: number) => parts.push(v & 0xff, (v >> 8) & 0xff);
  u16(Math.round(d.speedKmh * 100));
  if (d.cadenceRpm !== undefined) { flags |= 0x0004; u16(Math.round(d.cadenceRpm * 2)); }
  if (d.powerW !== undefined) { flags |= 0x0040; u16(Math.round(d.powerW) & 0xffff); }
  if (d.heartRateBpm !== undefined) { flags |= 0x0200; parts.push(d.heartRateBpm & 0xff); }
  return Uint8Array.of(flags & 0xff, flags >> 8, ...parts);
}

export function encodeCyclingPower(d: { powerW: number; crankRevs?: number; crankEventTicks?: number }): Uint8Array {
  const crank = d.crankRevs !== undefined;
  const flags = crank ? 0x0020 : 0;
  const p = Math.round(d.powerW) & 0xffff;
  const out = [flags & 0xff, flags >> 8, p & 0xff, p >> 8];
  if (crank) {
    const r = d.crankRevs! & 0xffff;
    const t = (d.crankEventTicks ?? 0) & 0xffff;
    out.push(r & 0xff, r >> 8, t & 0xff, t >> 8);
  }
  return Uint8Array.from(out);
}

export function encodeHeartRate(bpm: number, rrS: number[] = []): Uint8Array {
  const flags = rrS.length ? 0x10 : 0;
  const out = [flags, bpm & 0xff];
  for (const rr of rrS) {
    const v = Math.round(rr * 1024) & 0xffff;
    out.push(v & 0xff, v >> 8);
  }
  return Uint8Array.from(out);
}
