"""OpenStreetMap feature providers: fixture sidecar GeoJSON, local .pbf extract (pyosmium), Overpass (dev only)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import shape

from . import ProviderInfo, ProviderUnavailable, http_client

OSM_INFO = ProviderInfo("osm", "osm", "ODbL 1.0", "© OpenStreetMap contributors")


@dataclass
class Feature:
    geom: object  # shapely geometry in lon/lat
    tags: dict
    osm_id: int | None = None
    _xy: dict = field(default_factory=dict, repr=False)

    def geom_xy(self, frame):
        key = id(frame)
        g = self._xy.get(key)
        if g is None:
            g = shapely.transform(self.geom, lambda c: np.c_[frame.to_xy(c[:, 1], c[:, 0])])
            self._xy[key] = g
        return g


# Feature classes the pipeline uses
def is_road(t): return "highway" in t
def is_building(t): return "building" in t and t.get("building") != "no"
def is_tree_row(t): return t.get("natural") == "tree_row"
def is_tree(t): return t.get("natural") == "tree"
def is_hedge(t): return t.get("barrier") == "hedge"
def is_forest(t): return t.get("landuse") == "forest" or t.get("natural") == "wood"
def is_water(t): return t.get("natural") == "water" or "waterway" in t


class OsmProvider:
    info = OSM_INFO

    def available(self) -> bool:
        return True

    def features(self, bbox: tuple[float, float, float, float]) -> list[Feature]:
        """All relevant features intersecting bbox (west, south, east, north)."""
        raise NotImplementedError


def _filter_bbox(feats: list[Feature], bbox) -> list[Feature]:
    box = shapely.box(*bbox)
    geoms = [f.geom for f in feats]
    hit = shapely.intersects(np.array(geoms, dtype=object), box)
    return [f for f, h in zip(feats, hit) if h]


class SidecarOsm(OsmProvider):
    """Reads `<course>.features.geojson` next to the input file (used by the fixtures; also handy for testing)."""

    info = ProviderInfo("sidecar", "osm", "as declared by the sidecar (fixtures: synthetic, CC0)", "synthetic fixture features")

    def __init__(self, input_path: Path):
        self.path = input_path.with_name(input_path.stem + ".features.geojson")
        self._cache: list[Feature] | None = None

    def available(self) -> bool:
        return self.path.exists()

    def features(self, bbox):
        if not self.available():
            raise ProviderUnavailable(f"no sidecar {self.path.name}")
        if self._cache is None:
            data = json.loads(self.path.read_text())
            self._cache = [Feature(shape(f["geometry"]), f.get("properties") or {}, f.get("id")) for f in data["features"]]
        return _filter_bbox(self._cache, bbox)


class PbfOsm(OsmProvider):
    """Local Geofabrik .pbf extracts, read with pyosmium (optional dependency)."""

    def __init__(self, pbf_dir: str):
        self.dir = Path(pbf_dir) if pbf_dir else None

    def available(self) -> bool:
        if not self.dir or not self.dir.exists() or not any(self.dir.glob("*.osm.pbf")):
            return False
        try:
            import osmium  # noqa: F401
        except ImportError:
            return False
        return True

    def features(self, bbox):
        if not self.available():
            raise ProviderUnavailable("no local .pbf extracts or pyosmium missing")
        import osmium

        wanted = ("highway", "building", "natural", "landuse", "barrier", "waterway", "bridge")
        out: list[Feature] = []
        box = shapely.box(*bbox)
        for pbf in sorted(self.dir.glob("*.osm.pbf")):
            fp = osmium.FileProcessor(str(pbf)).with_locations().with_areas().with_filter(osmium.filter.KeyFilter(*wanted))
            for obj in fp:
                tags = dict(obj.tags)
                try:
                    if obj.is_node():
                        if tags.get("natural") != "tree":
                            continue
                        g = shapely.Point(obj.location.lon, obj.location.lat)
                    elif obj.is_way():
                        coords = [(n.lon, n.lat) for n in obj.nodes]
                        if len(coords) < 2:
                            continue
                        g = shapely.LineString(coords)
                    elif obj.is_area():
                        polys = []
                        for outer in obj.outer_rings():
                            polys.append(shapely.Polygon([(n.lon, n.lat) for n in outer], [[(n.lon, n.lat) for n in inner] for inner in obj.inner_rings(outer)]))
                        g = shapely.MultiPolygon(polys) if len(polys) > 1 else polys[0]
                    else:
                        continue
                except Exception:
                    continue
                if g.intersects(box):
                    out.append(Feature(g, tags, obj.id))
        return out


class OverpassOsm(OsmProvider):
    """Overpass API. Development only (fair-use limits); production uses local .pbf extracts."""

    def __init__(self, url: str, timeout: float, offline: bool):
        self.url = url
        self.timeout = timeout
        self.offline = offline

    def available(self) -> bool:
        return not self.offline

    def features(self, bbox):
        if self.offline:
            raise ProviderUnavailable("offline")
        w, s, e, n = bbox
        b = f"{s},{w},{n},{e}"
        q = f"""[out:json][timeout:120];
(
  way["highway"]({b}); way["building"]({b}); way["natural"~"tree_row|wood|water"]({b}); node["natural"="tree"]({b});
  way["landuse"]({b}); way["barrier"="hedge"]({b}); way["waterway"]({b});
);
out geom tags;"""
        try:
            with http_client(self.timeout) as c:
                r = c.post(self.url, data={"data": q})
                r.raise_for_status()
                data = r.json()
        except Exception as ex:  # noqa: BLE001
            raise ProviderUnavailable(f"Overpass failed: {ex}") from ex
        out = []
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            if el["type"] == "node":
                out.append(Feature(shapely.Point(el["lon"], el["lat"]), tags, el["id"]))
            elif el["type"] == "way" and "geometry" in el:
                coords = [(p["lon"], p["lat"]) for p in el["geometry"]]
                closed = len(coords) >= 4 and coords[0] == coords[-1]
                area = closed and (is_building(tags) or "landuse" in tags or tags.get("natural") in ("wood", "water"))
                out.append(Feature(shapely.Polygon(coords) if area else shapely.LineString(coords), tags, el["id"]))
        return out
