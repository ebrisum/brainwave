"""Stage 1 — ingest: parse, validate, concatenate segments, flag gaps, keep waypoints as POIs."""
from __future__ import annotations

import numpy as np

from ..geo import LocalFrame, cumulative_distance
from ..ingest import IngestError, read_course
from ..pipeline import BuildContext
from .common import write_parquet


def run(ctx: BuildContext) -> list[str]:
    t = ctx.config.tunables
    rc = read_course(ctx.input_path)
    # Drop exact duplicate consecutive points
    keep = np.ones(len(rc.lat), dtype=bool)
    keep[1:] = (np.diff(rc.lat) != 0) | (np.diff(rc.lon) != 0)
    lat, lon, ele, tim = rc.lat[keep], rc.lon[keep], rc.ele[keep], rc.time[keep]
    if len(lat) < t.min_points:
        raise IngestError(f"course has {len(lat)} points; at least {t.min_points} are required")
    frame = LocalFrame(lat[0], lon[0])
    x, y = frame.to_xy(lat, lon)
    s = cumulative_distance(x, y)
    if s[-1] > t.max_course_km * 1000:
        raise IngestError(f"course is {s[-1] / 1000:.1f} km; the limit is {t.max_course_km:.0f} km")
    gaps = np.nonzero(np.hypot(np.diff(x), np.diff(y)) > t.gap_flag_m)[0]
    for g in gaps[:50]:
        ctx.warn(f"gap of {np.hypot(x[g + 1] - x[g], y[g + 1] - y[g]):.0f} m in the track at {s[g] / 1000:.2f} km", code="gap",
                 s=float(s[g]))
    if len(gaps) > 50:
        ctx.warn(f"{len(gaps) - 50} more gaps over {t.gap_flag_m:.0f} m", code="gap")
    if not np.isfinite(ele).any():
        ctx.warn("input has no elevation; DEM only", code="no_input_elevation")
    ctx.write_json("origin.json", {"lat": float(lat[0]), "lon": float(lon[0])})
    seg = np.zeros(len(lat), dtype=np.int16)
    for b in rc.segment_breaks:
        seg[b:] += 1
    write_parquet(ctx, "route_raw.parquet", {"lat": lat, "lon": lon, "ele": ele, "time": tim, "x": x, "y": y, "s": s, "segment": seg})
    ctx.write_json("pois_raw.json", rc.pois)
    ctx.write_json("ingest.json", {"name": ctx.options.name or rc.name, "format": rc.source_format, "points": int(len(lat)),
                                   "rawDistanceM": float(s[-1]), "hasBarometric": rc.has_barometric, "segments": int(seg.max() + 1)})
    ctx._frame = frame
    return ["route_raw.parquet", "pois_raw.json", "origin.json", "ingest.json"]
