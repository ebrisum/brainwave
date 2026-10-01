"""Stage 4 — corridor: buffers, OSM features, DEM and land-cover rasters around the route only."""
from __future__ import annotations

import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import mapping

from ..pipeline import BuildContext
from ..providers.osm import is_building, is_forest, is_hedge, is_road, is_tree, is_tree_row, is_water
from .common import (FAR_RES_M, TILE_M, TILE_RES_M, dem_providers, ensure_dir, get_osm, json_dump_compact, landcover_provider, latlon_bbox,
                     load_route, sample_dem)

DEFAULT_BUILDING_HEIGHT = {"house": 7.0, "detached": 7.0, "semidetached_house": 8.0, "terrace": 9.0, "farm": 7.0, "barn": 8.0,
                           "farm_auxiliary": 6.0, "garage": 3.0, "shed": 3.0, "apartments": 15.0, "commercial": 12.0, "retail": 6.0,
                           "industrial": 9.0, "warehouse": 9.0, "church": 20.0, "cathedral": 35.0, "school": 10.0, "yes": 7.0}


def building_height(tags: dict) -> tuple[float, bool]:
    """(height m, known?) from height, building:levels×3 m, or a type default."""
    for k in ("height", "building:height"):
        v = tags.get(k)
        if v is not None:
            try:
                return max(2.0, float(str(v).split()[0].replace(",", "."))), True
            except ValueError:
                pass
    lv = tags.get("building:levels")
    if lv is not None:
        try:
            return max(3.0, float(lv) * 3.0 + (1.5 if tags.get("roof:shape", "flat") != "flat" else 0)), True
        except ValueError:
            pass
    return DEFAULT_BUILDING_HEIGHT.get(str(tags.get("building", "yes")), 7.0), False


def vegetation_height(tags: dict) -> float:
    v = tags.get("height")
    if v is not None:
        try:
            return float(v)
        except ValueError:
            pass
    if is_hedge(tags):
        return 2.0
    if is_tree_row(tags) or is_tree(tags):
        return 14.0
    return 20.0


def run(ctx: BuildContext) -> list[str]:
    t = ctx.config.tunables
    r = load_route(ctx)
    frame = ctx.frame
    line = shapely.LineString(np.c_[r["x"], r["y"]]).simplify(2.0)
    near = line.buffer(t.near_buffer_m, quad_segs=4)
    mid = line.buffer(t.mid_buffer_m, quad_segs=4)
    fetch = line.buffer(t.wind_fetch_m, quad_segs=4)
    ctx.progress_frac(0.05, "OSM features")
    bbox = latlon_bbox(r["lat"], r["lon"], t.wind_fetch_m + 200)
    feats = get_osm(ctx, bbox, "the corridor")
    # Keep features touching the wind-fetch zone
    keep = []
    if feats:
        geoms = np.array([f.geom_xy(frame) for f in feats], dtype=object)
        hit = shapely.intersects(geoms, fetch)
        keep = [f for f, h in zip(feats, hit) if h]
    buildings, vegetation, other = [], [], []
    no_height = 0
    for f in keep:
        g = f.geom_xy(frame)
        props = dict(f.tags)
        if is_building(f.tags):
            h, known = building_height(f.tags)
            no_height += not known
            props["_height"] = round(h, 2)
            props["_heightKnown"] = known
            buildings.append({"type": "Feature", "properties": props, "geometry": mapping(g)})
        elif is_tree(f.tags) or is_tree_row(f.tags) or is_hedge(f.tags) or is_forest(f.tags):
            props["_height"] = vegetation_height(f.tags)
            vegetation.append({"type": "Feature", "properties": props, "geometry": mapping(g)})
        elif is_road(f.tags) or is_water(f.tags) or "landuse" in f.tags or "natural" in f.tags or "railway" in f.tags or "junction" in f.tags:
            other.append({"type": "Feature", "properties": props, "geometry": mapping(g)})
    if buildings and no_height:
        ctx.warn(f"{no_height} of {len(buildings)} buildings have no height data; used type defaults", code="building_height_default",
                 count=no_height)
    ensure_dir(ctx.path("corridor"))
    crs = {"type": "name", "properties": {"name": "local:" + frame.proj}}
    ctx.write_bytes("corridor/buildings.geojson", json_dump_compact({"type": "FeatureCollection", "crs": crs, "features": buildings}))
    ctx.write_bytes("corridor/trees.geojson", json_dump_compact({"type": "FeatureCollection", "crs": crs, "features": vegetation}))
    ctx.write_bytes("corridor/osm.geojson", json_dump_compact({"type": "FeatureCollection", "crs": crs, "features": other}))
    ctx.write_bytes("corridor/zones.geojson", json_dump_compact({"type": "FeatureCollection", "crs": crs, "features": [
        {"type": "Feature", "properties": {"zone": z}, "geometry": mapping(g.simplify(5))} for z, g in (("near", near), ("mid", mid), ("fetch", fetch))]}))

    # ---- Rasters --------------------------------------------------------------------------------------
    ctx.progress_frac(0.2, "DEM and land cover tiles")
    minx, miny, maxx, maxy = fetch.bounds
    tiles = []
    for i in range(int(math.floor(minx / TILE_M)), int(math.floor(maxx / TILE_M)) + 1):
        for j in range(int(math.floor(miny / TILE_M)), int(math.floor(maxy / TILE_M)) + 1):
            if shapely.box(i * TILE_M, j * TILE_M, (i + 1) * TILE_M, (j + 1) * TILE_M).intersects(fetch):
                tiles.append((i, j))
    lc_provider = landcover_provider(ctx, feats)
    ctx.source("landcover", lc_provider.info)
    providers = dem_providers(ctx)
    npx = int(TILE_M / TILE_RES_M)
    ensure_dir(ctx.path("corridor/dem"))
    ensure_dir(ctx.path("corridor/lc"))
    cc = (np.arange(npx) + 0.5) * TILE_RES_M
    _TG.clear()
    _TG.update(frame=frame, providers=providers, lc=lc_provider, feats=feats, cc=cc, npx=npx, dir=str(ctx.dir),
               crs=ctx.cache.setdefault("crs_wkt", frame.crs_wkt()))
    workers = max(1, min(ctx.options.workers, len(tiles), os.cpu_count() or 1))
    fallback_msgs = set()
    if workers > 1:
        import multiprocessing as mp
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("fork")) as ex:
            for k, msg in enumerate(ex.map(_tile_work, tiles, chunksize=2)):
                if msg:
                    fallback_msgs.add(msg)
                ctx.progress_frac(0.2 + 0.6 * (k + 1) / len(tiles), f"tile {k + 1}/{len(tiles)}")
    else:
        for k, t_ in enumerate(tiles):
            msg = _tile_work(t_)
            if msg:
                fallback_msgs.add(msg)
            ctx.progress_frac(0.2 + 0.6 * (k + 1) / len(tiles), f"tile {k + 1}/{len(tiles)}")
    for msg in sorted(fallback_msgs):
        ctx.warn(f"land cover provider failed ({msg}); used OSM land use", code="landcover_fallback")
    _TG.clear()
    # Far field: terrain only, low resolution
    far = line.buffer(t.far_buffer_m, quad_segs=2)
    fminx, fminy, fmaxx, fmaxy = far.bounds
    fw = int(math.ceil((fmaxx - fminx) / FAR_RES_M))
    fh = int(math.ceil((fmaxy - fminy) / FAR_RES_M))
    X, Y = np.meshgrid(fminx + (np.arange(fw) + 0.5) * FAR_RES_M, fmaxy - (np.arange(fh) + 0.5) * FAR_RES_M)
    lat, lon = frame.to_latlon(X.ravel(), Y.ravel())
    zf, _, _ = sample_dem(ctx, lat, lon, providers)
    _write_tif(ctx, "corridor/dem_far.tif", zf.reshape(fh, fw).astype(np.float32), fminx, fmaxy, FAR_RES_M)
    ctx.write_json("corridor/index.json", {"tileM": TILE_M, "resM": TILE_RES_M, "tiles": tiles, "crs": frame.proj,
                                           "far": {"bounds": [fminx, fminy, fmaxx, fmaxy], "resM": FAR_RES_M, "width": fw, "height": fh},
                                           "buffers": {"near": t.near_buffer_m, "mid": t.mid_buffer_m, "far": t.far_buffer_m, "fetch": t.wind_fetch_m},
                                           "counts": {"buildings": len(buildings), "vegetation": len(vegetation), "other": len(other)}})
    outs = ["corridor/buildings.geojson", "corridor/trees.geojson", "corridor/osm.geojson", "corridor/zones.geojson", "corridor/index.json",
            "corridor/dem_far.tif"]
    outs += [f"corridor/dem/{i}_{j}.tif" for i, j in tiles] + [f"corridor/lc/{i}_{j}.tif" for i, j in tiles]
    return outs


_TG: dict = {}


def _tile_work(tile):
    """Sample DEM and land cover for one corridor tile (runs in a worker process)."""
    from ..providers.landcover import OsmLandcover

    i, j = tile
    g = _TG
    frame, npx, cc = g["frame"], g["npx"], g["cc"]
    X, Y = np.meshgrid(i * TILE_M + cc, (j + 1) * TILE_M - cc)
    lat, lon = frame.to_latlon(X.ravel(), Y.ravel())
    z = _sample_any(g["providers"], lat, lon)
    msg = None
    try:
        lc = g["lc"].sample(lat, lon)
    except Exception as ex:  # noqa: BLE001
        msg = str(ex)
        lc = OsmLandcover(g["feats"], frame).sample(lat, lon)
    d = Path(g["dir"])
    _write_tif_path(d / f"corridor/dem/{i}_{j}.tif", z.reshape(npx, npx).astype(np.float32), i * TILE_M, (j + 1) * TILE_M, TILE_RES_M, g["crs"])
    _write_tif_path(d / f"corridor/lc/{i}_{j}.tif", np.asarray(lc).reshape(npx, npx).astype(np.uint8), i * TILE_M, (j + 1) * TILE_M, TILE_RES_M, g["crs"])
    return msg


def _sample_any(providers, lat, lon):
    z = np.full(lat.shape, np.nan)
    for p in providers:
        need = np.isnan(z)
        if not need.any() or not p.available():
            continue
        try:
            zi = p.sample(lat[need], lon[need])
        except Exception:  # noqa: BLE001
            continue
        sub = z[need]
        ok = np.isfinite(zi)
        sub[ok] = zi[ok]
        z[need] = sub
    return np.where(np.isnan(z), 0.0, z)


def _write_tif(ctx: BuildContext, rel: str, arr: np.ndarray, west: float, north: float, res: float) -> None:
    _write_tif_path(ctx.path(rel), arr, west, north, res, ctx.cache.setdefault("crs_wkt", ctx.frame.crs_wkt()))


def _write_tif_path(p: Path, arr: np.ndarray, west: float, north: float, res: float, crs_wkt: str | None) -> None:
    import tempfile

    import rasterio
    from rasterio.transform import from_origin

    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=".tif")
    os.close(fd)
    profile = {"driver": "GTiff", "height": arr.shape[0], "width": arr.shape[1], "count": 1, "dtype": arr.dtype.name,
               "transform": from_origin(west, north, res, res), "compress": "deflate", "tiled": False}
    if crs_wkt:
        profile["crs"] = crs_wkt
    with rasterio.open(tmp, "w", **profile) as ds:
        ds.write(arr, 1)
    os.replace(tmp, p)
