/** Minimal course representation the physics needs (decoded from route.bin by @rideprep/course-format). */
export interface CourseProfile {
  spacingM: number;
  count: number;
  s: Float32Array;
  x: Float32Array;
  y: Float32Array;
  z: Float32Array;
  gradePct: Float32Array;
  /** Compass bearing of travel, radians clockwise from north. */
  headingRad: Float32Array;
  radiusM: Float32Array;
  crrMultiplier: Float32Array;
}

export interface CourseSample {
  s: number;
  x: number;
  y: number;
  z: number;
  grade: number;
  headingRad: number;
  radiusM: number;
  crrMultiplier: number;
}

export function courseLength(c: CourseProfile): number {
  return c.s[c.count - 1];
}

function lerpAngle(a: number, b: number, t: number): number {
  let d = b - a;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return a + d * t;
}

/** Linear interpolation of the profile at distance s (clamped to the course). */
export function sampleCourse(c: CourseProfile, s: number, out?: CourseSample): CourseSample {
  const o = out ?? ({} as CourseSample);
  const fi = Math.min(Math.max(s / c.spacingM, 0), c.count - 1);
  const i = Math.min(Math.floor(fi), c.count - 2);
  const t = fi - i;
  const j = i + 1;
  o.s = s;
  o.x = c.x[i] + (c.x[j] - c.x[i]) * t;
  o.y = c.y[i] + (c.y[j] - c.y[i]) * t;
  o.z = c.z[i] + (c.z[j] - c.z[i]) * t;
  o.grade = (c.gradePct[i] + (c.gradePct[j] - c.gradePct[i]) * t) / 100;
  o.headingRad = lerpAngle(c.headingRad[i], c.headingRad[j], t);
  o.radiusM = t < 0.5 ? c.radiusM[i] : c.radiusM[j];
  o.crrMultiplier = c.crrMultiplier[i] + (c.crrMultiplier[j] - c.crrMultiplier[i]) * t;
  return o;
}

/** Average grade (fraction) over [s0, s1]. */
export function averageGrade(c: CourseProfile, s0: number, s1: number): number {
  const a = sampleCourse(c, s0).z;
  const b = sampleCourse(c, s1).z;
  return s1 > s0 ? (b - a) / (s1 - s0) : 0;
}

/** Build a course from arrays of elevation etc. at uniform spacing (helper for tests and synthetic courses). */
export function makeCourse(opts: {
  spacingM: number;
  z: number[];
  headingRad?: number[];
  radiusM?: number[];
  crrMultiplier?: number[];
}): CourseProfile {
  const n = opts.z.length;
  const s = new Float32Array(n);
  const x = new Float32Array(n);
  const y = new Float32Array(n);
  const z = Float32Array.from(opts.z);
  const gradePct = new Float32Array(n);
  const heading = Float32Array.from(opts.headingRad ?? new Array(n).fill(0));
  const radius = Float32Array.from(opts.radiusM ?? new Array(n).fill(Infinity));
  const crr = Float32Array.from(opts.crrMultiplier ?? new Array(n).fill(1));
  for (let i = 0; i < n; i++) {
    s[i] = i * opts.spacingM;
    if (i > 0) {
      const hd = heading[i - 1];
      x[i] = x[i - 1] + Math.sin(hd) * opts.spacingM;
      y[i] = y[i - 1] + Math.cos(hd) * opts.spacingM;
    }
    const a = Math.max(i - 2, 0);
    const b = Math.min(i + 2, n - 1);
    gradePct[i] = b > a ? ((z[b] - z[a]) / ((b - a) * opts.spacingM)) * 100 : 0;
  }
  return { spacingM: opts.spacingM, count: n, s, x, y, z, gradePct, headingRad: heading, radiusM: radius, crrMultiplier: crr };
}
