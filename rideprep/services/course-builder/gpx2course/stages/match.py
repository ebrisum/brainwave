"""Stage 2 — match: resample to 5 m and map-match to OSM (Valhalla → nearest-way → unmatched)."""
from __future__ import annotations

import numpy as np

from ..geo import cumulative_distance, gaussian_smooth, heading_compass, resample_uniform
from ..pipeline import BuildContext
from ..providers.matcher import NearestWayMatcher, ValhallaMatcher, empty_attributes
from ..roadsnap import needs_snap, snap
from .common import get_osm, latlon_bbox, read_parquet, write_parquet


def run(ctx: BuildContext) -> list[str]:
    raw = read_parquet(ctx, "route_raw.parquet")
    sp = ctx.config.tunables.sample_spacing_m
    snapped = False
    if needs_snap(raw["x"], raw["y"]):
        # Sparse planner export: rebuild the geometry on the road network first (gpx2course/roadsnap.py)
        rlat, rlon = ctx.frame.to_latlon(raw["x"], raw["y"])
        feats = get_osm(ctx, latlon_bbox(rlat, rlon, 400), "snap to road")
        roads = [f for f in feats if "highway" in f.tags and f.geom.geom_type in ("LineString", "MultiLineString")]
        if roads:
            sx, sy, src, share = snap(raw["x"], raw["y"], roads, ctx.frame)
            ctx.warn(f"Sparse route file ({len(raw['x'])} points); geometry rebuilt along the road network "
                     f"({share:.0%} of point pairs routed)", code="snapped_to_road")
            e = raw["ele"]
            ok = np.isfinite(e)
            ele = np.interp(src, np.nonzero(ok)[0], e[ok]) if ok.sum() >= 2 else np.full(len(sx), np.nan)
            raw = {"x": sx, "y": sy, "ele": ele}
            snapped = True
    # Light smoothing of GPS jitter before matching (a snapped route is already clean)
    xs = raw["x"] if snapped else gaussian_smooth(raw["x"], 1.0, 2.0)
    ys = raw["y"] if snapped else gaussian_smooth(raw["y"], 1.0, 2.0)
    s = cumulative_distance(xs, ys)
    grid, (x, y) = resample_uniform(s, sp, xs, ys)
    lat, lon = ctx.frame.to_latlon(x, y)
    heading = heading_compass(gaussian_smooth(x, sp, 10), gaussian_smooth(y, sp, 10))
    attrs = None
    snap_x = np.full(len(x), np.nan)
    snap_y = np.full(len(x), np.nan)
    for name in ctx.config.providers.matcher:
        if name == "valhalla":
            m = ValhallaMatcher(ctx.config.endpoints.valhalla_url, ctx.config.tunables.network_timeout_s, ctx.config.offline)
            if not m.available():
                continue
            try:
                attrs = m.match(lat, lon, x, y, heading)
                ctx.source("matcher", m.info)
                break
            except Exception as ex:  # noqa: BLE001
                ctx.warn(f"Valhalla matching failed ({ex}); trying the next matcher", code="matcher_failed")
        elif name == "nearest-way":
            feats = get_osm(ctx, latlon_bbox(lat, lon, 60), "map matching")
            m = NearestWayMatcher(feats, ctx.frame)
            if not m.available():
                continue
            attrs = m.match(lat, lon, x, y, heading)
            # Snapped to the matched way geometry for clean curvature
            snap_x, snap_y = attrs.pop("snap_x"), attrs.pop("snap_y")
            ctx.source("matcher", m.info)
            break
    if attrs is None:
        attrs = empty_attributes(len(x))
        ctx.warn("No map matcher available; the whole course is unmatched (raw track, default surfaces)", code="unmatched_all")
    _report_unmatched(ctx, attrs["matched"], grid)
    e = raw["ele"]
    ok = np.isfinite(e)
    ele = np.interp(grid, s[ok], e[ok]) if ok.sum() >= 2 else np.full(len(grid), np.nan)
    cols = {"s": grid, "x": x, "y": y, "lat": lat, "lon": lon, "heading": heading, "snap_x": snap_x, "snap_y": snap_y, "ele": ele}
    cols.update({k: v for k, v in attrs.items()})
    write_parquet(ctx, "route_matched.parquet", cols)
    return ["route_matched.parquet"]


def _report_unmatched(ctx: BuildContext, matched: np.ndarray, s: np.ndarray) -> None:
    if matched.all():
        return
    runs = []
    i = 0
    n = len(matched)
    while i < n:
        if not matched[i]:
            j = i
            while j < n and not matched[j]:
                j += 1
            if s[min(j, n - 1)] - s[i] >= 50:
                runs.append((float(s[i]), float(s[min(j, n - 1)])))
            i = j
        else:
            i += 1
    for a, b in runs[:30]:
        ctx.warn(f"unmatched stretch {a / 1000:.2f}–{b / 1000:.2f} km (kept raw track)", code="unmatched", sStart=a, sEnd=b)
    share = 1 - matched.mean()
    if share > 0.2:
        ctx.warn(f"{share:.0%} of the course could not be matched to OSM", code="unmatched_share")
