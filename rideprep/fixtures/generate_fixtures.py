#!/usr/bin/env python3
"""Generate the synthetic test fixtures (see docs/DECISIONS.md: no routing/OSM access at build time).

Each fixture is a GPX file placed in real geography with a synthetic but plausible elevation profile, plus a
`<name>.features.geojson` sidecar with OSM-tagged features (roads with surface/width/bridge, tree rows, hedges,
forests, water, buildings with heights). The `geojson` OSM provider reads the sidecar, so every pipeline stage
can run offline and deterministically. Replace these with real recorded GPX files when network access allows.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pyproj import Transformer

HERE = Path(__file__).parent


def local_tf(lat0: float, lon0: float):
    proj = f"+proj=tmerc +lat_0={lat0} +lon_0={lon0} +k=1 +x_0=0 +y_0=0 +ellps=WGS84 +units=m"
    fwd = Transformer.from_crs("EPSG:4326", proj, always_xy=True)
    inv = Transformer.from_crs(proj, "EPSG:4326", always_xy=True)
    return fwd, inv


@dataclass
class Path2D:
    """A route built from straight segments and circular arcs, in local metres (x east, y north)."""
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0  # compass radians
    pts: list = field(default_factory=list)
    tags: list = field(default_factory=list)  # per point dict of road tags
    step: float = 2.0

    def __post_init__(self):
        self.pts.append((self.x, self.y))
        self.tags.append({})

    def straight(self, length: float, **tags):
        n = max(1, int(length / self.step))
        for _ in range(n):
            self.x += math.sin(self.heading) * length / n
            self.y += math.cos(self.heading) * length / n
            self.pts.append((self.x, self.y))
            self.tags.append(tags)
        return self

    def arc(self, radius: float, angle_deg: float, **tags):
        """Turn by angle (positive = right/clockwise) on a circle of the given radius."""
        ang = math.radians(angle_deg)
        length = abs(ang) * radius
        n = max(2, int(length / self.step))
        for _ in range(n):
            self.heading += ang / n
            self.x += math.sin(self.heading) * length / n
            self.y += math.cos(self.heading) * length / n
            self.pts.append((self.x, self.y))
            self.tags.append(tags)
        return self

    def turn_to(self, heading_deg: float, radius: float, **tags):
        d = (heading_deg - math.degrees(self.heading) + 540) % 360 - 180
        return self.arc(radius, d, **tags)

    def length(self) -> float:
        return sum(math.dist(a, b) for a, b in zip(self.pts, self.pts[1:]))


class Features:
    def __init__(self, inv):
        self.inv = inv
        self.items = []

    def _ll(self, coords):
        lon, lat = self.inv.transform([c[0] for c in coords], [c[1] for c in coords])
        return [[round(a, 7), round(b, 7)] for a, b in zip(lon, lat)]

    def line(self, coords, **props):
        self.items.append({"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": self._ll(coords)}})

    def poly(self, coords, **props):
        ring = list(coords) + [coords[0]]
        self.items.append({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [self._ll(ring)]}})

    def point(self, xy, **props):
        self.items.append({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": self._ll([xy])[0]}})

    def rect(self, cx, cy, w, h, rot=0.0, **props):
        c, s = math.cos(rot), math.sin(rot)
        pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
        self.poly([(cx + px * c - py * s, cy + px * s + py * c) for px, py in pts], **props)

    def roads_from_path(self, p: Path2D):
        """Emit OSM-like highway ways along the route, split where tags change."""
        cur, start = None, 0
        for i, t in enumerate(p.tags + [None]):
            key = json.dumps(t, sort_keys=True) if t is not None else None
            if key != cur:
                if cur is not None and i - start >= 2:
                    self.line(p.pts[max(start - 1, 0):i], **json.loads(cur))
                cur, start = key, i


def offset_line(pts, d):
    """Offset a polyline by d metres (positive = right of travel)."""
    out = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1
        out.append((pts[i][0] + dy / n * d, pts[i][1] - dx / n * d))
    return out


def write_gpx(name, p: Path2D, elev_fn, inv, waypoints, start: datetime, speed=8.0, jitter=1.5, seed=1):
    rng = random.Random(seed)
    xs, ys, zs = [], [], []
    acc = 0.0
    last = None
    for (x, y) in p.pts:
        if last is not None:
            acc += math.dist(last, (x, y))
        last = (x, y)
        xs.append(x); ys.append(y); zs.append(elev_fn(x, y, acc))
    # Thin to ~10 m GPS spacing and add jitter
    out = []
    acc = 0.0
    lastk = None
    for i in range(len(xs)):
        if lastk is not None:
            acc += math.dist((xs[i], ys[i]), (xs[i - 1], ys[i - 1]))
        if lastk is None or acc - lastk >= 10 or i == len(xs) - 1:
            out.append((xs[i] + rng.gauss(0, jitter), ys[i] + rng.gauss(0, jitter), zs[i] + rng.gauss(0, 0.4), acc))
            lastk = acc
    lon, lat = inv.transform([o[0] for o in out], [o[1] for o in out])
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<gpx version="1.1" creator="rideprep-fixtures" xmlns="http://www.topografix.com/GPX/1/1">',
             f"  <metadata><name>{name}</name></metadata>"]
    for wp in waypoints:
        wlon, wlat = inv.transform(wp[0], wp[1])
        lines.append(f'  <wpt lat="{wlat:.7f}" lon="{wlon:.7f}"><name>{wp[2]}</name><type>{wp[3]}</type></wpt>')
    lines.append(f"  <trk><name>{name}</name><trkseg>")
    for (o, la, lo) in zip(out, lat, lon):
        t = start + timedelta(seconds=o[3] / speed)
        lines.append(f'    <trkpt lat="{la:.7f}" lon="{lo:.7f}"><ele>{o[2]:.1f}</ele><time>{t.strftime("%Y-%m-%dT%H:%M:%SZ")}</time></trkpt>')
    lines.append("  </trkseg></trk>\n</gpx>\n")
    (HERE / f"{name}.gpx").write_text("\n".join(lines))
    return len(out)


def write_features(name, feats: Features):
    (HERE / f"{name}.features.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats.items}, separators=(",", ":")))


# ---------------------------------------------------------------------------------------------------------------
def polder():
    """60 km polder/coastal loop near Lelystad: dike along the Markermeer, open polder roads, poplar rows, farms."""
    name = "polder_coastal_60k"
    lat0, lon0 = 52.44, 5.62
    _, inv = local_tf(lat0, lon0)
    f = Features(inv)
    asphalt = dict(highway="secondary", surface="asphalt", smoothness="good", width=6)
    dike = dict(highway="cycleway", surface="asphalt", smoothness="good", width=3)
    p = Path2D(heading=0.0)
    p.straight(6000, **asphalt)                 # north along polder road with tree row
    p.turn_to(90, 25, **asphalt).straight(5000, **asphalt)
    p.turn_to(0, 30, **asphalt).straight(4000, **asphalt)
    p.turn_to(270, 25, **asphalt).straight(8500, **asphalt)   # west to the dike
    p.turn_to(180, 40, **dike)
    dike_start = len(p.pts)
    p.straight(15000, **dike)                    # south on the dike, water to the west
    dike_end = len(p.pts)
    p.turn_to(90, 30, **asphalt).straight(9000, **asphalt)
    p.turn_to(0, 25, **dict(asphalt, surface="paving_stones", smoothness="intermediate"))
    p.straight(2500, **dict(asphalt, surface="paving_stones", smoothness="intermediate"))
    p.straight(2500, **asphalt)
    p.turn_to(270, 20, **asphalt)
    # back to start
    p.straight(abs(p.x) - 30, **asphalt)
    p.turn_to(0, 30, **asphalt).straight(max(0.0, -p.y - 30), **asphalt)
    f.roads_from_path(p)
    # Water west of the dike (Markermeer), the dike itself raises the road
    dike_pts = p.pts[dike_start:dike_end]
    west = min(x for x, _ in dike_pts)
    ys = [y for _, y in dike_pts]
    f.poly([(west - 30, min(ys) - 2000), (west - 9000, min(ys) - 2000), (west - 9000, max(ys) + 2000), (west - 30, max(ys) + 2000)], natural="water")
    # Poplar tree row along the first road (west side, 12 m off), and along the eastward road (north side)
    f.line(offset_line(p.pts[5:2900], -12), natural="tree_row", leaf_type="broadleaved", height=22, species="poplar")
    i0 = next(i for i, (x, y) in enumerate(p.pts) if y > 5900)
    f.line(offset_line(p.pts[i0 + 60:i0 + 2400], -10), natural="tree_row", leaf_type="broadleaved", height=18)
    # Hedges and a small wood
    f.line(offset_line(p.pts[dike_end + 50:dike_end + 2000], 8), barrier="hedge", height=2.5)
    cx, cy = p.pts[dike_end + 3000]
    f.poly([(cx + 40, cy - 600), (cx + 900, cy - 600), (cx + 900, cy - 60), (cx + 40, cy - 60)], landuse="forest", leaf_type="mixed", height=20)
    # Farms (houses + barns) every ~2 km along polder roads
    rng = random.Random(7)
    for k in range(0, len(p.pts), 1100):
        if dike_start <= k <= dike_end:
            continue
        x, y = p.pts[k]
        side = rng.choice([-1, 1])
        ox, oy = offset_line(p.pts[max(k - 1, 0):k + 2], side * 40)[1 if k > 0 else 0]
        f.rect(ox, oy, 12, 9, rng.random(), building="house", height=8, **{"roof:shape": "gabled"})
        f.rect(ox + 25 * side, oy + 10, 30, 18, rng.random(), building="barn", height=10)
        f.line([(ox - 20, oy - 20), (ox + 20, oy - 25)], natural="tree_row", leaf_type="broadleaved", height=14)
    # Land use: cropland everywhere in the polder (east of the dike)
    f.poly([(west, -3000), (25000, -3000), (25000, 20000), (west, 20000)], landuse="farmland")

    def elev(x, y, s):
        d = x - west
        if d < 60:
            return 4.5 - max(0.0, d - 6) * 0.08   # dike crown ~+4.5 m
        return -4.2 + 0.3 * math.sin(s / 3000)
    wps = [(p.pts[0][0], p.pts[0][1], "Start/Finish", "start"),
           (dike_pts[len(dike_pts) // 2][0], dike_pts[len(dike_pts) // 2][1], "Aid station dike", "aid_station")]
    n = write_gpx(name, p, elev, inv, wps, datetime(2025, 9, 21, 7, 40, tzinfo=timezone.utc), seed=11)
    write_features(name, f)
    return name, p.length(), n


def forest_climb():
    """40 km Ardennes-style route: valley roads, a 6 km forested climb, hairpin descent."""
    name = "forest_climb_40k"
    lat0, lon0 = 50.43, 5.93
    _, inv = local_tf(lat0, lon0)
    f = Features(inv)
    road = dict(highway="tertiary", surface="asphalt", smoothness="good", width=5)
    forest_rd = dict(highway="unclassified", surface="asphalt", smoothness="intermediate", width=4)
    gravel = dict(highway="track", surface="fine_gravel", width=3)
    p = Path2D(heading=math.radians(60))
    p.straight(4500, **road).arc(400, 30, **road).straight(5000, **road)
    climb_start = p.length()
    p.arc(300, -40, **forest_rd).straight(1500, **forest_rd).arc(200, 60, **forest_rd).straight(2000, **forest_rd)
    p.arc(250, -50, **forest_rd).straight(2200, **forest_rd)
    climb_end = p.length()
    p.straight(2500, **gravel)
    descent_start = p.length()
    # Technical descent: hairpins
    p.turn_to(200, 60, **forest_rd).straight(500, **forest_rd)
    for k in range(5):
        p.arc(14, 175 if k % 2 == 0 else -175, **forest_rd).straight(350, **forest_rd)
    p.arc(25, 60, **forest_rd).straight(1500, **forest_rd)
    descent_end = p.length()
    p.turn_to(240, 120, **road).straight(4000, **road).arc(300, 40, **road).straight(3000, **road)
    p.turn_to(math.degrees(math.atan2(-p.x, -p.y)) % 360, 200, **road)
    p.straight(max(0.0, math.hypot(p.x, p.y) - 50), **road)
    f.roads_from_path(p)
    # Forest around the climb and descent
    xs = [x for x, _ in p.pts]
    ys = [y for _, y in p.pts]
    acc = [0.0]
    for a, b in zip(p.pts, p.pts[1:]):
        acc.append(acc[-1] + math.dist(a, b))
    idx = [i for i, s in enumerate(acc) if climb_start - 200 <= s <= descent_end]
    fx = [xs[i] for i in idx]
    fy = [ys[i] for i in idx]
    f.poly([(min(fx) - 800, min(fy) - 800), (max(fx) + 800, min(fy) - 800), (max(fx) + 800, max(fy) + 800), (min(fx) - 800, max(fy) + 800)],
           landuse="forest", leaf_type="needleleaved", height=24)
    # Village at the start with houses along the road
    for k in range(10, 900, 45):
        x, y = p.pts[k]
        for side in (-1, 1):
            ox, oy = offset_line(p.pts[k - 1:k + 2], side * 14)[1]
            f.rect(ox, oy, 10, 9, p.heading, building="house", height=9, **{"roof:shape": "gabled"})
    f.poly([(xs[0] - 600, ys[0] - 600), (xs[0] + 2000, ys[0] - 600), (xs[0] + 2000, ys[0] + 1500), (xs[0] - 600, ys[0] + 1500)], landuse="residential")
    f.poly([(min(xs) - 3000, min(ys) - 3000), (max(xs) + 3000, min(ys) - 3000), (max(xs) + 3000, max(ys) + 3000), (min(xs) - 3000, max(ys) + 3000)], landuse="meadow")
    total = acc[-1]

    def elev(x, y, s):
        base = 260 + 20 * math.sin(s / 2500)
        if s < climb_start:
            return base
        if s < climb_end:
            return base + (s - climb_start) * 0.062 + 8 * math.sin((s - climb_start) / 400)
        top = 260 + 20 * math.sin(climb_end / 2500) + (climb_end - climb_start) * 0.062
        if s < descent_start:
            return top + 5 * math.sin((s - climb_end) / 300)
        if s < descent_end:
            frac = (s - descent_start) / (descent_end - descent_start)
            return top - frac * (top - (260 + 20 * math.sin(descent_end / 2500)))
        return 260 + 20 * math.sin(s / 2500)
    wps = [(xs[0], ys[0], "Start", "start"), (xs[idx[len(idx) // 3]], ys[idx[len(idx) // 3]], "Feed zone", "aid_station")]
    n = write_gpx(name, p, elev, inv, wps, datetime(2025, 6, 15, 9, 0, tzinfo=timezone.utc), speed=7, seed=12)
    write_features(name, f)
    return name, total, n


def urban():
    """15 km dense urban loop in Ghent-like grid: cobbles, a canal bridge, continuous building rows."""
    name = "urban_cobbles_15k"
    lat0, lon0 = 51.05, 3.72
    _, inv = local_tf(lat0, lon0)
    f = Features(inv)
    street = dict(highway="residential", surface="asphalt", smoothness="good", width=7)
    cobble = dict(highway="residential", surface="sett", smoothness="bad", width=6)
    bridge = dict(highway="secondary", surface="asphalt", smoothness="good", width=8, bridge="yes", layer=1)
    p = Path2D(heading=0.0)
    lap = []
    p.straight(800, **street).turn_to(90, 12, **street).straight(600, **cobble).turn_to(0, 10, **cobble).straight(500, **cobble)
    p.turn_to(90, 15, **street).straight(400, **street)
    b0 = len(p.pts)
    p.straight(80, **bridge)
    b1 = len(p.pts)
    p.straight(1200, **street).turn_to(180, 12, **street).straight(2000, **street).turn_to(270, 12, **street)
    p.straight(max(0.0, p.x - 12), **cobble).turn_to(0, 10, **street)
    p.straight(max(0.0, -p.y - 10), **street)
    p.turn_to(0, 8, **street)
    lap_len = p.length()
    # Second lap: repeat the same geometry (lap detection)
    tags = p.tags[1:]
    pts = p.pts[1:]
    for (x, y), t in zip(pts, tags):
        p.pts.append((x, y))
        p.tags.append(t)
    f.roads_from_path(p)
    # Canal under the bridge
    bx, by = p.pts[(b0 + b1) // 2]
    f.poly([(bx - 15, by - 3000), (bx + 15, by - 3000), (bx + 15, by + 3000), (bx - 15, by + 3000)], waterway="canal", natural="water")
    # Continuous building rows along every street except the bridge
    rng = random.Random(3)
    first_lap = len(pts) + 1
    for k in range(4, first_lap - 4, 6):
        if b0 - 8 <= k <= b1 + 8:
            continue
        a, b = p.pts[k - 1], p.pts[k + 1]
        h = math.atan2(b[0] - a[0], b[1] - a[1])
        for side in (-1, 1):
            ox, oy = offset_line(p.pts[k - 1:k + 2], side * 13)[1]
            f.rect(ox, oy, 8, 12, -h, building="apartments" if rng.random() < 0.6 else "house",
                   height=round(rng.uniform(9, 18), 1), **{"building:levels": rng.randint(3, 6)})
    f.point(p.pts[200], natural="tree", height=12)
    f.poly([(-2000, -2000), (3000, -2000), (3000, 2500), (-2000, 2500)], landuse="residential")

    def elev(x, y, s):
        return 8 + 1.5 * math.sin(s / 700)
    wps = [(p.pts[0][0], p.pts[0][1], "Start/Finish", "start")]
    n = write_gpx(name, p, elev, inv, wps, datetime(2025, 3, 2, 10, 0, tzinfo=timezone.utc), speed=7, jitter=2.5, seed=13)
    write_features(name, f)
    return name, p.length(), n


def perf_180k():
    """180 km rolling loop for performance tests: a mix of farmland, villages, woods and a few climbs."""
    name = "perf_180k"
    lat0, lon0 = 50.85, 5.85
    _, inv = local_tf(lat0, lon0)
    f = Features(inv)
    rng = random.Random(21)
    road = dict(highway="secondary", surface="asphalt", smoothness="good", width=6)
    minor = dict(highway="unclassified", surface="asphalt", smoothness="intermediate", width=4)
    p = Path2D(heading=math.radians(80), step=4.0)
    target = 180000.0
    while p.length() < target * 0.9:
        t = road if rng.random() < 0.6 else minor
        p.straight(rng.uniform(800, 3500), **t)
        # steer gently so the loop closes: bias heading by position angle
        ang = math.degrees(math.atan2(p.x, p.y))
        desired = (ang + 100) % 360
        diff = (desired - math.degrees(p.heading) + 540) % 360 - 180
        p.arc(rng.uniform(40, 400), max(-90, min(90, diff * 0.5 + rng.uniform(-30, 30))), **t)
    p.turn_to(math.degrees(math.atan2(-p.x, -p.y)) % 360, 150, **road)
    p.straight(max(0.0, math.hypot(p.x, p.y) - 60), **road)
    f.roads_from_path(p)
    xs = [x for x, _ in p.pts]
    ys = [y for _, y in p.pts]
    for k in range(0, len(p.pts), 600):
        x, y = p.pts[k]
        r = rng.random()
        if r < 0.25:
            f.line(offset_line(p.pts[k:k + 300], rng.choice([-1, 1]) * rng.uniform(8, 20)), natural="tree_row", leaf_type="broadleaved", height=rng.uniform(12, 22))
        elif r < 0.4:
            f.rect(x + rng.uniform(-600, 600), y + rng.uniform(-600, 600), rng.uniform(300, 900), rng.uniform(300, 900), rng.random(), landuse="forest", leaf_type="broadleaved", height=22)
        elif r < 0.55:
            for j in range(0, 120, 12):
                q = p.pts[min(k + j, len(p.pts) - 2)]
                for side in (-1, 1):
                    ox, oy = offset_line(p.pts[min(k + j, len(p.pts) - 3):min(k + j, len(p.pts) - 3) + 3], side * 15)[1]
                    f.rect(ox, oy, 10, 9, rng.random(), building="house", height=rng.uniform(6, 11))
        elif r < 0.65:
            f.line(offset_line(p.pts[k:k + 200], 6), barrier="hedge", height=2)
    f.poly([(min(xs) - 3000, min(ys) - 3000), (max(xs) + 3000, min(ys) - 3000), (max(xs) + 3000, max(ys) + 3000), (min(xs) - 3000, max(ys) + 3000)], landuse="farmland")

    def elev(x, y, s):
        return 120 + 45 * math.sin(x / 7000) * math.cos(y / 9000) + 20 * math.sin(s / 1800) + 35 * max(0.0, math.sin(s / 15000)) ** 3
    n = write_gpx(name, p, elev, inv, [(xs[0], ys[0], "Start", "start")], datetime(2025, 8, 10, 8, 0, tzinfo=timezone.utc), seed=14)
    write_features(name, f)
    return name, p.length(), n


if __name__ == "__main__":
    for gen in (polder, forest_climb, urban, perf_180k):
        nm, length, n = gen()
        print(f"{nm}: {length / 1000:.1f} km, {n} trackpoints")
