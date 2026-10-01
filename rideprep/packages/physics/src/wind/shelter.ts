/** Near-field obstacle shelter (WIND_MODEL.md §3). */

export type ObstacleKind = "building" | "wall" | "conifer" | "forest_edge" | "deciduous" | "hedge" | "single_tree";

export interface ObstacleHit {
  /** Distance upwind from the route sample to the obstacle, m. */
  distanceM: number;
  /** Obstacle height, m. */
  heightM: number;
  /** Optical porosity 0..1. */
  porosity: number;
}

/** Leaf-on/leaf-off aware porosity. `leafOn` is decided from date and latitude by `isLeafOn`. */
export function porosityFor(kind: ObstacleKind, leafOn: boolean): number {
  switch (kind) {
    case "building":
    case "wall": return 0.0;
    case "conifer":
    case "forest_edge": return 0.3;
    case "deciduous": return leafOn ? 0.3 : 0.6;
    case "hedge": return 0.4;
    case "single_tree": return leafOn ? 0.5 : 0.7;
  }
}

/**
 * Leaf-on season for deciduous trees. Western Europe (~52°N) is leaf-off roughly Nov–Mar;
 * the season shortens ~1 week per 2° further from the equator. Southern hemisphere is shifted by 6 months.
 */
export function isLeafOn(month: number, day: number, latDeg: number): boolean {
  let doy = Math.round((month - 1) * 30.44 + day);
  if (latDeg < 0) doy = (doy + 182) % 365;
  const absLat = Math.abs(latDeg);
  const shift = Math.round(((absLat - 52) / 2) * 7); // days later leaf-out / earlier leaf-fall
  if (absLat < 23) return true;
  const leafOut = 105 + shift; // ~15 Apr at 52°
  const leafFall = 305 - shift; // ~1 Nov at 52°
  return doy >= leafOut && doy < leafFall;
}

/** Relative wind speed R behind one obstacle (1 = no shelter). */
export function shelterFactorForHit(hit: ObstacleHit): number {
  const { distanceM: x, heightM: H, porosity: phi } = hit;
  if (H <= 0 || x < 0) return 1;
  const uMin = 0.15 + 0.85 * phi;
  const L = (12 + 20 * phi) * H;
  const xh = x / H;
  let f: number;
  if (xh < 3) f = 0.7 + 0.1 * xh;
  else if (x < L) f = 1 - (x - 3 * H) / (L - 3 * H);
  else f = 0;
  f = Math.min(Math.max(f, 0), 1);
  return 1 - (1 - uMin) * f;
}

/** Strongest shelter of all hits wins. */
export function shelterFactor(hits: ObstacleHit[]): number {
  let r = 1;
  for (const h of hits) r = Math.min(r, shelterFactorForHit(h));
  return r;
}

/** Maximum ray length for shelter casting: min(25·H_max, 400 m). */
export function shelterRayLength(hMax: number): number {
  return Math.min(25 * hMax, 400);
}
