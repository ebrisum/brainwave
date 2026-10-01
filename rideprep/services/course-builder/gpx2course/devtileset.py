"""Development stand-in for Google Photorealistic 3D Tiles: a 3D Tiles 1.1 tileset in ECEF built from the package's
own corridor DEM, land cover and buildings, with *ellipsoidal* heights (orthometric + a deliberate fake geoid offset).
It exercises the renderers' exact photoreal code path — ECEF placement, re-anchoring, vertical raycast calibration —
without an API key. `gpx2course dev-tileset <courseId>` writes <package>/devtiles/.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import shape

from .gltf import Mesh, write_glb

LC_RGB = {10: (0.13, 0.25, 0.10), 20: (0.35, 0.40, 0.22), 30: (0.40, 0.55, 0.25), 40: (0.62, 0.58, 0.32), 50: (0.55, 0.52, 0.48),
          60: (0.60, 0.55, 0.45), 80: (0.20, 0.30, 0.38), 90: (0.35, 0.45, 0.30)}
FAKE_GEOID_M = 46.5


def build(pkg: Path, step: int = 2) -> Path:
    import rasterio

    idx = json.loads((pkg / "corridor/index.json").read_text())
    proj = idx["crs"]
    to_ll = Transformer.from_crs(proj, "EPSG:4326", always_xy=True)
    to_ecef = Transformer.from_crs("EPSG:4979", "EPSG:4978", always_xy=True)
    out = pkg / "devtiles"
    out.mkdir(exist_ok=True)
    children = []
    blds = [(shape(f["geometry"]), f["properties"]) for f in json.loads((pkg / "corridor/buildings.geojson").read_text())["features"]]
    T, res = idx["tileM"], idx["resM"]
    for (i, j) in idx["tiles"]:
        with rasterio.open(pkg / f"corridor/dem/{i}_{j}.tif") as ds:
            z = ds.read(1)[::step, ::step].astype(np.float64)
        with rasterio.open(pkg / f"corridor/lc/{i}_{j}.tif") as ds:
            lc = ds.read(1)[::step, ::step]
        n = z.shape[0]
        cc = (np.arange(n) * step + 0.5) * res
        X, Y = np.meshgrid(i * T + cc, (j + 1) * T - cc)
        lon, lat = to_ll.transform(X.ravel(), Y.ravel())
        ex, ey, ez = to_ecef.transform(lon, lat, z.ravel() + FAKE_GEOID_M)
        P = np.c_[ex, ey, ez]
        C = P.mean(axis=0)
        rel = P - C
        col = np.array([LC_RGB.get(int(c), (0.4, 0.5, 0.3)) for c in lc.ravel()])
        k = np.arange((n - 1) * (n - 1))
        r, c = k // (n - 1), k % (n - 1)
        a = r * n + c
        tri = np.c_[a, a + n, a + 1, a + 1, a + n, a + n + 1].ravel().astype(np.uint32)
        meshes = [Mesh("terrain", "t", (rel @ np.diag([1, 1, 1]))[:, [0, 2, 1]] * [1, 1, -1], tri, colors=col)]
        # Buildings in this tile as boxes to the eave (walls only + flat roof)
        bp, bi, bc = [], [], []
        for g, p in blds:
            cx, cy = g.centroid.x, g.centroid.y
            if not (i * T <= cx < (i + 1) * T and j * T <= cy < (j + 1) * T):
                continue
            ring = np.asarray((g.geoms[0] if g.geom_type == "MultiPolygon" else g).exterior.coords)[:-1]
            rr = min(int((((j + 1) * T - cy) / res) // step), n - 1)
            cc_ = min(int(((cx - i * T) / res) // step), n - 1)
            z0 = float(z[rr, cc_])
            h = float(p.get("_height", 7))
            lo, la = to_ll.transform(np.r_[ring[:, 0], ring[:, 0]], np.r_[ring[:, 1], ring[:, 1]])
            hh = np.r_[np.full(len(ring), z0), np.full(len(ring), z0 + h)] + FAKE_GEOID_M
            bx, by, bz = to_ecef.transform(lo, la, hh)
            base = len(bp)
            m = len(ring)
            bp.extend((np.c_[bx, by, bz] - C).tolist())
            bc.extend([[0.6, 0.45, 0.38]] * m + [[0.75, 0.62, 0.55]] * m)
            for q in range(m):
                q2 = (q + 1) % m
                bi += [base + q, base + q2, base + m + q2, base + q, base + m + q2, base + m + q]
            for q in range(1, m - 1):
                bi += [base + m, base + m + q, base + m + q + 1]
        if bp:
            B = np.array(bp)
            meshes.append(Mesh("buildings", "b", B[:, [0, 2, 1]] * [1, 1, -1], np.array(bi, np.uint32), colors=np.array(bc)))
        mats = {"t": {"baseColor": [1, 1, 1], "roughness": 0.95}, "b": {"baseColor": [1, 1, 1], "roughness": 0.9}}
        name = f"{i}_{j}.glb"
        (out / name).write_bytes(write_glb(meshes, mats))
        radius = float(np.linalg.norm(rel, axis=1).max()) + 50
        children.append({"boundingVolume": {"sphere": [*C.tolist(), radius]}, "geometricError": 0, "refine": "ADD",
                         "content": {"uri": name}, "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, *C.tolist(), 1]})
    centers = np.array([c["transform"][12:15] for c in children])
    rc = centers.mean(axis=0)
    rr = float(max(np.linalg.norm(centers - rc, axis=1) + np.array([c["boundingVolume"]["sphere"][3] for c in children])))
    for c in children:  # bounding spheres are in the tile's (translated) frame
        c["boundingVolume"]["sphere"][:3] = [0, 0, 0]
    tileset = {"asset": {"version": "1.1", "copyright": "RidePrep dev stand-in (package data)"}, "geometricError": 500,
               "root": {"boundingVolume": {"sphere": [*rc.tolist(), rr]}, "geometricError": 200, "refine": "ADD", "children": children}}
    (out / "tileset.json").write_text(json.dumps(tileset))
    return out / "tileset.json"
