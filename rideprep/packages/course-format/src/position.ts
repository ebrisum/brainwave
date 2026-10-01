import { CourseProfile } from "@rideprep/physics";

export interface RoutePose { x: number; y: number; z: number; headingRad: number }

/**
 * Rider pose at route distance s: linear interpolation of x/y/z between the two bracketing 5 m samples, heading from
 * the interpolated unit vectors. This exact function is mirrored in C++ (apps/unreal RidePrepCourseMath.h) so every
 * renderer puts the rider in the same place (cross-renderer test, spec §16.8).
 */
export function poseAt(c: CourseProfile, s: number): RoutePose {
  const last = c.count - 1;
  const fi = Math.min(Math.max(s / c.spacingM, 0), last);
  const i = Math.min(Math.floor(fi), last - 1);
  const t = fi - i;
  const j = i + 1;
  const hx = Math.sin(c.headingRad[i]) * (1 - t) + Math.sin(c.headingRad[j]) * t;
  const hy = Math.cos(c.headingRad[i]) * (1 - t) + Math.cos(c.headingRad[j]) * t;
  return {
    x: c.x[i] + (c.x[j] - c.x[i]) * t,
    y: c.y[i] + (c.y[j] - c.y[i]) * t,
    z: c.z[i] + (c.z[j] - c.z[i]) * t,
    headingRad: (Math.atan2(hx, hy) + 2 * Math.PI) % (2 * Math.PI),
  };
}

/** ENU metres → Unreal centimetres (left-handed, Z-up). Mirrors gpx2course/coords.py. */
export const enuToUe = (x: number, y: number, z: number): [number, number, number] => [x * 100, -y * 100, z * 100];
export const ueToEnu = (X: number, Y: number, Z: number): [number, number, number] => [X / 100, -Y / 100, Z / 100];

/** ENU → three.js world (Y-up, right-handed): (x, z, −y). Same as the glTF convention used by baked chunks. */
export const enuToThree = (x: number, y: number, z: number): [number, number, number] => [x, z, -y];
