"""Overture Maps provider: roads, buildings, water and land use from the public GeoParquet release on S3.

Reads only what a bbox needs: the Parquet footers (cached on disk), then the row groups whose bbox statistics
overlap, via HTTP range requests. No duckdb/S3 SDK needed — plain HTTPS through the configured proxy.
Features come back as `Feature`s with OSM-style tags so the rest of the pipeline is unchanged.
Licence: ODbL 1.0 (transportation, buildings, base water/land_use are OSM-derived) — docs/LICENSES.md.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import io
import json
import os
import pickle
import re
import threading
from pathlib import Path

import numpy as np
import shapely
from shapely.ops import substring

from . import ProviderInfo, ProviderUnavailable
from .osm import Feature, OsmProvider, _filter_bbox

BUCKET = os.environ.get("OVERTURE_BASE", "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com")
RELEASE = os.environ.get("OVERTURE_RELEASE", "2026-09-23.0")
OVERTURE_INFO = ProviderInfo("overture", "osm", "ODbL 1.0 (Overture Maps Foundation; derived from OpenStreetMap)",
                             "© OpenStreetMap contributors, Overture Maps Foundation")

# theme/type → columns we need (besides geometry/bbox)
LAYERS = {
    "transportation/segment": ["id", "subtype", "class", "names", "road_surface", "road_flags", "width_rules"],
    "buildings/building": ["id", "class", "height", "num_floors", "roof_shape", "roof_color", "facade_color", "facade_material", "roof_material"],
    "base/water": ["id", "subtype", "class", "names"],
    "base/land_use": ["id", "subtype", "class", "names"],
    "places/place": ["id", "names", "categories"],
}

# Overture road class → OSM highway (identical for most)
_HW = {"unknown": "road", "unclassified": "unclassified"}
# Overture land_use class → OSM tag
_LANDUSE = {"vineyard": ("landuse", "vineyard"), "orchard": ("landuse", "orchard"), "farmland": ("landuse", "farmland"),
            "meadow": ("landuse", "meadow"), "grass": ("landuse", "grass"), "forest": ("landuse", "forest"),
            "residential": ("landuse", "residential"), "industrial": ("landuse", "industrial"), "salt_pond": ("landuse", "salt_pond"),
            "cemetery": ("landuse", "cemetery"), "park": ("leisure", "park"), "pitch": ("leisure", "pitch"),
            "nature_reserve": ("leisure", "nature_reserve"), "beach": ("natural", "beach"), "wetland": ("natural", "wetland"),
            "olive_grove": ("landuse", "orchard")}


class _RangeFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests."""

    def __init__(self, client, url: str, size: int):
        self.client, self.url, self.size, self.pos = client, url, size, 0

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.size, self.pos + len(b)) - 1
        for attempt in range(4):
            try:
                r = self.client.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
                r.raise_for_status()
                break
            except Exception:
                if attempt == 3:
                    raise
        d = r.content
        b[: len(d)] = d
        self.pos += len(d)
        return len(d)


class OvertureOsm(OsmProvider):
    info = OVERTURE_INFO

    def __init__(self, cache_dir: str | Path, offline: bool = False, timeout: float = 60.0, layers: list[str] | None = None):
        self.cache = Path(cache_dir) / "overture" / RELEASE
        self.offline = offline
        self.timeout = timeout
        self.layers = layers or ["transportation/segment", "buildings/building", "base/water", "base/land_use"]
        self._client = None
        self._lock = threading.Lock()

    # ---- plumbing -------------------------------------------------------------------------------------------
    def available(self) -> bool:
        if self.offline:
            return any(self.cache.glob("q_*.pkl"))
        try:
            import pyarrow.parquet  # noqa: F401
        except ImportError:
            return False
        return True

    def client(self):
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=self.timeout, follow_redirects=True, limits=httpx.Limits(max_connections=16))
        return self._client

    def _keys(self, layer: str) -> list[tuple[str, int]]:
        theme, typ = layer.split("/")
        f = self.cache / "index" / f"{theme}_{typ}.json"
        if f.exists():
            return [tuple(k) for k in json.loads(f.read_text())]
        if self.offline:
            raise ProviderUnavailable("overture: offline and no cached index")
        out, tok = [], None
        while True:
            p = {"list-type": "2", "prefix": f"release/{RELEASE}/theme={theme}/type={typ}/"}
            if tok:
                p["continuation-token"] = tok
            x = self.client().get(BUCKET + "/", params=p).text
            out += [(k, int(s)) for k, s in re.findall(r"<Key>([^<]+\.parquet)</Key>.*?<Size>(\d+)</Size>", x)]
            m = re.search(r"<NextContinuationToken>([^<]+)<", x)
            if not m:
                break
            tok = m.group(1)
        if not out:
            raise ProviderUnavailable(f"overture: no files for {layer} in release {RELEASE}")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(out))
        return out

    def _rg_stats(self, key: str, size: int) -> list[list[float]]:
        """Per-row-group [xmin, ymin, xmax, ymax] from the footer statistics (cached)."""
        f = self.cache / "stats" / (hashlib.sha1(key.encode()).hexdigest()[:16] + ".json")
        if f.exists():
            return json.loads(f.read_text())
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(io.BufferedReader(_RangeFile(self.client(), f"{BUCKET}/{key}", size), 1 << 20))
        md = pf.metadata
        out = []
        for i in range(md.num_row_groups):
            rg = md.row_group(i)
            st = {}
            for c in range(rg.num_columns):
                col = rg.column(c)
                if col.path_in_schema in ("bbox.xmin", "bbox.ymin", "bbox.xmax", "bbox.ymax") and col.statistics and col.statistics.has_min_max:
                    st[col.path_in_schema] = col.statistics
            if len(st) == 4:
                out.append([st["bbox.xmin"].min, st["bbox.ymin"].min, st["bbox.xmax"].max, st["bbox.ymax"].max])
            else:
                out.append([-180, -90, 180, 90])
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(out))
        return out

    def read_layer(self, layer: str, bbox) -> list[dict]:
        """Raw rows (dicts with 'geometry' as shapely) of one layer intersecting bbox."""
        import pyarrow.parquet as pq

        w, s, e, n = bbox
        keys = self._keys(layer)
        with cf.ThreadPoolExecutor(12) as ex:
            stats = list(ex.map(lambda k: self._rg_stats(*k), keys))
        jobs = [(k, sz, [i for i, b in enumerate(st) if b[0] <= e and b[2] >= w and b[1] <= n and b[3] >= s])
                for (k, sz), st in zip(keys, stats)]
        jobs = [j for j in jobs if j[2]]
        cols = LAYERS[layer] + ["geometry", "bbox"]

        def read(job):
            k, sz, rgs = job
            pf = pq.ParquetFile(io.BufferedReader(_RangeFile(self.client(), f"{BUCKET}/{k}", sz), 4 << 20))
            have = set(pf.schema_arrow.names)
            t = pf.read_row_groups(rgs, columns=[c for c in cols if c in have])
            bb = t.column("bbox").combine_chunks()
            xmin, xmax = np.asarray(bb.field("xmin")), np.asarray(bb.field("xmax"))
            ymin, ymax = np.asarray(bb.field("ymin")), np.asarray(bb.field("ymax"))
            keep = (xmin <= e) & (xmax >= w) & (ymin <= n) & (ymax >= s)
            t = t.filter(keep).drop(["bbox"])
            return t.to_pylist()

        rows = []
        with cf.ThreadPoolExecutor(6) as ex:
            for part in ex.map(read, jobs):
                rows += part
        geoms = shapely.from_wkb([r["geometry"] for r in rows]) if rows else []
        for r, g in zip(rows, geoms):
            r["geometry"] = g
        return rows

    # ---- OSM-style features ---------------------------------------------------------------------------------
    def features(self, bbox):
        qkey = hashlib.sha1(json.dumps([RELEASE, sorted(self.layers), [round(v, 4) for v in bbox]]).encode()).hexdigest()[:16]
        qf = self.cache / f"q_{qkey}.pkl"
        if qf.exists():
            return pickle.loads(qf.read_bytes())
        # Superset query already cached?
        for p in self.cache.glob("q_*.json"):
            meta = json.loads(p.read_text())
            b = meta["bbox"]
            if meta["layers"] == sorted(self.layers) and b[0] <= bbox[0] and b[1] <= bbox[1] and b[2] >= bbox[2] and b[3] >= bbox[3]:
                return _filter_bbox(pickle.loads(p.with_suffix(".pkl").read_bytes()), bbox)
        if self.offline:
            raise ProviderUnavailable("overture: offline and bbox not cached")
        try:
            feats: list[Feature] = []
            for layer in self.layers:
                rows = self.read_layer(layer, bbox)
                conv = {"transportation/segment": _segments, "buildings/building": _buildings,
                        "base/water": _water, "base/land_use": _land_use, "places/place": _places}[layer]
                feats += conv(rows)
        except ProviderUnavailable:
            raise
        except Exception as ex:  # network, proxy, schema drift
            raise ProviderUnavailable(f"overture: {type(ex).__name__}: {ex}") from ex
        self.cache.mkdir(parents=True, exist_ok=True)
        tmp = qf.with_suffix(".tmp")
        tmp.write_bytes(pickle.dumps(feats))
        tmp.replace(qf)
        qf.with_suffix(".json").write_text(json.dumps({"bbox": list(bbox), "layers": sorted(self.layers)}))
        return feats


# ---- row → Feature converters -------------------------------------------------------------------------------
def _first(rules, default=None):
    """Value of the first rule that covers the whole segment (no `between`), else of the longest-covering one."""
    if not rules:
        return default
    best, cover = default, -1.0
    for r in rules:
        b = r.get("between")
        c = 1.0 if not b else float(b[1] - b[0])
        if c > cover:
            best, cover = r.get("value"), c
    return best


def _name(r):
    n = r.get("names")
    return (n or {}).get("primary") if isinstance(n, dict) else None


def _segments(rows) -> list[Feature]:
    out = []
    for r in rows:
        if r.get("subtype") != "road" or r["geometry"] is None or r["geometry"].geom_type != "LineString":
            continue
        cls = r.get("class") or "unknown"
        base = {"highway": _HW.get(cls, cls), "overture:id": r["id"]}
        if (nm := _name(r)):
            base["name"] = nm
        if (sf := _first(r.get("road_surface"))):
            base["surface"] = sf
        if (wd := _first(r.get("width_rules"))):
            base["width"] = str(round(float(wd), 1))
        # Bridges/tunnels may apply to part of a segment: split at the flag ranges
        cuts = []
        for fl in r.get("road_flags") or []:
            vals = set(fl.get("values") or [])
            tag = "bridge" if "is_bridge" in vals else "tunnel" if "is_tunnel" in vals else None
            if tag:
                b = fl.get("between") or [0.0, 1.0]
                cuts.append((float(b[0]), float(b[1]), tag))
        g = r["geometry"]
        if not cuts:
            out.append(Feature(g, base))
            continue
        edges = sorted({0.0, 1.0, *[c[0] for c in cuts], *[c[1] for c in cuts]})
        for a, b in zip(edges[:-1], edges[1:]):
            if b - a < 1e-6:
                continue
            t = dict(base)
            for ca, cb, tag in cuts:
                if ca <= a + 1e-9 and cb >= b - 1e-9:
                    t[tag] = "yes"
            t["overture:between"] = (a, b)
            out.append(Feature(substring(g, a, b, normalized=True), t))
    return out


def _buildings(rows) -> list[Feature]:
    out = []
    for r in rows:
        g = r["geometry"]
        if g is None or g.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        t = {"building": r.get("class") or "yes", "overture:id": r["id"]}
        if r.get("height"):
            t["height"] = str(round(float(r["height"]), 1))
        if r.get("num_floors"):
            t["building:levels"] = str(int(r["num_floors"]))
        for k, osm in (("roof_shape", "roof:shape"), ("roof_color", "roof:colour"), ("facade_color", "building:colour"),
                       ("facade_material", "building:material"), ("roof_material", "roof:material")):
            if r.get(k):
                t[osm] = r[k]
        out.append(Feature(g, t))
    return out


def _water(rows) -> list[Feature]:
    out = []
    for r in rows:
        g = r["geometry"]
        if g is None:
            continue
        cls = r.get("class") or r.get("subtype") or "water"
        if g.geom_type in ("LineString", "MultiLineString"):
            t = {"waterway": cls}
        else:
            t = {"natural": "water", "water": cls}
        if (nm := _name(r)):
            t["name"] = nm
        out.append(Feature(g, t))
    return out


def _land_use(rows) -> list[Feature]:
    out = []
    for r in rows:
        g = r["geometry"]
        if g is None or g.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        cls = r.get("class") or ""
        k, v = _LANDUSE.get(cls, ("landuse", cls or r.get("subtype") or "unknown"))
        t = {k: v, "overture:subtype": r.get("subtype")}
        if (nm := _name(r)):
            t["name"] = nm
        out.append(Feature(g, t))
    return out


def _places(rows) -> list[Feature]:
    out = []
    for r in rows:
        if r["geometry"] is None:
            continue
        cat = (r.get("categories") or {}).get("primary") if isinstance(r.get("categories"), dict) else None
        out.append(Feature(r["geometry"], {"place:category": cat or "", "name": _name(r) or ""}))
    return out
