"""Stage 6 — wind: per 10 m sample and 16 FROM-direction bins, precompute fRough, shelter, topo and channel factors."""
from __future__ import annotations

import math
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from ..models.wind import f_rough, is_leaf_on, porosity, shelter_r, z0_table
from ..pipeline import BuildContext
from .common import CorridorRaster, load_route

BINS = 16
LAYERS = ("fRough", "shelter", "topo", "channel")
RAY_OFFSETS_DEG = (-15.0, -7.5, 0.0, 7.5, 15.0)
SECTOR_OFFSETS_DEG = np.arange(-30, 31, 10, dtype=float)
FETCH_DIST = np.arange(300, 2001, 100, dtype=float)
OBST_RES = 4.0
BLOCK = 250  # route samples per work block (2.5 km)

_G: dict = {}  # per-process globals (populated before forking)


def _rasterize_block(x0, y0, x1, y1, buildings, vegetation, leaf_on):
    """Height, porosity and building-flag rasters for a block bbox at OBST_RES."""
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    import shapely

    w = int(math.ceil((x1 - x0) / OBST_RES))
    h = int(math.ceil((y1 - y0) / OBST_RES))
    tr = from_origin(x0, y1, OBST_RES, OBST_RES)
    box = shapely.box(x0, y0, x1, y1)
    H = np.zeros((h, w), dtype=np.float32)
    P = np.ones((h, w), dtype=np.float32)
    B = np.zeros((h, w), dtype=np.uint8)
    veg_shapes_h, veg_shapes_p = [], []
    for g, props in vegetation:
        if not g.intersects(box):
            continue
        tags = props
        hgt = float(props.get("_height", 15))
        if tags.get("natural") == "tree_row":
            kind, gg = "tree_row", g.buffer(3.0)
        elif tags.get("natural") == "tree":
            kind, gg = "single_tree", g.buffer(max(2.0, hgt * 0.25))
        elif tags.get("barrier") == "hedge":
            kind, gg = "hedge", g.buffer(1.0)
        else:
            kind, gg = "forest", g
        phi = porosity("single_tree" if kind == "single_tree" else ("hedge" if kind == "hedge" else "tree"), tags.get("leaf_type"), leaf_on)
        veg_shapes_h.append((gg, hgt))
        veg_shapes_p.append((gg, phi))
    bld_h, bld_p = [], []
    for g, props in buildings:
        if g.intersects(box):
            bld_h.append((g, float(props.get("_height", 7))))
            bld_p.append((g, 0.0))
    if veg_shapes_h:
        H = rasterize(veg_shapes_h, out_shape=(h, w), transform=tr, fill=0, dtype="float32")
        P = rasterize(veg_shapes_p, out_shape=(h, w), transform=tr, fill=1, dtype="float32")
    if bld_h:
        bh = rasterize(bld_h, out_shape=(h, w), transform=tr, fill=0, dtype="float32")
        m = bh > 0
        H[m] = bh[m]
        P[m] = 0.0
        B[m] = 1
    return H, P, B, tr


def _sample_grid(arr, x0, y1, xs, ys, fill):
    c = np.floor((xs - x0) / OBST_RES).astype(int)
    r = np.floor((y1 - ys) / OBST_RES).astype(int)
    ok = (r >= 0) & (r < arr.shape[0]) & (c >= 0) & (c < arr.shape[1])
    out = np.full(xs.shape, fill, dtype=arr.dtype)
    out[ok] = arr[r[ok], c[ok]]
    return out


def _work(block):
    a, b = block
    g = _G
    x = g["x"][a:b]
    y = g["y"][a:b]
    hd = g["heading"][a:b]
    n = len(x)
    out = np.ones((len(LAYERS), n, BINS), dtype=np.float32)
    lc: CorridorRaster = g["lc"]
    dem: CorridorRaster = g["dem"]
    z0t = g["z0t"]
    dirs = np.arange(BINS) * (360.0 / BINS)

    # ---- fRough --------------------------------------------------------------------------------------
    ang = np.radians(dirs[:, None, None] + SECTOR_OFFSETS_DEG[None, :, None])  # (16, 7, 1)
    dx = np.sin(ang) * FETCH_DIST[None, None, :]
    dy = np.cos(ang) * FETCH_DIST[None, None, :]
    w = np.exp(-FETCH_DIST / 500.0)[None, None, :] * np.ones_like(dx)
    px = x[:, None, None, None] + dx[None]
    py = y[:, None, None, None] + dy[None]
    cls = lc.sample(px, py).astype(np.int64)
    lnz = np.log(z0t[np.clip(cls, 0, 255)])
    z0eff = np.exp((lnz * w[None]).sum(axis=(2, 3)) / w.sum(axis=(1, 2))[None, :])
    out[0] = f_rough(np.minimum(z0eff, 0.30))

    # ---- shelter + channel -----------------------------------------------------------------------------
    ray_len = g["ray_len"]
    pad = ray_len + 10
    x0, x1 = x.min() - pad, x.max() + pad
    y0, y1 = y.min() - pad, y.max() + pad
    H, P, B, _ = _rasterize_block(x0, y0, x1, y1, g["buildings"], g["vegetation"], g["leaf_on"])
    if H.max() > 0:
        steps = np.arange(OBST_RES, ray_len + 1e-6, OBST_RES / 1.0)
        rang = np.radians(dirs[:, None] + np.array(RAY_OFFSETS_DEG)[None, :])  # (16, 5)
        for d in range(BINS):
            rx = x[:, None, None] + np.sin(rang[d])[None, :, None] * steps[None, None, :]
            ry = y[:, None, None] + np.cos(rang[d])[None, :, None] * steps[None, None, :]
            hh = _sample_grid(H, x0, y1, rx, ry, 0.0)
            pp = _sample_grid(P, x0, y1, rx, ry, 1.0)
            dist = np.broadcast_to(steps[None, None, :], hh.shape)
            r = shelter_r(dist, hh, pp)
            # Strongest shelter along each ray, averaged over the 5 rays of the ±15° fan (WIND_MODEL.md §3)
            out[1, :, d] = r.min(axis=2).mean(axis=1)
        # channel: buildings on both sides within 25 m
        offs = np.arange(6.0, 25.1, 3.0)
        nx, ny = np.cos(hd), -np.sin(hd)  # unit vector to the right of travel
        left = _sample_grid(B, x0, y1, x[:, None] - nx[:, None] * offs, y[:, None] - ny[:, None] * offs, 0).max(axis=1)
        right = _sample_grid(B, x0, y1, x[:, None] + nx[:, None] * offs, y[:, None] + ny[:, None] * offs, 0).max(axis=1)
        street = (left > 0) & (right > 0)
        if street.any():
            rel = np.abs(((dirs[None, :] - np.degrees(hd)[:, None]) + 90) % 180 - 90)  # angle to the street axis, 0..90
            out[3] = np.where(street[:, None] & (rel <= 30), 1.10, 1.0)

    # ---- topography ----------------------------------------------------------------------------------
    ring_a = np.radians(np.arange(16) * 22.5)
    zc = dem.sample(x, y)
    zr = dem.sample(x[:, None] + 500 * np.sin(ring_a)[None, :], y[:, None] + 500 * np.cos(ring_a)[None, :])
    tpi = zc - zr.mean(axis=1)
    tpi_n = np.clip(tpi / 30.0, -1, 1)
    wd = np.radians(dirs)
    zup = dem.sample(x[:, None] + 30 * np.sin(wd)[None, :], y[:, None] + 30 * np.cos(wd)[None, :])
    s_up = (zc[:, None] - zup) / 30.0  # >0: ground falls away upwind → windward slope
    crest = 1 + 0.12 * np.clip(tpi_n, 0, 1)[:, None] + 0.08 * np.clip(s_up / 0.1, 0, 1) * (tpi_n[:, None] >= 0)
    axis = np.degrees(ring_a[np.argmin(zr, axis=1)]) % 180
    alpha = np.abs(((dirs[None, :] - axis[:, None]) + 90) % 180 - 90)
    valley = np.where(alpha <= 30, 1 + 0.10 * np.abs(tpi_n)[:, None], 1 - 0.30 * np.abs(tpi_n)[:, None] * (alpha - 30) / 60)
    topo = np.where(tpi_n[:, None] >= 0, crest, valley)
    out[2] = np.clip(topo, 0.7, 1.2)
    return a, out


def run(ctx: BuildContext) -> list[str]:
    import shapely
    from shapely.geometry import shape

    r = load_route(ctx)
    t = ctx.config.tunables
    sp = t.wind_spacing_m
    L = r["s"][-1]
    sw = np.arange(0, L + 1e-6, sp)
    if sw[-1] < L - 1e-6:
        sw = np.append(sw, L)
    x = np.interp(sw, r["s"], r["x"])
    y = np.interp(sw, r["s"], r["y"])
    # heading: interpolate unit vectors
    hx = np.interp(sw, r["s"], np.sin(r["headingRad"]))
    hy = np.interp(sw, r["s"], np.cos(r["headingRad"]))
    heading = np.mod(np.arctan2(hx, hy), 2 * np.pi)
    ev = ctx.options.event_start
    month, day = (ev.month, ev.day) if ev else (7, 1)
    if not ev:
        ctx.warn("no event date; wind layers assume July (leaf-on, summer crops)", code="no_event_date")
    o = ctx.read_json("origin.json")
    leaf_on = is_leaf_on(month, day, o["lat"])
    blds = [(shape(f["geometry"]), f["properties"]) for f in ctx.read_json("corridor/buildings.geojson")["features"]]
    veg = [(shape(f["geometry"]), f["properties"]) for f in ctx.read_json("corridor/trees.geojson")["features"]]
    h_max = max([p.get("_height", 0) for _, p in blds + veg] + [1.0])
    ray_len = float(min(25 * h_max, 400.0))
    _G.clear()
    _G.update(x=x, y=y, heading=heading, lc=CorridorRaster(ctx, "lc"), dem=CorridorRaster(ctx, "dem"), z0t=z0_table(month),
              buildings=blds, vegetation=veg, leaf_on=leaf_on, ray_len=ray_len)
    n = len(sw)
    blocks = [(a, min(a + BLOCK, n)) for a in range(0, n, BLOCK)]
    out = np.ones((len(LAYERS), n, BINS), dtype=np.float32)
    workers = max(1, min(ctx.options.workers, len(blocks), os.cpu_count() or 1))
    done = 0
    if workers > 1:
        import multiprocessing as mp
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("fork")) as ex:
            for a, res in ex.map(_work, blocks):
                out[:, a:a + res.shape[1]] = res
                done += 1
                ctx.progress_frac(done / len(blocks), f"block {done}/{len(blocks)}")
    else:
        for blk in blocks:
            a, res = _work(blk)
            out[:, a:a + res.shape[1]] = res
            done += 1
            ctx.progress_frac(done / len(blocks), f"block {done}/{len(blocks)}")
    q = np.clip(np.round(out * 100), 0, 255).astype(np.uint8)
    ctx.write_bytes("wind.bin", q.tobytes())
    summary = {"count": n, "sampleSpacingM": sp, "directionBins": BINS, "layers": list(LAYERS), "encoding": "uint8 value*100",
               "layout": "layer-major: offset = (layer*count + sample)*bins + dirBin; bin d = FROM-direction d*22.5°",
               "month": month, "leafOn": leaf_on, "rayLengthM": ray_len,
               "mean": {name: round(float(out[k].mean()), 3) for k, name in enumerate(LAYERS)},
               "min": {name: round(float(out[k].min()), 3) for k, name in enumerate(LAYERS)}}
    ctx.write_json("wind_meta.json", summary)
    _G.clear()
    return ["wind.bin", "wind_meta.json"]
