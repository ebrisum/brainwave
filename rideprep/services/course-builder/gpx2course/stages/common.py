"""Helpers shared by stages: route arrays, OSM access, corridor rasters, provider selection."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from ..pipeline import BuildContext
from ..providers import ProviderUnavailable

# route.bin layout (spec §5): order and dtypes
ROUTE_ARRAYS = [("s", "float32"), ("x", "float32"), ("y", "float32"), ("z", "float32"), ("gradePct", "float32"),
                ("headingRad", "float32"), ("radiusM", "float32"), ("crrMultiplier", "float32"), ("surfaceCode", "uint8"),
                ("roadWidthM", "uint8")]

TILE_M = 3000.0      # corridor raster tile size (local frame)
TILE_RES_M = 10.0    # corridor raster resolution
FAR_RES_M = 90.0


def write_parquet(ctx: BuildContext, rel: str, cols: dict) -> None:
    table = pa.table({k: pa.array(v.tolist() if isinstance(v, np.ndarray) and v.dtype == object else v) for k, v in cols.items()})
    p = ctx.path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(p)


def read_parquet(ctx: BuildContext, rel: str) -> dict:
    t = pq.read_table(ctx.path(rel))
    return {c: t.column(c).to_numpy(zero_copy_only=False) for c in t.column_names}


def encode_route_bin(arrays: dict) -> tuple[bytes, list[dict]]:
    parts, layout, off = [], [], 0
    for name, dt in ROUTE_ARRAYS:
        a = np.ascontiguousarray(arrays[name], dtype=np.dtype(dt).newbyteorder("<"))
        layout.append({"name": name, "type": dt, "offset": off})
        parts.append(a.tobytes())
        off += a.nbytes
    return b"".join(parts), layout


def load_route(ctx: BuildContext) -> dict:
    """route.bin arrays + lat/lon (route_geo.parquet) as numpy arrays."""
    if "route" in ctx.cache:
        return ctx.cache["route"]
    meta = ctx.read_json("route_meta.json")
    buf = ctx.path("route.bin").read_bytes()
    n = meta["count"]
    out = {}
    for a in meta["arrays"]:
        dt = np.dtype(a["type"]).newbyteorder("<")
        out[a["name"]] = np.frombuffer(buf, dtype=dt, count=n, offset=a["offset"]).astype(np.float64 if a["type"] == "float32" else np.int32)
    geo = read_parquet(ctx, "route_geo.parquet")
    out["lat"] = geo["lat"]
    out["lon"] = geo["lon"]
    out["count"] = n
    out["spacing"] = meta["sampleSpacingM"]
    out["surface"] = geo["surface"]
    out["bridge"] = geo["bridge"]
    out["tunnel"] = geo["tunnel"]
    out["highway"] = geo["highway"]
    ctx.cache["route"] = out
    return out


def latlon_bbox(lat: np.ndarray, lon: np.ndarray, buffer_m: float) -> tuple[float, float, float, float]:
    dlat = buffer_m / 111_320.0
    dlon = buffer_m / (111_320.0 * max(math.cos(math.radians(float(np.mean(lat)))), 0.05))
    return float(lon.min() - dlon), float(lat.min() - dlat), float(lon.max() + dlon), float(lat.max() + dlat)


def osm_providers(ctx: BuildContext):
    from ..providers.osm import OverpassOsm, PbfOsm, SidecarOsm

    cfg = ctx.config
    out = []
    for name in cfg.providers.osm:
        if name == "sidecar":
            out.append(SidecarOsm(ctx.input_path))
        elif name == "pbf":
            out.append(PbfOsm(cfg.endpoints.osm_pbf_dir))
        elif name == "overpass":
            out.append(OverpassOsm(cfg.endpoints.overpass_url, cfg.tunables.network_timeout_s, cfg.offline))
    return out


def get_osm(ctx: BuildContext, bbox, purpose: str):
    """Features from the first OSM provider that can serve bbox. Empty list (with a warning) if none can."""
    key = ("osm", tuple(round(v, 5) for v in bbox))
    if key in ctx.cache:
        return ctx.cache[key]
    # Reuse a cached superset
    for k, v in ctx.cache.items():
        if isinstance(k, tuple) and k[0] == "osm" and k[1][0] <= bbox[0] and k[1][1] <= bbox[1] and k[1][2] >= bbox[2] and k[1][3] >= bbox[3]:
            from ..providers.osm import _filter_bbox
            return _filter_bbox(v, bbox)
    errors = []
    for p in osm_providers(ctx):
        if not p.available():
            errors.append(f"{type(p).__name__}: unavailable")
            continue
        try:
            feats = p.features(bbox)
        except ProviderUnavailable as ex:
            errors.append(str(ex))
            continue
        ctx.source("osm", p.info)
        ctx.cache[key] = feats
        return feats
    ctx.warn(f"No OSM data for {purpose}; continuing without ({'; '.join(errors)})", code="no_osm")
    ctx.cache[key] = []
    return []


def dem_providers(ctx: BuildContext, raw=None):
    from ..providers.dem import CopernicusDem, GpxDem

    cfg = ctx.config
    out = []
    for name in cfg.providers.dem:
        if name == "copernicus":
            out.append(CopernicusDem(cfg.endpoints.copernicus_dem, cfg.cache_dir, cfg.offline))
        elif name == "gpx":
            if raw is None:
                raw = read_parquet(ctx, "route_raw.parquet")
            try:
                out.append(GpxDem(raw["lat"], raw["lon"], raw["ele"]))
            except ProviderUnavailable:
                pass
    return out


def sample_dem(ctx: BuildContext, lat: np.ndarray, lon: np.ndarray, providers=None, record: bool = True):
    """Best available DEM height per point. Returns (z, provider index per point, providers)."""
    providers = providers if providers is not None else ctx.cache.setdefault("dem_providers", dem_providers(ctx))
    z = np.full(np.shape(lat), np.nan)
    src = np.full(np.shape(lat), -1, dtype=np.int16)
    for i, p in enumerate(providers):
        need = np.isnan(z)
        if not need.any():
            break
        if not p.available():
            continue
        try:
            zi = p.sample(lat[need], lon[need])
        except ProviderUnavailable as ex:
            if record:
                ctx.cache.setdefault("dem_errors", set()).add(f"{p.info.name}: {ex}")
            continue
        sub = z[need]
        ok = np.isfinite(zi)
        sub[ok] = zi[ok]
        z[need] = sub
        s2 = src[need]
        s2[ok] = i
        src[need] = s2
    if np.isnan(z).any():
        z = np.where(np.isnan(z), 0.0, z)
    return z, src, providers


def landcover_provider(ctx: BuildContext, features):
    from ..providers.landcover import OsmLandcover, WorldCover

    for name in ctx.config.providers.landcover:
        if name == "worldcover":
            wc = WorldCover(ctx.config.endpoints.worldcover, ctx.config.cache_dir, ctx.config.offline)
            if wc.available():
                return wc
        elif name == "osm":
            return OsmLandcover(features, ctx.frame, default_class=30)
    return OsmLandcover([], ctx.frame)


class CorridorRaster:
    """Lazy mosaic of the corridor GeoTIFF tiles in the local frame, with a far-field fallback for DEM."""

    def __init__(self, ctx: BuildContext, kind: str):
        import rasterio

        self.kind = kind
        self.tiles: dict[tuple[int, int], np.ndarray] = {}
        index = ctx.read_json("corridor/index.json")
        self.res = index["resM"]
        self.tile_m = index["tileM"]
        self.default = 30 if kind == "lc" else 0.0
        for t in index["tiles"]:
            p = ctx.path(f"corridor/{kind}/{t[0]}_{t[1]}.tif")
            with rasterio.open(p) as ds:
                self.tiles[(t[0], t[1])] = ds.read(1)
        self.far = None
        if kind == "dem" and ctx.path("corridor/dem_far.tif").exists():
            with rasterio.open(ctx.path("corridor/dem_far.tif")) as ds:
                self.far = (ds.read(1).astype(np.float64), ds.transform)

    def sample(self, x, y):
        from scipy.ndimage import map_coordinates

        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        shape = x.shape
        x = x.ravel()
        y = y.ravel()
        out = np.full(x.shape, np.nan)
        ti = np.floor(x / self.tile_m).astype(int)
        tj = np.floor(y / self.tile_m).astype(int)
        keys = ti * 100003 + tj
        n = int(self.tile_m / self.res)
        for k in np.unique(keys):
            sel = keys == k
            i, j = int(ti[sel][0]), int(tj[sel][0])
            arr = self.tiles.get((i, j))
            if arr is None:
                continue
            col = (x[sel] - i * self.tile_m) / self.res - 0.5
            row = ((j + 1) * self.tile_m - y[sel]) / self.res - 0.5
            if self.kind == "lc":
                r = np.clip(np.round(row).astype(int), 0, n - 1)
                c = np.clip(np.round(col).astype(int), 0, n - 1)
                out[sel] = arr[r, c]
            else:
                out[sel] = map_coordinates(arr.astype(np.float64), [row, col], order=1, mode="nearest")
        miss = np.isnan(out)
        if miss.any():
            if self.far is not None:
                arr, tr = self.far
                inv = ~tr
                c, r = inv * (x[miss], y[miss])
                out[miss] = map_coordinates(arr, [r - 0.5, c - 0.5], order=1, mode="nearest")
            else:
                out[miss] = self.default
        return out.reshape(shape)


def tile_bounds(i: int, j: int, tile_m: float = TILE_M):
    return i * tile_m, j * tile_m, (i + 1) * tile_m, (j + 1) * tile_m


def json_dump_compact(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode()


def round_list(a, nd=2):
    return [round(float(v), nd) for v in a]


def chunk_ranges(length: float, chunk_m: float):
    n = max(1, int(math.ceil(length / chunk_m - 1e-9)))
    return [(k, k * chunk_m, min(length, (k + 1) * chunk_m)) for k in range(n)]


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p
