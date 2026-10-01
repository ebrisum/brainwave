/** NOAA solar position algorithm (simplified, accurate to ~0.1°). Returns elevation and azimuth (deg, clockwise from north). */
export function solarPosition(date: Date, latDeg: number, lonDeg: number): { elevationDeg: number; azimuthDeg: number } {
  const rad = Math.PI / 180;
  const jd = date.getTime() / 86400000 + 2440587.5;
  const t = (jd - 2451545) / 36525;
  const L0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360;
  const M = 357.52911 + t * (35999.05029 - 0.0001537 * t);
  const e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t);
  const C = Math.sin(M * rad) * (1.914602 - t * (0.004817 + 0.000014 * t)) + Math.sin(2 * M * rad) * (0.019993 - 0.000101 * t) + Math.sin(3 * M * rad) * 0.000289;
  const trueLong = L0 + C;
  const omega = 125.04 - 1934.136 * t;
  const lambda = trueLong - 0.00569 - 0.00478 * Math.sin(omega * rad);
  const eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60;
  const eps = eps0 + 0.00256 * Math.cos(omega * rad);
  const decl = Math.asin(Math.sin(eps * rad) * Math.sin(lambda * rad)) / rad;
  const y = Math.tan((eps / 2) * rad) ** 2;
  const eqTime = 4 / rad * (y * Math.sin(2 * L0 * rad) - 2 * e * Math.sin(M * rad) + 4 * e * y * Math.sin(M * rad) * Math.cos(2 * L0 * rad)
    - 0.5 * y * y * Math.sin(4 * L0 * rad) - 1.25 * e * e * Math.sin(2 * M * rad));
  const minutes = date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60;
  const tst = (minutes + eqTime + 4 * lonDeg + 1440) % 1440;
  const ha = tst / 4 < 0 ? tst / 4 + 180 : tst / 4 - 180;
  const cosZen = Math.sin(latDeg * rad) * Math.sin(decl * rad) + Math.cos(latDeg * rad) * Math.cos(decl * rad) * Math.cos(ha * rad);
  const zen = Math.acos(Math.min(Math.max(cosZen, -1), 1)) / rad;
  const azDen = Math.cos(latDeg * rad) * Math.sin(zen * rad);
  let az: number;
  if (Math.abs(azDen) > 1e-6) {
    const azRad = (Math.sin(latDeg * rad) * Math.cos(zen * rad) - Math.sin(decl * rad)) / azDen;
    az = 180 - Math.acos(Math.min(Math.max(azRad, -1), 1)) / rad;
    if (ha > 0) az = -az;
  } else {
    az = latDeg > 0 ? 180 : 0;
  }
  return { elevationDeg: 90 - zen, azimuthDeg: (az + 360) % 360 };
}
