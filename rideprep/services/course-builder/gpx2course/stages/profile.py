"""Stage 3 — profile: geometry, elevation (DEM, bridges, smoothing), grade, curvature, surfaces → route.bin."""
from __future__ import annotations

import hashlib

import numpy as np

from .. import PIPELINE_VERSION
from ..geo import cumulative_distance, gaussian_smooth, heading_compass, resample_uniform, turning_radius
from ..pipeline import BuildContext, stable_json
from ..surfaces import SURFACE_CODES, classify, width_m
from .common import encode_route_bin, read_parquet, sample_dem, write_parquet


def ascent_with_hysteresis(z: np.ndarray, threshold: float = 1.0) -> tuple[float, float]:
    up = down = 0.0
    ref = z[0]
    for v in z[1:]:
        d = v - ref
        if d >= threshold:
            up += d
            ref = v
        elif d <= -threshold:
            down -= d
            ref = v
    return up, down


def runs(mask: np.ndarray):
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            yield i, j
            i = j
        else:
            i += 1


def run(ctx: BuildContext) -> list[str]:
    t = ctx.config.tunables
    sp = t.sample_spacing_m
    m = read_parquet(ctx, "route_matched.parquet")
    matched = m["matched"].astype(bool)
    # Geometry: snapped where matched, smoothed raw elsewhere; blend lightly to avoid kinks at transitions
    raw_x = gaussian_smooth(m["x"], sp, 8.0)
    raw_y = gaussian_smooth(m["y"], sp, 8.0)
    gx = np.where(matched & np.isfinite(m["snap_x"]), m["snap_x"], raw_x)
    gy = np.where(matched & np.isfinite(m["snap_y"]), m["snap_y"], raw_y)
    gx = gaussian_smooth(gx, sp, 3.0)
    gy = gaussian_smooth(gy, sp, 3.0)
    s_old = m["s"]
    s_new = cumulative_distance(gx, gy)
    grid, (x, y, s_ref) = resample_uniform(s_new, sp, gx, gy, s_old)
    n = len(grid)
    # Attributes: nearest original sample
    src_idx = np.clip(np.round(s_ref / sp).astype(int), 0, len(s_old) - 1)
    attr = {k: m[k][src_idx] for k in ("highway", "surface", "smoothness", "width", "lanes", "bridge", "tunnel", "name", "cycleway", "way_id", "matched")}
    lat, lon = ctx.frame.to_latlon(x, y)

    # ---- Elevation ------------------------------------------------------------------------------------
    z_raw, src, providers = sample_dem(ctx, lat, lon)
    # The input file's own elevation is used along the track (not by spatial nearest neighbour, which mixes passes
    # where a route crosses itself at different heights).
    z_track = np.interp(s_ref, s_old, m["ele"]) if np.isfinite(m["ele"]).sum() >= 2 else None
    for ui, p in enumerate(providers):
        if p.info.name == "gpx" and z_track is not None:
            z_raw = np.where(src == ui, z_track, z_raw)
    for e in sorted(ctx.cache.get("dem_errors", [])):
        ctx.warn(f"DEM provider unavailable — {e}", code="dem_unavailable")
    used = sorted(set(src.tolist()) - {-1})
    best_res = 1e9
    zones = []
    for ui in used:
        p = providers[ui]
        ctx.source(f"dem:{p.info.name}", p.info)
        share = float((src == ui).mean())
        zones.append({"provider": p.info.name, "share": round(share, 4), "resolution_m": p.info.resolution_m})
        best_res = min(best_res, p.info.resolution_m or 30.0)
    if not used:
        ctx.warn("No elevation source available; course treated as flat", code="no_elevation")
    if any(providers[u].info.resolution_m and providers[u].info.resolution_m >= 25 for u in used):
        ctx.warn("Low-resolution DEM (≥25 m) used on part of the course", code="low_res_dem")
    # Bridges and tunnels: interpolate between abutments
    bt = np.array([(b or "") not in ("", "no") for b in attr["bridge"]]) | np.array([(v or "") not in ("", "no") for v in attr["tunnel"]])
    z = z_raw.copy()
    structures = []
    for a, b in runs(bt):
        a0 = max(a - 2, 0)
        b0 = min(b + 1, n - 1)
        z[a0:b0 + 1] = np.linspace(z[a0], z[b0], b0 - a0 + 1)
        structures.append({"sStart": float(grid[a]), "sEnd": float(grid[min(b, n - 1)]), "kind": "bridge" if attr["bridge"][a] not in ("", "no") else "tunnel"})
    # Coarse DSMs (Copernicus GLO-30) include trees/buildings beside the road: a 50 m running median removes those
    # spikes before the Gaussian smoothing (docs/DECISIONS.md).
    dsm = np.array([providers[u].info.name == "copernicus" for u in src.clip(0)]) & (src >= 0) if used else np.zeros(n, bool)
    if dsm.any():
        from scipy.ndimage import median_filter
        zm = median_filter(z, size=max(3, int(round(50 / sp)) | 1), mode="nearest")
        z = np.where(dsm & ~bt, zm, z)
    sigma = 20.0 if best_res <= 2 else 40.0
    if used and all(providers[u].info.name == "gpx" for u in used):
        sigma = 20.0
    zs = gaussian_smooth(z, sp, sigma)
    # Grade over a centred 20 m window
    k = max(1, int(round(10 / sp)))
    idx = np.arange(n)
    a = np.clip(idx - k, 0, n - 1)
    b = np.clip(idx + k, 0, n - 1)
    grade = np.where(b > a, (zs[b] - zs[a]) / ((b - a) * sp) * 100, 0.0)
    over = np.abs(grade) > t.max_grade_pct
    for ra, rb in runs(over):
        ctx.warn(f"grade clamped to ±{t.max_grade_pct:.0f}% at {grid[ra] / 1000:.2f}–{grid[min(rb, n - 1)] / 1000:.2f} km "
                 f"(max {np.abs(grade[ra:rb]).max():.1f}%)", code="grade_clamped", sStart=float(grid[ra]))
    grade = np.clip(grade, -t.max_grade_pct, t.max_grade_pct)
    ascent, descent = ascent_with_hysteresis(zs)

    # ---- Heading, curvature ---------------------------------------------------------------------------
    heading = heading_compass(x, y)
    radius = turning_radius(x, y, sp, 10.0)
    radius = np.where(np.isfinite(radius) & (radius < 5000), radius, np.inf)

    # ---- Surfaces ---------------------------------------------------------------------------------------
    crr = np.ones(n)
    code = np.zeros(n, dtype=np.uint8)
    width = np.zeros(n)
    surf_class = np.empty(n, dtype=object)
    cache = {}
    for i in range(n):
        key = (attr["surface"][i], attr["smoothness"][i], attr["highway"][i], attr["width"][i], attr["lanes"][i])
        if key not in cache:
            cls, mult = classify(key[0], key[1], key[2])
            cache[key] = (cls, mult, width_m({"width": key[3] or None, "lanes": key[4] or None, "highway": key[2]}))
        cls, mult, w = cache[key]
        surf_class[i] = cls
        crr[i] = mult
        code[i] = SURFACE_CODES.get(cls, 0)
        width[i] = w
    # Bridge decks
    code[bt & (np.array([v not in ("", "no") for v in attr["bridge"]]))] = SURFACE_CODES["bridge_deck"]

    arrays = {"s": grid, "x": x, "y": y, "z": zs, "gradePct": grade, "headingRad": heading,
              "radiusM": radius, "crrMultiplier": crr, "surfaceCode": code, "roadWidthM": np.clip(np.round(width), 1, 255)}
    data, layout = encode_route_bin(arrays)
    course_id = "c_" + hashlib.sha256(data + stable_json(ctx.options.fingerprint()).encode() + PIPELINE_VERSION.encode()).hexdigest()[:20]

    # Barometric comparison
    info = ctx.read_json("ingest.json")
    baro = None
    if info.get("hasBarometric"):
        raw = read_parquet(ctx, "route_raw.parquet")
        e = raw["ele"]
        if np.isfinite(e).mean() > 0.9:
            ok = np.isfinite(e)
            sr, (er,) = resample_uniform(raw["s"][ok], sp, e[ok])
            up, _ = ascent_with_hysteresis(gaussian_smooth(er, sp, 20.0))
            baro = {"inputAscentM": round(up, 1), "demAscentM": round(ascent, 1), "differenceM": round(up - ascent, 1)}

    stats = {"distanceM": round(float(grid[-1]), 1), "ascentM": round(ascent, 1), "descentM": round(descent, 1),
             "maxGradePct": round(float(np.abs(grade).max()), 1), "minElevationM": round(float(zs.min()), 1),
             "maxElevationM": round(float(zs.max()), 1), "laps": 1}
    o = ctx.read_json("origin.json")
    o.update({"hOrthometric": round(float(zs[0]), 2), "verticalDatum": "EGM2008", "geoidUndulation": geoid_undulation(o["lat"], o["lon"])})

    ctx.adopt_course_id(course_id)
    ctx.write_json("origin.json", o)
    ctx.write_bytes("route.bin", data)
    ctx.write_json("route_meta.json", {"count": n, "sampleSpacingM": sp, "arrays": layout, "stats": stats, "structures": structures,
                                       "elevationSources": zones, "barometric": baro, "smoothingSigmaM": sigma})
    write_parquet(ctx, "route_geo.parquet", {"s": grid, "lat": lat, "lon": lon, "surface": surf_class, "bridge": attr["bridge"],
                                             "tunnel": attr["tunnel"], "highway": attr["highway"], "name": attr["name"],
                                             "matched": attr["matched"], "zRaw": z_raw, "demSource": src})
    ctx.cache.pop("route", None)
    return ["route.bin", "route_meta.json", "route_geo.parquet", "origin.json"]


def geoid_undulation(lat: float, lon: float) -> float | None:
    """EGM2008 undulation N (ellipsoidal = orthometric + N) via PROJ grids, if installed; else None."""
    try:
        from pyproj import Transformer

        tf = Transformer.from_crs("EPSG:4979", "EPSG:4326+3855", always_xy=True, only_best=True)
        _, _, h = tf.transform(lon, lat, 0.0)
        if np.isfinite(h) and abs(h) < 200:
            return round(-float(h), 3)
    except Exception:  # noqa: BLE001
        pass
    return None
