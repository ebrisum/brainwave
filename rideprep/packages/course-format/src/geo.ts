/**
 * Local frame ↔ WGS84 for course packages: transverse Mercator centred on the origin (k0 = 1, WGS84), matching
 * gpx2course.geo.LocalFrame (PROJ +proj=tmerc). Snyder (1987) series — sub-millimetre within ±200 km of the origin.
 */
const A = 6378137.0;
const F = 1 / 298.257223563;
const E2 = F * (2 - F);
const EP2 = E2 / (1 - E2);
const RAD = Math.PI / 180;

function meridionalArc(phi: number): number {
  const e4 = E2 * E2, e6 = e4 * E2;
  return A * ((1 - E2 / 4 - (3 * e4) / 64 - (5 * e6) / 256) * phi - ((3 * E2) / 8 + (3 * e4) / 32 + (45 * e6) / 1024) * Math.sin(2 * phi)
    + ((15 * e4) / 256 + (45 * e6) / 1024) * Math.sin(4 * phi) - ((35 * e6) / 3072) * Math.sin(6 * phi));
}

/** Local x (east), y (north) metres → [lat, lon] degrees. */
export function localToLatLon(lat0: number, lon0: number, x: number, y: number): [number, number] {
  const M = meridionalArc(lat0 * RAD) + y;
  const mu = M / (A * (1 - E2 / 4 - (3 * E2 * E2) / 64 - (5 * E2 ** 3) / 256));
  const e1 = (1 - Math.sqrt(1 - E2)) / (1 + Math.sqrt(1 - E2));
  const phi1 = mu + ((3 * e1) / 2 - (27 * e1 ** 3) / 32) * Math.sin(2 * mu) + ((21 * e1 ** 2) / 16 - (55 * e1 ** 4) / 32) * Math.sin(4 * mu)
    + ((151 * e1 ** 3) / 96) * Math.sin(6 * mu) + ((1097 * e1 ** 4) / 512) * Math.sin(8 * mu);
  const s1 = Math.sin(phi1), c1 = Math.cos(phi1), t1 = Math.tan(phi1);
  const C1 = EP2 * c1 * c1;
  const T1 = t1 * t1;
  const N1 = A / Math.sqrt(1 - E2 * s1 * s1);
  const R1 = (A * (1 - E2)) / Math.pow(1 - E2 * s1 * s1, 1.5);
  const D = x / N1;
  const lat = phi1 - ((N1 * t1) / R1) * (D * D / 2 - ((5 + 3 * T1 + 10 * C1 - 4 * C1 * C1 - 9 * EP2) * D ** 4) / 24
    + ((61 + 90 * T1 + 298 * C1 + 45 * T1 * T1 - 252 * EP2 - 3 * C1 * C1) * D ** 6) / 720);
  const lon = (D - ((1 + 2 * T1 + C1) * D ** 3) / 6 + ((5 - 2 * C1 + 28 * T1 - 3 * C1 * C1 + 8 * EP2 + 24 * T1 * T1) * D ** 5) / 120) / c1;
  return [lat / RAD, lon0 + lon / RAD];
}
