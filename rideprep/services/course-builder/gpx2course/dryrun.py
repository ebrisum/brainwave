"""--dry-run: data coverage, chosen sources and a time estimate, without building."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from .config import Config
from .geo import LocalFrame, cumulative_distance
from .ingest import read_course
from .pipeline import BuildOptions

# Seconds per km per stage on one worker, calibrated on the fixtures (see docs/MILESTONES.md); fixed overheads in seconds.
COST_PER_KM = {"ingest": 0.002, "match": 0.01, "profile": 0.02, "corridor": 0.12, "structure": 0.01, "wind": 0.35, "weather": 0.0,
               "quick": 0.08, "bake": 0.25, "export-web": 0.01, "export-unreal": 0.06, "validate": 0.02}
PARALLEL = {"wind", "bake"}
OVERHEAD_S = {"weather": 1.0, "validate": 0.5, "corridor": 0.5}


def estimate(km: float, workers: int, tier: str, targets) -> dict:
    per = {}
    for st, c in COST_PER_KM.items():
        if tier == "quick" and st in ("bake", "export-web"):
            continue
        if st == "export-unreal" and "unreal" not in targets:
            continue
        if st == "export-web" and "web" not in targets:
            continue
        t = c * km / (min(workers, 16) * 0.8 if st in PARALLEL else 1) + OVERHEAD_S.get(st, 0.2)
        per[st] = round(t, 1)
    return per


def dry_run(path: Path, cfg: Config, opts: BuildOptions) -> dict:
    from .providers.matcher import ValhallaMatcher
    from .providers.osm import OverpassOsm, PbfOsm, SidecarOsm

    t0 = time.time()
    rc = read_course(path)
    fr = LocalFrame(rc.lat[0], rc.lon[0])
    x, y = fr.to_xy(rc.lat, rc.lon)
    km = float(cumulative_distance(x, y)[-1] / 1000)
    sources = {}
    osm = {"sidecar": SidecarOsm(path).available(), "pbf": PbfOsm(cfg.endpoints.osm_pbf_dir).available(), "overpass": not cfg.offline}
    sources["osm"] = next((k for k in cfg.providers.osm if osm.get(k)), None)
    sources["matcher"] = "valhalla" if ValhallaMatcher(cfg.endpoints.valhalla_url, 3, cfg.offline).available() else (
        "nearest-way" if sources["osm"] else "none (unmatched)")
    dem = []
    if "copernicus" in cfg.providers.dem and not cfg.offline:
        from .providers.dem import CopernicusDem
        try:
            idx = np.linspace(0, len(rc.lat) - 1, 20).astype(int)
            z = CopernicusDem(cfg.endpoints.copernicus_dem, cfg.cache_dir).sample(rc.lat[idx], rc.lon[idx])
            dem.append({"provider": "copernicus", "coverage": float(np.isfinite(z).mean()), "resolution_m": 30})
        except Exception as ex:  # noqa: BLE001
            dem.append({"provider": "copernicus", "coverage": 0.0, "error": str(ex)})
    if np.isfinite(rc.ele).any():
        dem.append({"provider": "gpx", "coverage": float(np.isfinite(rc.ele).mean())})
    sources["dem"] = dem
    sources["landcover"] = "worldcover" if not cfg.offline and "worldcover" in cfg.providers.landcover else "osm-landcover"
    sources["weather"] = "open-meteo" if not cfg.offline else "generic climatology (offline)"
    per = estimate(km, opts.workers, opts.tier, opts.targets)
    return {"name": opts.name or rc.name, "distanceKm": round(km, 2), "points": int(len(rc.lat)), "format": rc.source_format,
            "sources": sources, "estimateS": per, "totalEstimateS": round(sum(per.values()), 1), "workers": opts.workers,
            "dryRunS": round(time.time() - t0, 2)}
