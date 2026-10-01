"""Land cover providers returning ESA WorldCover class codes."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import ProviderInfo, ProviderUnavailable
from .dem import TiledCogSampler

WORLDCOVER_CLASSES = {10: "tree", 20: "shrub", 30: "grass", 40: "crop", 50: "built", 60: "bare", 70: "snow", 80: "water",
                      90: "wetland", 95: "mangrove", 100: "moss"}


class LandcoverProvider:
    info: ProviderInfo

    def available(self) -> bool:
        return True

    def sample(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        raise NotImplementedError


class WorldCover(LandcoverProvider):
    info = ProviderInfo("worldcover", "landcover", "CC BY 4.0", "ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021)", 10)

    def __init__(self, base_url: str, cache_dir: Path, offline: bool = False):
        self.base_url = base_url.rstrip("/")
        self.offline = offline
        self.sampler = TiledCogSampler(self._url, 3, cache_dir, max_pixels=60_000_000, resampling="nearest")

    def _url(self, tlat: int, tlon: int) -> str:
        ns = f"N{tlat:02d}" if tlat >= 0 else f"S{-tlat:02d}"
        ew = f"E{tlon:03d}" if tlon >= 0 else f"W{-tlon:03d}"
        return f"/vsicurl/{self.base_url}/ESA_WorldCover_10m_2021_v200_{ns}{ew}_Map.tif"

    def available(self) -> bool:
        return not self.offline

    def sample(self, lat, lon):
        if self.offline:
            raise ProviderUnavailable("offline")
        v = self.sampler.read(lat, lon, order=0)
        if np.all(np.isnan(v)):
            raise ProviderUnavailable("WorldCover not reachable")
        v = np.where(np.isnan(v) | (v == 0), 30, v)
        return v.astype(np.uint8).reshape(np.shape(lat))


# OSM tag → WorldCover class
def osm_tags_to_class(tags: dict) -> int | None:
    nat = tags.get("natural")
    lu = tags.get("landuse")
    if nat == "water" or tags.get("waterway") in ("riverbank", "dock") or lu in ("reservoir", "basin"):
        return 80
    if nat in ("wood",) or lu == "forest":
        return 10
    if nat in ("scrub", "heath"):
        return 20
    if nat in ("wetland",):
        return 90
    if nat in ("bare_rock", "sand", "beach", "scree"):
        return 60
    if lu in ("residential", "commercial", "industrial", "retail", "construction"):
        return 50
    if lu in ("farmland", "orchard", "vineyard", "allotments"):
        return 40
    if lu in ("meadow", "grass", "village_green", "recreation_ground") or nat == "grassland":
        return 30
    return None


class OsmLandcover(LandcoverProvider):
    """Fallback: rasterises OSM land-use polygons; buildings count as built-up; default open grassland."""

    info = ProviderInfo("osm-landcover", "landcover", "ODbL", "© OpenStreetMap contributors", None)

    def __init__(self, features, frame, default_class: int = 30):
        import shapely
        self.frame = frame
        self.default = default_class
        polys, classes, areas = [], [], []
        for f in features:
            if f.geom.geom_type not in ("Polygon", "MultiPolygon"):
                continue
            c = 50 if f.tags.get("building") else osm_tags_to_class(f.tags)
            if c is None:
                continue
            g = f.geom_xy(frame)
            polys.append(g)
            classes.append(c)
            areas.append(g.area)
        # Smaller polygons win over larger ones (water in farmland, buildings in residential areas)
        order = np.argsort(areas)
        self.polys = [polys[i] for i in order]
        self.classes = np.array([classes[i] for i in order], dtype=np.uint8)
        self.tree = shapely.STRtree(self.polys) if self.polys else None

    def sample(self, lat, lon):
        import shapely
        x, y = self.frame.to_xy(np.ravel(lat), np.ravel(lon))
        out = np.full(x.shape, self.default, dtype=np.uint8)
        if self.tree is None:
            return out.reshape(np.shape(lat))
        pts = shapely.points(x, y)
        pi, gi = self.tree.query(pts, predicate="within")
        # For each point keep the smallest polygon (lowest index after sort)
        best = np.full(x.shape, np.iinfo(np.int64).max)
        np.minimum.at(best, pi, gi)
        hit = best != np.iinfo(np.int64).max
        out[hit] = self.classes[best[hit]]
        return out.reshape(np.shape(lat))
