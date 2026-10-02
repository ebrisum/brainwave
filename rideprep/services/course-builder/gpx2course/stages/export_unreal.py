"""Stage 11 — export-unreal: 16-bit heightmap tiles, layer weight maps, road spline, instance lists, course_ue.json."""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

from ..coords import compass_to_ue_yaw_deg, enu_to_ue
from ..pipeline import BuildContext
from .common import CorridorRaster, load_route
from .quick import CATEGORIES, INSTANCE_DTYPE, flatten_under_road

# Unreal Landscape: a 505×505 heightmap (2×2 sections of 63 quads × 4 components) is one of the recommended sizes.
UE_TILE_PX = 505
UE_RES_M = 8.0
UE_RECOMMENDED = (127, 253, 505, 1009, 2017, 4033, 8129)
LAYERS = ["asphalt", "gravel", "grass", "crop", "forest_floor", "bare", "water"]
LC_TO_LAYER = {10: "forest_floor", 95: "forest_floor", 20: "grass", 30: "grass", 90: "grass", 100: "grass", 40: "crop", 50: "bare",
               60: "bare", 70: "bare", 80: "water"}
UE_INSTANCE_DTYPE = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("yawDeg", "<f4"), ("scale", "<f4"), ("height", "<f4"),
                              ("species", "<u2"), ("pad", "<u2")])


def png16(a: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(a.astype(np.uint16), "I;16").save(buf, format="PNG")
    return buf.getvalue()


def png8(a: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(a.astype(np.uint8), "L").save(buf, format="PNG")
    return buf.getvalue()


def run(ctx: BuildContext) -> list[str]:
    import shapely

    r = load_route(ctx)
    dem = CorridorRaster(ctx, "dem")
    lc = CorridorRaster(ctx, "lc")
    t = ctx.config.tunables
    route_xyz = np.c_[r["x"], r["y"], r["z"]]
    tree = cKDTree(route_xyz[:, :2])
    hw = r["roadWidthM"] / 2
    line = shapely.LineString(route_xyz[:, :2])
    zone = line.buffer(t.mid_buffer_m)
    tile_m = (UE_TILE_PX - 1) * UE_RES_M
    minx, miny, maxx, maxy = zone.bounds
    tiles = []
    for i in range(int(math.floor(minx / tile_m)), int(math.floor(maxx / tile_m)) + 1):
        for j in range(int(math.floor(miny / tile_m)), int(math.floor(maxy / tile_m)) + 1):
            if shapely.box(i * tile_m, j * tile_m, (i + 1) * tile_m, (j + 1) * tile_m).intersects(zone):
                tiles.append((i, j))
    # Global vertical mapping for all tiles
    zmin = float(r["z"].min()) - 200
    zmax = float(r["z"].max()) + 400
    offset_m = (zmin + zmax) / 2
    z_scale_cm = max(100.0, math.ceil((zmax - zmin) * 100 * 128 / 65000))
    unit_m = z_scale_cm / 128 / 100
    outs = []
    tile_meta = []
    c = np.arange(UE_TILE_PX) * UE_RES_M
    gravel_codes = {6, 7, 8}
    for k, (i, j) in enumerate(tiles):
        X, Y = np.meshgrid(i * tile_m + c, (j + 1) * tile_m - c)
        Z = flatten_under_road(X, Y, dem.sample(X, Y), tree, route_xyz, hw)
        H = np.clip(np.round((Z - offset_m) / unit_m + 32768), 0, 65535)
        name = f"heightmap_{i}_{j}.png"
        ctx.write_bytes(f"unreal/{name}", png16(H))
        outs.append(f"unreal/{name}")
        L = lc.sample(X, Y).astype(int)
        d, ii = tree.query(np.c_[X.ravel(), Y.ravel()], distance_upper_bound=40)
        on_road = np.isfinite(d) & (d <= hw[np.minimum(ii, len(hw) - 1)] + 0.5)
        road_gravel = on_road & np.isin(r["surfaceCode"][np.minimum(ii, len(hw) - 1)], list(gravel_codes))
        on_road = on_road.reshape(X.shape)
        road_gravel = road_gravel.reshape(X.shape)
        wfiles = {}
        for layer in LAYERS:
            mask = np.zeros(X.shape, bool)
            for cls, ly in LC_TO_LAYER.items():
                if ly == layer:
                    mask |= L == cls
            if layer == "asphalt":
                mask = on_road & ~road_gravel
            elif layer == "gravel":
                mask = road_gravel
            else:
                mask &= ~on_road
            if mask.any():
                fn = f"weights_{layer}_{i}_{j}.png"
                ctx.write_bytes(f"unreal/{fn}", png8(mask * 255))
                wfiles[layer] = fn
                outs.append(f"unreal/{fn}")
        ux, uy, _ = enu_to_ue(i * tile_m, (j + 1) * tile_m, 0)
        tile_meta.append({"i": i, "j": j, "heightmap": name, "weights": wfiles, "sizePx": UE_TILE_PX, "resolutionM": UE_RES_M,
                          "enuNorthWest": [i * tile_m, (j + 1) * tile_m], "ueLocationCm": [float(ux), float(uy), float(offset_m * 100)]})
        ctx.progress_frac((k + 1) / len(tiles) * 0.7, f"tile {k + 1}/{len(tiles)}")
    # Road spline every 10 m
    step = max(1, int(round(10 / r["spacing"])))
    sel = np.arange(0, r["count"], step)
    if sel[-1] != r["count"] - 1:
        sel = np.append(sel, r["count"] - 1)
    X, Y, Z = enu_to_ue(r["x"][sel], r["y"][sel], r["z"][sel])
    tx, ty = np.gradient(X), np.gradient(Y)
    tz = np.gradient(Z)
    pts = [{"s": round(float(r["s"][k]), 2), "p": [round(float(a), 1), round(float(b), 1), round(float(cc), 1)],
            "t": [round(float(a), 1), round(float(b), 1), round(float(cc), 1)], "widthCm": int(r["roadWidthM"][k] * 100),
            "bankDeg": round(float(r["bankDeg"][k]), 2) if "bankDeg" in r else 0.0, "surface": int(r["surfaceCode"][k])}
           for k, a, b, cc, *_ in zip(sel, X, Y, Z)]
    for p_, a, b, cc in zip(pts, tx, ty, tz):
        p_["t"] = [round(float(a), 1), round(float(b), 1), round(float(cc), 1)]
    ctx.write_json("unreal/road_spline.json", {"units": "cm", "spacingM": 10, "points": pts})
    outs.append("unreal/road_spline.json")
    # Instances per category
    inst = np.frombuffer(ctx.path("instances.bin").read_bytes(), dtype=INSTANCE_DTYPE)
    for k, cat in enumerate(CATEGORIES):
        sub = inst[inst["category"] == k]
        a = np.zeros(len(sub), UE_INSTANCE_DTYPE)
        a["x"], a["y"], a["z"] = enu_to_ue(sub["x"], sub["y"], sub["z"])
        a["yawDeg"] = compass_to_ue_yaw_deg(sub["rot"])
        a["scale"], a["height"], a["species"] = sub["scale"], sub["height"], sub["species"]
        ctx.write_bytes(f"unreal/instances_{cat}.bin", a.tobytes())
        outs.append(f"unreal/instances_{cat}.bin")
    o = ctx.read_json("origin.json")
    mats = ctx.read_json("materials.json")
    chunks = ctx.read_json("chunks/index.json")["chunks"] if ctx.path("chunks/index.json").exists() else []
    ue = {"version": 1, "origin": o, "units": "cm", "axes": "UE.X = E*100, UE.Y = -N*100, UE.Z = U*100 (left-handed, Z-up)",
          "landscape": {"tileSizePx": UE_TILE_PX, "resolutionM": UE_RES_M, "tileSizeM": tile_m, "zScaleCm": z_scale_cm, "offsetM": offset_m,
                        "heightFormula": "h_m = (value - 32768) * zScaleCm / 128 / 100 + offsetM", "layers": LAYERS, "tiles": tile_meta},
          "roadSpline": "road_spline.json",
          "instances": {cat: {"file": f"instances_{cat}.bin", "recordBytes": UE_INSTANCE_DTYPE.itemsize,
                              "fields": [[n, str(UE_INSTANCE_DTYPE[n])] for n in UE_INSTANCE_DTYPE.names]} for cat in CATEGORIES},
          "materials": {mid: f"/Game/RidePrep/Materials/MI_{mid}" for mid in mats["materials"]},
          "chunks": [{"id": ch["id"], "sStart": ch["sStart"], "sEnd": ch["sEnd"], "lod": ["../" + f for f in ch["lod"]],
                      "originUeCm": [float(v) for v in enu_to_ue(*ch["origin"])]} for ch in chunks],
          "farField": "../far_terrain.glb", "cesium": {"georeferenceOrigin": [o["lat"], o["lon"], o.get("hOrthometric", 0.0)],
                                                        "geoidUndulationM": o.get("geoidUndulation")}}
    ctx.write_json("unreal/course_ue.json", ue, indent=1)
    outs.append("unreal/course_ue.json")
    return outs
