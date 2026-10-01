"""Stage 8 — quick tier: heightfield tiles, land-cover splat, vegetation instances and footprints for client-side generation."""
from __future__ import annotations

import hashlib
import io
import json
import math
import struct
from importlib import resources

import numpy as np
import shapely
from PIL import Image
from scipy.spatial import cKDTree
from shapely.geometry import shape

from ..pipeline import BuildContext
from .common import TILE_M, CorridorRaster, load_route

VERT_RES = 10.0
CATEGORIES = ["tree_deciduous", "tree_conifer", "tree_poplar", "hedge", "prop"]
INSTANCE_DTYPE = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("rot", "<f4"), ("scale", "<f4"), ("height", "<f4"),
                           ("category", "u1"), ("species", "u1"), ("flags", "<u2")])
PROP_SPECIES = {"km_post": 0, "flag": 1, "sign": 2}


def terrarium_png(z: np.ndarray) -> bytes:
    v = np.clip(z + 32768.0, 0, 65535.99)
    r = np.floor(v / 256)
    g = np.floor(v - r * 256)
    b = np.floor((v - np.floor(v)) * 256)
    img = Image.fromarray(np.dstack([r, g, b]).astype(np.uint8), "RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def gray_png(a: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(a.astype(np.uint8), "L").save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def _rng(*key) -> np.random.Generator:
    h = hashlib.sha256(json.dumps(key).encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "little"))


def flatten_under_road(X, Y, Z, route_tree, route_xyz, half_width):
    """Blend terrain to the road height within the road half width + 4 m (prevents DEM poking through the road)."""
    d, i = route_tree.query(np.c_[X.ravel(), Y.ravel()], distance_upper_bound=half_width.max() + 12)
    ok = np.isfinite(d)
    Zf = Z.ravel().copy()
    ii = i[ok]
    hw = half_width[ii]
    zr = route_xyz[ii, 2] - 0.05
    w = np.clip(1 - (d[ok] - hw) / 8.0, 0, 1)
    Zf[ok] = Zf[ok] * (1 - w) + zr * w
    return Zf.reshape(Z.shape)


def run(ctx: BuildContext) -> list[str]:
    r = load_route(ctx)
    dem = CorridorRaster(ctx, "dem")
    lc = CorridorRaster(ctx, "lc")
    idx = ctx.read_json("corridor/index.json")
    route_xyz = np.c_[r["x"], r["y"], r["z"]]
    route_tree = cKDTree(route_xyz[:, :2])
    half_w = r["roadWidthM"] / 2.0
    outs = []
    # ---- Heightfield tiles (vertex grids, seamless edges) ------------------------------------------
    n = int(TILE_M / VERT_RES) + 1
    c = np.arange(n) * VERT_RES
    tiles = []
    for k, (i, j) in enumerate(idx["tiles"]):
        X, Y = np.meshgrid(i * TILE_M + c, (j + 1) * TILE_M - c)
        Z = dem.sample(X, Y)
        Z = flatten_under_road(X, Y, Z, route_tree, route_xyz, half_w)
        L = lc.sample(X, Y)
        ctx.write_bytes(f"dem/{i}_{j}.png", terrarium_png(Z))
        ctx.write_bytes(f"lc/{i}_{j}.png", gray_png(L))
        tiles.append({"i": i, "j": j, "minZ": round(float(Z.min()), 2), "maxZ": round(float(Z.max()), 2)})
        outs += [f"dem/{i}_{j}.png", f"lc/{i}_{j}.png"]
        ctx.progress_frac(0.5 * (k + 1) / len(idx["tiles"]), "terrain tiles")
    far = idx["far"]
    import rasterio
    with rasterio.open(ctx.path("corridor/dem_far.tif")) as ds:
        zf = ds.read(1).astype(np.float64)
    ctx.write_bytes("dem/far.png", terrarium_png(zf))
    outs.append("dem/far.png")
    terrain = {"tiling": "local", "tileSizeM": TILE_M, "vertexSpacingM": VERT_RES, "verticesPerSide": n, "encoding": "terrarium",
               "demTiles": "dem/{i}_{j}.png", "landcoverTiles": "lc/{i}_{j}.png", "tiles": tiles,
               "far": {"file": "dem/far.png", "bounds": far["bounds"], "resM": far["resM"], "width": far["width"], "height": far["height"],
                       "pixelIsArea": True}}
    ctx.write_json("terrain.json", terrain)
    outs.append("terrain.json")

    # ---- Instances ------------------------------------------------------------------------------------
    ev = ctx.options.event_start
    recs = []
    veg = ctx.read_json("corridor/trees.geojson")["features"]
    blds = [shape(f["geometry"]) for f in ctx.read_json("corridor/buildings.geojson")["features"]]
    bld_tree = shapely.STRtree(blds) if blds else None
    route_line = shapely.LineString(route_xyz[:, :2])
    scatter_limit = 600.0

    def add(xs, ys, cat, heights, rng, species_n=4, flags=0):
        xs = np.asarray(xs, float)
        ys = np.asarray(ys, float)
        if len(xs) == 0:
            return
        d, ii = route_tree.query(np.c_[xs, ys])
        keep = d > half_w[ii] + 2.0
        if bld_tree is not None and keep.any():
            inside = np.zeros(len(xs), bool)
            pi, _ = bld_tree.query(shapely.points(xs, ys), predicate="within")
            inside[pi] = True
            keep &= ~inside
        xs, ys = xs[keep], ys[keep]
        h = np.broadcast_to(np.asarray(heights, float), keep.shape)[keep]
        m = len(xs)
        if m == 0:
            return
        a = np.zeros(m, INSTANCE_DTYPE)
        a["x"], a["y"] = xs, ys
        a["z"] = dem.sample(xs, ys)
        a["rot"] = rng.uniform(0, 2 * math.pi, m)
        a["scale"] = rng.uniform(0.85, 1.15, m)
        a["height"] = h * a["scale"]
        a["category"] = CATEGORIES.index(cat)
        a["species"] = rng.integers(0, species_n, m)
        a["flags"] = flags
        recs.append(a)

    for fi, f in enumerate(veg):
        p = f["properties"]
        g = shape(f["geometry"])
        h = float(p.get("_height", 15))
        rng = _rng("veg", fi)
        lt = (p.get("leaf_type") or "broadleaved").lower()
        if p.get("natural") == "tree":
            add([g.x], [g.y], "tree_conifer" if lt == "needleleaved" else "tree_deciduous", h, rng)
        elif p.get("natural") == "tree_row":
            spacing = 6.0 if p.get("species") == "poplar" else 8.0
            ds = np.arange(spacing / 2, g.length, spacing)
            pts = shapely.line_interpolate_point(g, ds + rng.uniform(-1, 1, len(ds)))
            cat = "tree_poplar" if p.get("species") == "poplar" else ("tree_conifer" if lt == "needleleaved" else "tree_deciduous")
            add(shapely.get_x(pts), shapely.get_y(pts), cat, h * rng.uniform(0.85, 1.1, len(ds)), rng)
        elif p.get("barrier") == "hedge":
            ds = np.arange(1.5, g.length, 3.0)
            pts = shapely.line_interpolate_point(g, ds)
            add(shapely.get_x(pts), shapely.get_y(pts), "hedge", h, rng)
        elif g.geom_type in ("Polygon", "MultiPolygon"):
            region = g.intersection(route_line.buffer(scatter_limit))
            if region.is_empty:
                continue
            spacing = 9.0
            minx, miny, maxx, maxy = region.bounds
            gx = np.arange(math.floor(minx / spacing) * spacing, maxx, spacing)
            gy = np.arange(math.floor(miny / spacing) * spacing, maxy, spacing)
            if len(gx) * len(gy) > 4_000_000:
                spacing *= math.sqrt(len(gx) * len(gy) / 4_000_000)
                gx = np.arange(minx, maxx, spacing)
                gy = np.arange(miny, maxy, spacing)
            X, Y = np.meshgrid(gx, gy)
            X = X.ravel() + rng.uniform(-spacing * 0.4, spacing * 0.4, X.size)
            Y = Y.ravel() + rng.uniform(-spacing * 0.4, spacing * 0.4, Y.size)
            inside = shapely.contains_xy(region, X, Y)
            cat = "tree_conifer" if lt == "needleleaved" else ("tree_deciduous" if lt == "broadleaved" else None)
            Xs, Ys = X[inside], Y[inside]
            if cat is None:
                mix = rng.random(len(Xs)) < 0.5
                add(Xs[mix], Ys[mix], "tree_conifer", h * rng.uniform(0.8, 1.1, mix.sum()), rng)
                add(Xs[~mix], Ys[~mix], "tree_deciduous", h * rng.uniform(0.8, 1.1, (~mix).sum()), rng)
            else:
                add(Xs, Ys, cat, h * rng.uniform(0.8, 1.1, len(Xs)), rng)
    # Props: km posts 4 m right of the road edge
    seg = ctx.read_json("segments.json")
    rng = _rng("props")
    kx, ky = [], []
    for kmk in seg["kmMarkers"]:
        i = min(int(round(kmk["s"] / r["spacing"])), r["count"] - 1)
        hd = r["headingRad"][i]
        off = half_w[i] + 1.5
        kx.append(r["x"][i] + math.cos(hd) * off)
        ky.append(r["y"][i] - math.sin(hd) * off)
    if kx:
        a = np.zeros(len(kx), INSTANCE_DTYPE)
        a["x"], a["y"] = kx, ky
        a["z"] = dem.sample(np.array(kx), np.array(ky))
        a["rot"] = [r["headingRad"][min(int(round(m["s"] / r["spacing"])), r["count"] - 1)] for m in seg["kmMarkers"]]
        a["scale"] = 1.0
        a["height"] = 1.2
        a["category"] = CATEGORIES.index("prop")
        a["species"] = PROP_SPECIES["km_post"]
        recs.append(a)
    inst = np.concatenate(recs) if recs else np.zeros(0, INSTANCE_DTYPE)
    order = np.lexsort((inst["y"], inst["x"], inst["category"])) if len(inst) else np.zeros(0, int)
    inst = inst[order]
    ctx.write_bytes("instances.bin", inst.tobytes())
    counts = {c: int((inst["category"] == k).sum()) for k, c in enumerate(CATEGORIES)}
    ctx.write_json("instances_meta.json", {"count": int(len(inst)), "recordBytes": INSTANCE_DTYPE.itemsize, "categories": CATEGORIES,
                                           "fields": [[nm, str(INSTANCE_DTYPE[nm])] for nm in INSTANCE_DTYPE.names], "counts": counts,
                                           "leafOn": _leaf_on(ctx)})
    outs += ["instances.bin", "instances_meta.json"]
    ctx.progress_frac(0.8, "footprints")

    # ---- Buildings / roads / water for client-side generation -----------------------------------------
    mid = route_line.buffer(ctx.config.tunables.mid_buffer_m)
    near = route_line.buffer(ctx.config.tunables.near_buffer_m)
    qb = []
    for f in ctx.read_json("corridor/buildings.geojson")["features"]:
        g = shape(f["geometry"])
        if not g.intersects(mid):
            continue
        polys = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
        p = f["properties"]
        for pg in polys:
            ring = np.asarray(pg.exterior.coords)[:-1]
            if len(ring) < 3:
                continue
            zg = dem.sample(ring[:, 0], ring[:, 1])
            qb.append({"h": p["_height"], "z": round(float(zg.min()), 2), "type": p.get("building", "yes"), "roof": p.get("roof:shape", "flat"),
                       "near": bool(pg.intersects(near)), "ring": np.round(ring, 2).tolist()})
    ctx.write_json("quick/buildings.json", {"buildings": qb})
    roads, water = [], []
    for f in ctx.read_json("corridor/osm.geojson")["features"]:
        p = f["properties"]
        g = shape(f["geometry"])
        if "highway" in p and g.geom_type == "LineString" and g.intersects(near):
            from ..surfaces import width_m
            gg = g.intersection(near.buffer(50))
            for part in getattr(gg, "geoms", [gg]):
                if part.geom_type == "LineString" and part.length > 5:
                    co = np.asarray(part.coords)
                    zz = dem.sample(co[:, 0], co[:, 1])
                    roads.append({"w": width_m(p), "surface": p.get("surface", ""), "pts": np.round(np.c_[co, zz], 2).tolist()})
        elif (p.get("natural") == "water" or "waterway" in p) and g.geom_type in ("Polygon", "MultiPolygon") and g.intersects(mid):
            gg = g.intersection(mid.buffer(500)).simplify(5)
            for part in getattr(gg, "geoms", [gg]):
                if part.geom_type == "Polygon" and part.area > 50:
                    ring = np.asarray(part.exterior.coords)[:-1]
                    zz = float(np.median(dem.sample(ring[:, 0], ring[:, 1])))
                    water.append({"z": round(zz, 2), "ring": np.round(ring, 1).tolist()})
    ctx.write_json("quick/roads.json", {"roads": roads})
    ctx.write_json("quick/water.json", {"water": water})
    mats = json.loads(resources.files("gpx2course").joinpath("data/materials.json").read_text())
    ctx.write_json("materials.json", mats, indent=1)
    outs += ["quick/buildings.json", "quick/roads.json", "quick/water.json", "materials.json"]
    return outs


def _leaf_on(ctx: BuildContext) -> bool:
    from ..models.wind import is_leaf_on

    ev = ctx.options.event_start
    return is_leaf_on(ev.month, ev.day, ctx.read_json("origin.json")["lat"]) if ev else True
