/**
 * Globe ↔ course-frame alignment for real-world 3D tiles (Google Photorealistic 3D Tiles, Cesium).
 *
 * Tiles live in ECEF (WGS84, ellipsoidal heights); the course lives in a local transverse-Mercator frame with
 * orthometric heights. We build an affine map ECEF → course frame anchored at a point A near the rider:
 * exact at A, and accurate to millimetres horizontally within a few km (the tangent plane drops away from the
 * flat course frame by d²/2R — 8 cm at 1 km — so renderers re-anchor as the rider moves).
 * The vertical offset (geoid undulation and data biases) is calibrated by raycasting the tiles at the road.
 */
import { localToLatLon } from "./geo";

const A = 6378137.0;
const F = 1 / 298.257223563;
const E2 = F * (2 - F);
const RAD = Math.PI / 180;

export type Vec3 = [number, number, number];

export function geodeticToEcef(latDeg: number, lonDeg: number, h: number): Vec3 {
  const la = latDeg * RAD, lo = lonDeg * RAD;
  const s = Math.sin(la), c = Math.cos(la);
  const N = A / Math.sqrt(1 - E2 * s * s);
  return [(N + h) * c * Math.cos(lo), (N + h) * c * Math.sin(lo), (N * (1 - E2) + h) * s];
}

/** East, north, up unit vectors (ECEF) at a geodetic position. */
export function enuBasis(latDeg: number, lonDeg: number): { e: Vec3; n: Vec3; u: Vec3 } {
  const la = latDeg * RAD, lo = lonDeg * RAD;
  const sl = Math.sin(la), cl = Math.cos(la), so = Math.sin(lo), co = Math.cos(lo);
  return { e: [-so, co, 0], n: [-sl * co, -sl * so, cl], u: [cl * co, cl * so, sl] };
}

const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];

export interface GlobeAnchor {
  /** Course-frame anchor (x east, y north, z orthometric up), metres. */
  local: Vec3;
  lat: number;
  lon: number;
  /** Assumed ellipsoidal height of the anchor (z + geoid undulation guess). */
  hEllipsoidal: number;
  /** 3×3 row-major linear part mapping ECEF → course frame (x, y, z). */
  linear: number[];
  /** Translation so that course = linear·ecef + translation. */
  translation: Vec3;
}

/** Affine ECEF → course frame anchored at local point (x, y, z). */
export function globeAnchor(originLat: number, originLon: number, x: number, y: number, z: number, geoidUndulation = 0): GlobeAnchor {
  const [lat, lon] = localToLatLon(originLat, originLon, x, y);
  const h = z + geoidUndulation;
  const PA = geodeticToEcef(lat, lon, h);
  const { e, n, u } = enuBasis(lat, lon);
  // Jacobian of course-frame (x, y) → local ENU at A, by finite differences of the exact inverse projection
  const step = 10;
  const toEnu = (p: Vec3): [number, number] => { const d = sub(p, PA); return [dot(d, e), dot(d, n)]; };
  const [lx, ly] = localToLatLon(originLat, originLon, x + step, y);
  const [mx, my] = localToLatLon(originLat, originLon, x, y + step);
  const jx = toEnu(geodeticToEcef(lx, ly, h)).map((v) => v / step);
  const jy = toEnu(geodeticToEcef(mx, my, h)).map((v) => v / step);
  // J = [[jx0, jy0], [jx1, jy1]] maps (dx, dy) → (de, dn); invert it
  const det = jx[0] * jy[1] - jy[0] * jx[1];
  const k = [jy[1] / det, -jy[0] / det, -jx[1] / det, jx[0] / det]; // (de, dn) → (dx, dy)
  // course = (x, y, z) + [K·(E·d, N·d), U·d] with d = P − PA
  const row0: Vec3 = [k[0] * e[0] + k[1] * n[0], k[0] * e[1] + k[1] * n[1], k[0] * e[2] + k[1] * n[2]];
  const row1: Vec3 = [k[2] * e[0] + k[3] * n[0], k[2] * e[1] + k[3] * n[1], k[2] * e[2] + k[3] * n[2]];
  const row2: Vec3 = u;
  const linear = [...row0, ...row1, ...row2];
  const translation: Vec3 = [x - dot(row0, PA), y - dot(row1, PA), z - dot(row2, PA)];
  return { local: [x, y, z], lat, lon, hEllipsoidal: h, linear, translation };
}

export function applyAnchor(a: GlobeAnchor, p: Vec3): Vec3 {
  const L = a.linear;
  return [L[0] * p[0] + L[1] * p[1] + L[2] * p[2] + a.translation[0], L[3] * p[0] + L[4] * p[1] + L[5] * p[2] + a.translation[1],
    L[6] * p[0] + L[7] * p[1] + L[8] * p[2] + a.translation[2]];
}
