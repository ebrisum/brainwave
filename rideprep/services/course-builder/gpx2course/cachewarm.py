"""Prefetch regional DEM/land-cover tiles into the cache so repeat courses in the same region build fast."""
from __future__ import annotations

import math

from .config import Config
from .providers import http_client
from .providers.dem import CopernicusDem
from .providers.landcover import WorldCover


def warm(cfg: Config, bbox: tuple[float, float, float, float]) -> None:
    w, s, e, n = bbox
    dem = CopernicusDem(cfg.endpoints.copernicus_dem, cfg.cache_dir)
    wc = WorldCover(cfg.endpoints.worldcover, cfg.cache_dir)
    jobs = []
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            jobs.append(dem.sampler.url_for_tile(lat, lon))
    for lat in range(math.floor(s / 3) * 3, math.ceil(n / 3) * 3, 3):
        for lon in range(math.floor(w / 3) * 3, math.ceil(e / 3) * 3, 3):
            jobs.append(wc.sampler.url_for_tile(lat, lon))
    with http_client(300) as c:
        for vsi in jobs:
            url = vsi.removeprefix("/vsicurl/")
            dst = dem.sampler.local_path(url)
            if dst.exists():
                print(f"cached  {dst.name}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_suffix(".part")
            try:
                with c.stream("GET", url) as r:
                    if r.status_code == 404:
                        print(f"absent  {dst.name} (no coverage, e.g. sea)")
                        continue
                    r.raise_for_status()
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_bytes(1 << 20):
                            f.write(chunk)
                tmp.replace(dst)
                print(f"fetched {dst.name}")
            except Exception as ex:  # noqa: BLE001
                print(f"failed  {dst.name}: {ex}")
