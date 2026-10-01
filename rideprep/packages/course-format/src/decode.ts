import { CourseProfile, WindLayers, WIND_LAYERS, WindLayerName } from "@rideprep/physics";
import { Manifest } from "./types";

/** Decode route.bin into the physics course profile (+ surface/width extras). */
export function decodeRoute(buf: ArrayBuffer, m: Manifest): CourseProfile & { surfaceCode: Uint8Array; roadWidthM: Uint8Array } {
  const n = m.route.count;
  const get = (name: string) => {
    const a = m.route.arrays.find((x) => x.name === name);
    if (!a) throw new Error(`route.bin has no array ${name}`);
    return a;
  };
  const f32 = (name: string) => {
    const a = get(name);
    // Copy so the result is aligned regardless of the offset
    return new Float32Array(buf.slice(a.offset, a.offset + 4 * n));
  };
  const u8 = (name: string) => {
    const a = get(name);
    return new Uint8Array(buf.slice(a.offset, a.offset + n));
  };
  if (!littleEndian()) throw new Error("big-endian hosts are not supported");
  return {
    spacingM: m.route.sampleSpacingM, count: n, s: f32("s"), x: f32("x"), y: f32("y"), z: f32("z"), gradePct: f32("gradePct"),
    headingRad: f32("headingRad"), radiusM: f32("radiusM"), crrMultiplier: f32("crrMultiplier"), surfaceCode: u8("surfaceCode"),
    roadWidthM: u8("roadWidthM"),
  };
}

function littleEndian(): boolean {
  return new Uint8Array(new Uint16Array([1]).buffer)[0] === 1;
}

export function decodeWind(buf: ArrayBuffer, m: Manifest): WindLayers {
  const layers = m.wind.layers.filter((l): l is WindLayerName => (WIND_LAYERS as readonly string[]).includes(l));
  return new WindLayers(new Uint8Array(buf), m.wind.count, m.wind.sampleSpacingM, m.wind.directionBins, layers);
}

export interface Instances {
  count: number;
  x: Float32Array; y: Float32Array; z: Float32Array; rot: Float32Array; scale: Float32Array; height: Float32Array;
  category: Uint8Array; species: Uint8Array; flags: Uint16Array;
}

/** instances.bin: 28-byte records (6×float32, uint8 category, uint8 species, uint16 flags), little-endian. */
export function decodeInstances(buf: ArrayBuffer, m: Manifest): Instances {
  const n = m.instances.count;
  const rb = m.instances.recordBytes;
  if (buf.byteLength !== n * rb) throw new Error("instances.bin size mismatch");
  const dv = new DataView(buf);
  const out: Instances = {
    count: n, x: new Float32Array(n), y: new Float32Array(n), z: new Float32Array(n), rot: new Float32Array(n), scale: new Float32Array(n),
    height: new Float32Array(n), category: new Uint8Array(n), species: new Uint8Array(n), flags: new Uint16Array(n),
  };
  for (let i = 0; i < n; i++) {
    const o = i * rb;
    out.x[i] = dv.getFloat32(o, true);
    out.y[i] = dv.getFloat32(o + 4, true);
    out.z[i] = dv.getFloat32(o + 8, true);
    out.rot[i] = dv.getFloat32(o + 12, true);
    out.scale[i] = dv.getFloat32(o + 16, true);
    out.height[i] = dv.getFloat32(o + 20, true);
    out.category[i] = dv.getUint8(o + 24);
    out.species[i] = dv.getUint8(o + 25);
    out.flags[i] = dv.getUint16(o + 26, true);
  }
  return out;
}

/** Terrarium RGB(A) pixels → heights (m): (R·256 + G + B/256) − 32768. */
export function decodeTerrarium(rgba: Uint8ClampedArray | Uint8Array, channels = 4): Float32Array {
  const n = rgba.length / channels;
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const o = i * channels;
    out[i] = rgba[o] * 256 + rgba[o + 1] + rgba[o + 2] / 256 - 32768;
  }
  return out;
}
