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
COST_PER_KM = {"ingest": 0.001, "match": 0.005, "profile": 0.002, "corridor": 0.26, "structure": 0.001, "wind": 0.065, "weather": 0.0,
               "quick": 0.055, "bake": 0.012, "export-web": 0.0005, "export-unreal": 0.105, "validate": 0.002}
PARALLEL = {"corridor", "wind", "bake"}
OVERHEAD_S = {"weather": 1.0, "validate": 0.5, "corridor": 0.5}


# Wall time of `_bench()` on the reference machine the COST_PER_KM table was calibrated on.
REFERENCE_BENCH_S = 0.15


def _bench() -> float:
    """Small workload shaped like the heavy stages (KD-tree queries, map_coordinates, shapely predicates)."""
    import shapely
    from scipy.ndimage import map_coordinates
    from scipy.spatial import cKDTree

    rng = np.random.default_rng(0)
    t0 = time.perf_counter()
    pts = rng.random((20000, 2)) * 1000
    cKDTree(pts).query(rng.random((60000, 2)) * 1000, k=3)
    map_coordinates(rng.random((300, 300)), rng.random((2, 200000)) * 299, order=1)
    polys = [shapely.box(x, y, x + 20, y + 20) for x, y in rng.random((2000, 2)) * 1000]
    shapely.STRtree(polys).query(shapely.points(rng.random((50000, 2)) * 1000), predicate="within")
    return time.perf_counter() - t0


def machine_factor() -> float:
    """>1 on slower machines. Median of three runs, clamped to a sane range."""
    runs = sorted(_bench() for _ in range(3))
    return float(min(max(runs[1] / REFERENCE_BENCH_S, 0.25), 6.0))


def estimate(km: float, workers: int, tier: str, targets, factor: float = 1.0) -> dict:
    per = {}
    for st, c in COST_PER_KM.items():
        if tier == "quick" and st in ("bake", "export-web"):
            continue
        if st == "export-unreal" and "unreal" not in targets:
            continue
        if st == "export-web" and "web" not in targets:
            continue
        t = factor * c * km / (min(workers, 16) * 0.8 if st in PARALLEL else 1) + OVERHEAD_S.get(st, 0.2)
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
    osm = {"sidecar": SidecarOsm(path).available(), "pbf": PbfOsm(cfg.endpoints.osm_pbf_dir).available(), "overture": not cfg.offline, "overpass": not cfg.offline}
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
    factor = machine_factor()
    per = estimate(km, opts.workers, opts.tier, opts.targets, factor)
    return {"name": opts.name or rc.name, "distanceKm": round(km, 2), "points": int(len(rc.lat)), "format": rc.source_format,
            "sources": sources, "estimateS": per, "machineFactor": round(factor, 2), "totalEstimateS": round(sum(per.values()), 1), "workers": opts.workers,
            "dryRunS": round(time.time() - t0, 2)}
