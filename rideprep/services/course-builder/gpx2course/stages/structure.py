"""Stage 5 — structure: climbs, technical corners, laps, POIs and surface runs → segments.json."""
from __future__ import annotations

import math

import numpy as np
import shapely
from scipy.spatial import cKDTree

from ..pipeline import BuildContext
from .common import load_route

G = 9.80665
A_LAT_DRY = 0.55 * G
A_LAT_WET = 0.35 * G


def detect_climbs(s: np.ndarray, z: np.ndarray, grade: np.ndarray, min_len=500.0, min_grade=3.0, dip_len=200.0, dip_loss=5.0) -> list[dict]:
    n = len(s)
    climbs = []
    i = 0
    while i < n - 1:
        # start at a local low point where the road starts rising
        if z[i + 1] <= z[i]:
            i += 1
            continue
        start = i
        peak = i
        j = i + 1
        while j < n:
            if z[j] > z[peak]:
                peak = j
            # end the climb if we lost ≥ dip_loss below the peak, or have been below the peak for ≥ dip_len
            if z[peak] - z[j] >= dip_loss or (s[j] - s[peak] >= dip_len and z[j] <= z[peak]):
                break
            j += 1
        a, b = start, peak
        # trim flat lead-in / run-out (50 m pieces under 2 %)
        step = max(1, int(round(50 / (s[1] - s[0]))))
        while b - a > step and (z[a + step] - z[a]) / (s[a + step] - s[a]) * 100 < 2.0:
            a += step
        while b - a > step and (z[b] - z[b - step]) / (s[b] - s[b - step]) * 100 < 2.0:
            b -= step
        length = s[b] - s[a]
        if length >= min_len:
            avg = (z[b] - z[a]) / length * 100
            if avg >= min_grade:
                seg_grade = grade[a:b + 1]
                win = max(1, int(round(100 / (s[1] - s[0]))))
                g100 = (z[a + win:b + 1] - z[a:b + 1 - win]) / (s[a + win:b + 1] - s[a:b + 1 - win]) * 100 if b - a > win else seg_grade
                diff = float(np.sum(np.clip(seg_grade, 0, None) ** 2) * (s[1] - s[0]) / 1000.0)
                climbs.append({"sStart": round(float(s[a]), 1), "sEnd": round(float(s[b]), 1), "lengthM": round(float(length), 1),
                               "avgGradePct": round(float(avg), 2), "maxGradePct": round(float(np.max(g100)), 1),
                               "gainM": round(float(z[b] - z[a]), 1), "difficulty": round(diff, 1)})
        i = max(peak, i + 1)
    for k, c in enumerate(climbs):
        c["id"] = k
        c["category"] = climb_category(c["difficulty"])
    return climbs


def climb_category(difficulty: float) -> str:
    """Rough category from Σ(grade%²·km)."""
    for lim, cat in ((800, "HC"), (400, "1"), (200, "2"), (100, "3"), (40, "4")):
        if difficulty >= lim:
            return cat
    return "uncat"


def detect_corners(s, x, y, heading, radius, max_radius=30.0, v_limit_kmh=35.0) -> list[dict]:
    sp = s[1] - s[0]
    v_lim = np.sqrt(A_LAT_DRY * np.minimum(radius, 1e6))
    tech = (radius < max_radius) | (v_lim < v_limit_kmh / 3.6)
    out = []
    n = len(s)
    i = 0
    while i < n:
        if not tech[i]:
            i += 1
            continue
        j = i
        while j < n and (tech[j] or (j + 3 < n and tech[j:j + 4].any())):
            j += 1
        a, b = i, min(j, n - 1)
        apex = a + int(np.argmin(radius[a:b + 1]))
        k = max(1, int(round(20 / sp)))
        h0 = heading[max(a - k, 0)]
        h1 = heading[min(b + k, n - 1)]
        turn = math.degrees((h1 - h0 + math.pi) % (2 * math.pi) - math.pi)
        r = float(radius[apex])
        if abs(turn) >= 20:
            out.append({"s": round(float(s[apex]), 1), "sStart": round(float(s[a]), 1), "sEnd": round(float(s[b]), 1), "radiusM": round(r, 1),
                        "turnDeg": round(turn, 0), "direction": "right" if turn > 0 else "left",
                        "vMaxDryKmh": round(math.sqrt(A_LAT_DRY * r) * 3.6, 1), "vMaxWetKmh": round(math.sqrt(A_LAT_WET * r) * 3.6, 1),
                        "hairpin": abs(turn) >= 135})
        i = j + 1
    for k, c in enumerate(out):
        c["id"] = k
    return out


def detect_laps(s, x, y, heading, tol=15.0, min_overlap=0.8, min_lap=1000.0) -> list[dict]:
    """Find a repeated lap: the route returns to its start with the same heading and the next lap overlaps ≥80 %."""
    n = len(s)
    L = s[-1]
    sp = s[1] - s[0]
    d0 = np.hypot(x - x[0], y - y[0])
    dh = np.abs((heading - heading[0] + np.pi) % (2 * np.pi) - np.pi)
    cand = np.nonzero((d0 < tol) & (dh < math.radians(30)) & (s > min_lap) & (s < L - min_lap * 0.5))[0]
    if len(cand) == 0:
        return [{"index": 0, "sStart": 0.0, "sEnd": round(float(L), 1)}]
    # first contiguous group of candidates
    first = cand[0]
    grp = cand[cand < first + int(50 / sp)]
    lap_end = int(grp[np.argmin(d0[grp])])
    lap_len = s[lap_end]
    tree = cKDTree(np.c_[x[:lap_end + 1], y[:lap_end + 1]])
    starts = [0]
    k = lap_end
    while k < n - int(min_lap / sp) * 0.5:
        e = min(n - 1, k + lap_end)
        d, _ = tree.query(np.c_[x[k:e + 1], y[k:e + 1]])
        if (d < tol).mean() < min_overlap:
            break
        starts.append(k)
        k = e
    if len(starts) == 1:
        return [{"index": 0, "sStart": 0.0, "sEnd": round(float(L), 1)}]
    laps = []
    for idx, a in enumerate(starts):
        b = starts[idx + 1] if idx + 1 < len(starts) else n - 1
        laps.append({"index": idx, "sStart": round(float(s[a]), 1), "sEnd": round(float(s[b]), 1)})
    return laps


def project_to_route(tree: cKDTree, s: np.ndarray, x: float, y: float, max_dist: float, last: bool = False):
    """Route distance of a point. On loops/laps several passes qualify: take the first (or last, for finishes)."""
    d, i = tree.query([x, y])
    if d > max_dist:
        return None, float(d)
    cand = tree.query_ball_point([x, y], max(30.0, d + 10.0))
    ss = s[cand]
    return float(ss.max() if last else ss.min()), float(d)


def run(ctx: BuildContext) -> list[str]:
    r = load_route(ctx)
    s, x, y, z, grade, heading, radius = r["s"], r["x"], r["y"], r["z"], r["gradePct"], r["headingRad"], r["radiusM"]
    climbs = detect_climbs(s, z, grade)
    corners = detect_corners(s, x, y, heading, radius)
    laps = detect_laps(s, x, y, heading)
    tree = cKDTree(np.c_[x, y])
    pois = []
    for p in ctx.read_json("pois_raw.json"):
        px, py = ctx.frame.to_xy(p["lat"], p["lon"])
        sp_, d = project_to_route(tree, s, float(px), float(py), 200, last=_poi_type(p) == "finish")
        if sp_ is None:
            ctx.warn(f"waypoint '{p.get('name')}' is {d:.0f} m from the route; ignored", code="poi_far")
            continue
        pois.append({"s": round(sp_, 1), "name": p.get("name", ""), "type": _poi_type(p), "source": "gpx"})
    # Structures from the route attributes (bridges/tunnels)
    for st in ctx.read_json("route_meta.json").get("structures", []):
        pois.append({"s": st["sStart"], "sEnd": st["sEnd"], "name": st["kind"].title(), "type": st["kind"], "source": "osm"})
    # OSM features near the route: level crossings, roundabouts, town entries
    osm = ctx.read_json("corridor/osm.geojson")["features"] if ctx.path("corridor/osm.geojson").exists() else []
    route_line = shapely.LineString(np.c_[x, y])
    for f in osm:
        tags = f["properties"]
        g = shapely.geometry.shape(f["geometry"])
        if tags.get("railway") == "level_crossing" or tags.get("junction") == "roundabout":
            if route_line.distance(g) < 15:
                sp_ = float(route_line.project(g.centroid if g.geom_type != "Point" else g))
                kind = "level_crossing" if tags.get("railway") else "roundabout"
                pois.append({"s": round(sp_, 1), "name": kind.replace("_", " ").title(), "type": kind, "source": "osm"})
        elif tags.get("landuse") == "residential" and g.geom_type in ("Polygon", "MultiPolygon"):
            inside = shapely.contains_xy(g, x, y)
            entries = np.nonzero(inside[1:] & ~inside[:-1])[0] + 1
            if inside[0]:
                entries = np.r_[0, entries]
            for e in entries:
                pois.append({"s": round(float(s[e]), 1), "name": tags.get("name", "Town"), "type": "town_entry", "source": "osm"})
    pois.sort(key=lambda p: p["s"])
    # km markers
    km = [{"s": float(k * 1000), "label": f"{k} km"} for k in range(1, int(s[-1] // 1000) + 1)]
    # Surface runs
    surf = r["surface"]
    runs_ = []
    a = 0
    for i in range(1, len(s) + 1):
        if i == len(s) or surf[i] != surf[a]:
            runs_.append({"sStart": round(float(s[a]), 1), "sEnd": round(float(s[min(i, len(s) - 1)]), 1), "surface": str(surf[a] or "unknown"),
                          "crrMultiplier": round(float(r["crrMultiplier"][a]), 3)})
            a = i
    # Merge tiny runs (<30 m) into neighbours for readability
    merged = []
    for run_ in runs_:
        if merged and (run_["sEnd"] - run_["sStart"] < 30 or merged[-1]["surface"] == run_["surface"]):
            merged[-1]["sEnd"] = run_["sEnd"]
        else:
            merged.append(run_)
    seg = {"climbs": climbs, "corners": corners, "laps": laps, "pois": pois, "surfaceRuns": merged, "kmMarkers": km}
    ctx.write_json("segments.json", seg)
    meta = ctx.read_json("route_meta.json")
    meta["stats"]["laps"] = len(laps)
    ctx.write_json("route_meta.json", meta)
    return ["segments.json"]


def _poi_type(p: dict) -> str:
    t = (p.get("type") or p.get("sym") or "").lower()
    name = (p.get("name") or "").lower()
    for key, kind in (("aid", "aid_station"), ("feed", "aid_station"), ("water", "aid_station"), ("transition", "transition"),
                      ("turn", "turnaround"), ("start", "start"), ("finish", "finish")):
        if key in t or key in name:
            return kind
    return "waypoint"
