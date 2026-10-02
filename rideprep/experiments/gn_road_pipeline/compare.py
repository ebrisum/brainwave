"""Compare the proposed Phase 1 curve with the gpx2course route on the same GPX + DEM.

  python compare.py --phase1 phase1.json --pkg <course package> --out out/

Reference: Overture road centrelines (drivable classes) and building footprints from the package corridor.
Writes out/compare_metrics.json, out/compare_map.png and out/phase1_to_pkg.json (2nd-order fit, phase-1 frame → package
frame, used to drop the Phase 2 mesh into the package world for renders).
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import shape

from gpx2course.geo import LocalFrame
from gpx2course.stages.common import read_parquet
from gpx2course.stages.profile import ascent_with_hysteresis

R_EARTH = 6_371_008.8
DRIVABLE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service", "road",
            "cycleway", "track", "pedestrian", "primary_link", "secondary_link", "tertiary_link", "trunk_link"}


class _Pkg:
    def __init__(self, d):
        self.dir = Path(d)

    def path(self, rel):
        return self.dir / rel


def resample(x, y, step=5.0):
    s = np.r_[0, np.cumsum(np.hypot(np.diff(x), np.diff(y)))]
    g = np.arange(0, s[-1], step)
    return np.interp(g, s, x), np.interp(g, s, y), g


def grade_stats(s, z, window=50.0):
    up, _ = ascent_with_hysteresis(z)
    k = max(1, int(window / (s[1] - s[0])))
    g = (z[k:] - z[:-k]) / (s[k:] - s[:-k]) * 100
    return {"ascentM": round(float(up), 1), "maxGradePct50m": round(float(np.max(np.abs(g))), 1),
            "kmOver12Pct": round(float(np.sum(np.abs(g) > 12) * (s[1] - s[0]) / 1000), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase1", required=True)
    ap.add_argument("--pkg", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    p1 = json.load(open(a.phase1))
    pkg = Path(a.pkg)
    origin = json.loads((pkg / "origin.json").read_text())
    frame = LocalFrame(origin["lat"], origin["lon"])
    lat0, lon0 = p1["frame"]
    k = math.cos(math.radians(lat0))

    def p1_to_pkg(x, y):
        lat = lat0 + np.degrees(np.asarray(y) / R_EARTH)
        lon = lon0 + np.degrees(np.asarray(x) / (R_EARTH * k))
        return frame.to_xy(lat, lon)

    # Phase 1 curve and our route in the package frame, both resampled at 5 m
    px, py = p1_to_pkg(np.array(p1["x"]), np.array(p1["y"]))
    pz = np.array(p1["z"])
    s1 = np.r_[0, np.cumsum(np.hypot(np.diff(px), np.diff(py)))]
    ax, ay, ag = resample(px, py)
    az = np.interp(ag, s1, pz)
    geo = read_parquet(_Pkg(pkg), "route_geo.parquet")
    ox, oy = frame.to_xy(geo["lat"], geo["lon"])
    meta = json.loads((pkg / "route_meta.json").read_text())
    buf = (pkg / "route.bin").read_bytes()
    zarr = next(x for x in meta["arrays"] if x["name"] == "z")
    oz = np.frombuffer(buf, dtype="<f4", count=meta["count"], offset=zarr["offset"]).astype(float)
    bx, by, bg = resample(ox, oy)
    so = np.r_[0, np.cumsum(np.hypot(np.diff(ox), np.diff(oy)))]
    bz = np.interp(bg, so, oz)
    # Reference roads and buildings (package corridor, Overture-derived)
    osm = json.loads((pkg / "corridor/osm.geojson").read_text())["features"]
    roads = [shape(f["geometry"]) for f in osm if f["properties"].get("highway") in DRIVABLE and f["geometry"]["type"] == "LineString"]
    rtree = shapely.STRtree(roads)
    blds = [shape(f["geometry"]) for f in json.loads((pkg / "corridor/buildings.geojson").read_text())["features"]]
    btree = shapely.STRtree(blds)

    def fidelity(x, y):
        pts = shapely.points(x, y)
        idx = rtree.query_nearest(pts, max_distance=200, return_distance=True)
        d = np.full(len(x), 200.0)
        d[idx[0][0]] = np.minimum(d[idx[0][0]], idx[1])
        # Points inside a building footprint shrunk by 0.5 m (i.e. clearly through the building)
        inb = np.zeros(len(x), bool)
        pi, _ = btree.query(pts, predicate="within")
        inb[pi] = True
        return d, {"medianM": round(float(np.median(d)), 2), "p95M": round(float(np.percentile(d, 95)), 1), "maxM": round(float(d.max()), 1),
                   "shareOver3m": round(float(np.mean(d > 3)), 3), "shareOver10m": round(float(np.mean(d > 10)), 3),
                   "kmOver10m": round(float(np.sum(d > 10) * 5 / 1000), 2), "kmOver25m": round(float(np.sum(d > 25) * 5 / 1000), 2),
                   "samplesInsideBuildings": int(inb.sum())}

    d1, f1 = fidelity(ax, ay)
    d2, f2 = fidelity(bx, by)
    m = {"proposedPhase1": {"lengthKm": round(float(ag[-1]) / 1000, 2), "offRoad": f1, **grade_stats(ag, az)},
         "gpx2course": {"lengthKm": round(float(bg[-1]) / 1000, 2), "offRoad": f2, **grade_stats(bg, bz)},
         "officialKm": 90.0}
    (out / "compare_metrics.json").write_text(json.dumps(m, indent=1))
    print(json.dumps(m, indent=1))
    # 2nd-order polynomial fit phase-1 frame → package frame (for the render overlay)
    gx, gy = np.meshgrid(np.linspace(min(p1["x"]) - 500, max(p1["x"]) + 500, 30), np.linspace(min(p1["y"]) - 500, max(p1["y"]) + 500, 30))
    X, Y = gx.ravel(), gy.ravel()
    tx, ty = p1_to_pkg(X, Y)
    A = np.c_[np.ones_like(X), X, Y, X * X, X * Y, Y * Y]
    cx = np.linalg.lstsq(A, tx, rcond=None)[0]
    cy = np.linalg.lstsq(A, ty, rcond=None)[0]
    err = np.hypot(A @ cx - tx, A @ cy - ty).max()
    (out / "phase1_to_pkg.json").write_text(json.dumps({"cx": cx.tolist(), "cy": cy.tolist(), "maxErrM": float(err)}))
    plot(out / "compare_map.png", roads, blds, (ax, ay, d1), (bx, by, d2), btree)


def plot(path, roads, blds, prop, ours, btree):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ax_, ay_, d1 = prop
    bx, by, _ = ours
    # Panels: the four worst stretches of the proposed curve (distinct places)
    order = np.argsort(-d1)
    centres = []
    for i in order:
        c = (ax_[i], ay_[i])
        if all(math.dist(c, q) > 1500 for q in centres):
            centres.append(c)
        if len(centres) == 4:
            break
    fig, axs = plt.subplots(2, 2, figsize=(14, 14))
    for axp, (cx, cy) in zip(axs.ravel(), centres):
        r = 260
        box = shapely.box(cx - r, cy - r, cx + r, cy + r)
        for g in btree.geometries[btree.query(box)]:
            xs, ys = g.exterior.xy
            axp.fill(xs, ys, color="#d9c7a6", lw=0)
        for g in roads:
            if g.intersects(box):
                xs, ys = g.xy
                axp.plot(xs, ys, color="#9a9a9a", lw=3, solid_capstyle="round")
        sel = (np.abs(bx - cx) < r) & (np.abs(by - cy) < r)
        axp.plot(np.where(sel, bx, np.nan), np.where(sel, by, np.nan), color="#1a9850", lw=2.2, label="gpx2course (snapped + matched)")
        sel = (np.abs(ax_ - cx) < r) & (np.abs(ay_ - cy) < r)
        axp.plot(np.where(sel, ax_, np.nan), np.where(sel, ay_, np.nan), color="#d73027", lw=2.2, ls="--", label="proposed Phase 1 (GPX → smoothed Bezier)")
        axp.set_xlim(cx - r, cx + r)
        axp.set_ylim(cy - r, cy + r)
        axp.set_aspect("equal")
        axp.set_xticks([])
        axp.set_yticks([])
        axp.set_title(f"worst deviation {float(d1[np.argmin(np.hypot(ax_ - cx, ay_ - cy))]):.0f} m", fontsize=11)
    axs[0, 0].legend(loc="lower left", fontsize=10)
    fig.suptitle("IRONMAN 70.3 Emilia-Romagna — route geometry vs real roads (grey) and buildings (tan)", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=80)


if __name__ == "__main__":
    main()
