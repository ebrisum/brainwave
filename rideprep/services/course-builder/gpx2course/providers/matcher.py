"""Map matching: self-hosted Valhalla (trace_attributes) with a nearest-way fallback."""
from __future__ import annotations

import numpy as np
import shapely

from . import ProviderInfo, ProviderUnavailable, http_client
from .osm import Feature, is_road

ATTR_KEYS = ("highway", "surface", "smoothness", "width", "lanes", "bridge", "tunnel", "name", "cycleway", "oneway")


def empty_attributes(n: int) -> dict:
    a = {k: np.array([""] * n, dtype=object) for k in ATTR_KEYS}
    a["way_id"] = np.full(n, -1, dtype=np.int64)
    a["matched"] = np.zeros(n, dtype=bool)
    return a


class Matcher:
    info: ProviderInfo

    def available(self) -> bool:
        return True

    def match(self, lat: np.ndarray, lon: np.ndarray, x: np.ndarray, y: np.ndarray, heading: np.ndarray) -> dict:
        raise NotImplementedError


# Valhalla's edge.surface categories → OSM-like surface/smoothness
_VALHALLA_SURFACE = {
    "paved_smooth": ("asphalt", "excellent"), "paved": ("asphalt", "good"), "paved_rough": ("asphalt", "bad"),
    "compacted": ("compacted", ""), "dirt": ("dirt", ""), "gravel": ("gravel", ""), "path": ("ground", ""), "impassable": ("ground", "impassable"),
}
_VALHALLA_CLASS = {"motorway": "motorway", "trunk": "trunk", "primary": "primary", "secondary": "secondary", "tertiary": "tertiary",
                   "unclassified": "unclassified", "residential": "residential", "service_other": "service"}


class ValhallaMatcher(Matcher):
    info = ProviderInfo("valhalla", "matcher", "MIT (software); data ODbL", "© OpenStreetMap contributors")

    def __init__(self, url: str, timeout: float, offline: bool):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.offline = offline

    def available(self) -> bool:
        if self.offline:
            return False
        try:
            with http_client(3) as c:
                return c.get(f"{self.url}/status").status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def match(self, lat, lon, x, y, heading):
        n = len(lat)
        out = empty_attributes(n)
        step = 4  # send every 4th 5 m sample (20 m) to keep requests small
        idx = np.arange(0, n, step)
        attrs = ["edge.way_id", "edge.surface", "edge.road_class", "edge.bridge", "edge.tunnel", "edge.names", "edge.lane_count",
                 "edge.cycle_lane", "edge.use", "matched.edge_index", "matched.type"]
        with http_client(self.timeout) as c:
            for k0 in range(0, len(idx), 3000):
                part = idx[k0:k0 + 3000]
                body = {"shape": [{"lat": float(lat[i]), "lon": float(lon[i])} for i in part], "costing": "bicycle",
                        "shape_match": "map_snap", "filters": {"attributes": attrs, "action": "include"}}
                try:
                    r = c.post(f"{self.url}/trace_attributes", json=body)
                    r.raise_for_status()
                    res = r.json()
                except Exception as ex:  # noqa: BLE001
                    raise ProviderUnavailable(f"Valhalla trace_attributes failed: {ex}") from ex
                edges = res.get("edges", [])
                for j, mp in enumerate(res.get("matched_points", [])):
                    ei = mp.get("edge_index")
                    if mp.get("type") == "unmatched" or ei is None or ei >= len(edges):
                        continue
                    e = edges[ei]
                    i0 = part[j]
                    sl = slice(i0, min(i0 + step, n))
                    surf, smooth = _VALHALLA_SURFACE.get(e.get("surface", ""), ("", ""))
                    out["matched"][sl] = True
                    out["way_id"][sl] = int(e.get("way_id", -1))
                    hw = "cycleway" if e.get("use") == "cycleway" else _VALHALLA_CLASS.get(e.get("road_class", ""), "")
                    vals = {"highway": hw, "surface": surf, "smoothness": smooth, "lanes": str(e.get("lane_count", "")),
                            "bridge": "yes" if e.get("bridge") else "", "tunnel": "yes" if e.get("tunnel") else "",
                            "name": ";".join(e.get("names", []) or []), "cycleway": str(e.get("cycle_lane", "") or "")}
                    for k, v in vals.items():
                        out[k][sl] = v
        return out


def way_id(f: Feature, index: int) -> int:
    return int(f.osm_id) if isinstance(f.osm_id, int) else int(index)


class NearestWayMatcher(Matcher):
    """Snaps each sample to the nearest OSM highway within 20 m whose direction agrees within 45°."""

    info = ProviderInfo("nearest-way", "matcher", "ODbL", "© OpenStreetMap contributors")

    def __init__(self, roads: list[Feature], frame, max_dist: float = 20.0):
        self.roads = [f for f in roads if is_road(f.tags) and f.geom.geom_type in ("LineString", "MultiLineString")]
        self.frame = frame
        self.max_dist = max_dist

    def available(self) -> bool:
        return len(self.roads) > 0

    def match(self, lat, lon, x, y, heading):
        n = len(x)
        out = empty_attributes(n)
        if not self.roads:
            return out
        # Split long ways into short pieces: linear referencing is O(vertices) per query.
        pieces, owner = [], []
        for k, f in enumerate(self.roads):
            g = f.geom_xy(self.frame)
            for part in getattr(g, "geoms", [g]):
                co = np.asarray(part.coords)
                for a in range(0, len(co) - 1, 32):
                    pieces.append(shapely.LineString(co[a:a + 33]))
                    owner.append(k)
        geoms = np.array(pieces, dtype=object)
        owner = np.array(owner)
        tree = shapely.STRtree(geoms)
        pts = shapely.points(x, y)
        pi, gi = tree.query(pts, predicate="dwithin", distance=self.max_dist)
        if len(pi) == 0:
            return out
        g = geoms[gi]
        p = pts[pi]
        dist = shapely.distance(p, g)
        t = shapely.line_locate_point(g, p)
        a = shapely.line_interpolate_point(g, np.maximum(t - 3, 0))
        b = shapely.line_interpolate_point(g, t + 3)
        bear = np.arctan2(shapely.get_x(b) - shapely.get_x(a), shapely.get_y(b) - shapely.get_y(a))
        diff = np.abs((bear - heading[pi] + np.pi) % (2 * np.pi) - np.pi)
        diff = np.minimum(diff, np.pi - diff)  # ways are bidirectional
        score = dist + np.where(diff < np.radians(45), 0, 1e6) + diff * 10
        best = np.full(n, np.inf)
        best_g = np.full(n, -1)
        best_piece = np.full(n, -1)
        best_t = np.zeros(n)
        order = np.argsort(score)[::-1]  # assign best last so it wins
        best[pi[order]] = score[order]
        best_g[pi[order]] = owner[gi[order]]
        best_piece[pi[order]] = gi[order]
        best_t[pi[order]] = t[order]
        ok = best < 1e5
        snap = shapely.line_interpolate_point(geoms[best_piece[ok]], best_t[ok])
        out["snap_x"] = np.full(n, np.nan)
        out["snap_y"] = np.full(n, np.nan)
        out["snap_x"][ok] = shapely.get_x(snap)
        out["snap_y"][ok] = shapely.get_y(snap)
        for i in np.nonzero(ok)[0]:
            f = self.roads[best_g[i]]
            out["matched"][i] = True
            out["way_id"][i] = way_id(f, best_g[i])
            for k in ATTR_KEYS:
                v = f.tags.get(k)
                out[k][i] = "" if v is None else str(v)
        return out
