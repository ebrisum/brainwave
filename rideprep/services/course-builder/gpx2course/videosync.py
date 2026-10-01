"""Video mode: map a recorded ride (GPX/TCX/FIT with timestamps, e.g. from the camera or a head unit) onto the course,
so the client can play that ride's video at the rider's *virtual* speed. Output: <package>/video/<name>.json with
(s, videoTimeS) pairs every ~10 m. Partial coverage is fine; the client falls back to the 3D world outside it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from .geo import LocalFrame
from .ingest import read_course


def map_track(pkg: Path, track: Path, name: str | None = None, video_offset_s: float = 0.0, max_dist_m: float = 40.0) -> dict:
    """video_offset_s: video time (s) at the first track timestamp (positive if the video started earlier)."""
    m = json.loads((pkg / "manifest.json").read_text())
    meta = json.loads((pkg / "route_meta.json").read_text())
    buf = (pkg / "route.bin").read_bytes()
    n = meta["count"]
    arr = {a["name"]: np.frombuffer(buf, "<f4", n, a["offset"]).astype(np.float64) for a in meta["arrays"] if a["type"] == "float32"}
    rc = read_course(track)
    ok = np.isfinite(rc.time)
    if ok.sum() < 10:
        raise ValueError("the track has no timestamps; video sync needs a recorded ride (GPX/TCX/FIT with time)")
    o = m["origin"]
    fr = LocalFrame(o["lat"], o["lon"])
    x, y = fr.to_xy(rc.lat[ok], rc.lon[ok])
    t = rc.time[ok] - rc.time[ok][0] + video_offset_s
    tree = cKDTree(np.c_[arr["x"], arr["y"]])
    s_route = arr["s"]
    out_s, out_t = [], []
    s_prev = None
    for xi, yi, ti in zip(x, y, t):
        idx = tree.query_ball_point([xi, yi], max_dist_m)
        if not idx:
            continue
        cand = s_route[idx]
        if s_prev is not None:
            fwd = cand[(cand >= s_prev - 20) & (cand <= s_prev + 400)]  # forward along the course (handles laps)
            if len(fwd) == 0:
                continue
            d = np.hypot(arr["x"][np.searchsorted(s_route, fwd)] - xi, arr["y"][np.searchsorted(s_route, fwd)] - yi)
            s_new = float(fwd[np.argmin(d)])
            s_new = max(s_new, s_prev)
        else:
            # On loops several passes are close: start on the earliest one
            s_new = float(cand.min())
        if s_prev is None or s_new - s_prev >= 10 or (out_t and ti - out_t[-1] > 30):
            out_s.append(round(s_new, 1))
            out_t.append(round(float(ti), 2))
            s_prev = s_new
    if len(out_s) < 2:
        raise ValueError("the track does not follow this course")
    sp = np.diff(out_s) / np.maximum(np.diff(out_t), 1e-3)
    nm = name or re.sub(r"[^A-Za-z0-9_-]+", "_", track.stem)
    res = {"name": nm, "source": track.name, "videoOffsetS": video_offset_s, "sStart": out_s[0], "sEnd": out_s[-1],
           "coverage": round((out_s[-1] - out_s[0]) / m["stats"]["distanceM"], 3), "medianSpeedMs": round(float(np.median(sp)), 2),
           "points": [[a, b] for a, b in zip(out_s, out_t)]}
    (pkg / "video").mkdir(exist_ok=True)
    (pkg / "video" / f"{nm}.json").write_text(json.dumps(res, separators=(",", ":")))
    return res
