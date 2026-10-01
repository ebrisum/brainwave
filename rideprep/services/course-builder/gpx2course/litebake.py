"""Pure-Python chunk baker (fallback when Blender is unavailable): road, markings, verges, railings, buildings, LODs.

Reads the same chunk input JSON as blender/bake_chunk.py and writes c{k}_lod{0,1,2}.glb.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import shapely

from .gltf import Mesh, enu_to_gltf, write_glb

BAKER_VERSION = "lite-2"


def _ribbon(x, y, z, nx, ny, left, right, dz_left=0.0, dz_right=0.0):
    """Triangle strip between offsets left/right (metres, + = right of travel)."""
    n = len(x)
    L = np.c_[x + nx * left, y + ny * left, z + dz_left]
    R = np.c_[x + nx * right, y + ny * right, z + dz_right]
    pos = np.empty((2 * n, 3))
    pos[0::2] = L
    pos[1::2] = R
    k = np.arange(n - 1)
    a, b, c, d = 2 * k, 2 * k + 1, 2 * k + 2, 2 * k + 3
    # Counter-clockwise when seen from above (z up) → front face up after the glTF axis swap
    idx = np.c_[a, b, c, b, d, c].ravel()
    return pos, idx


def _merge(parts):
    pos, idx, col, off = [], [], [], 0
    for p, i, c in parts:
        pos.append(p)
        idx.append(i + off)
        col.append(c if c is not None else np.ones((len(p), 3)))
        off += len(p)
    if not pos:
        return np.zeros((0, 3)), np.zeros(0, np.uint32), np.zeros((0, 3))
    return np.vstack(pos), np.concatenate(idx).astype(np.uint32), np.vstack(col)


def _box_along(x, y, z, nx, ny, off, w, h):
    """Rail/guard: a thin box (top + two vertical sides) following the polyline at lateral offset `off` (scalar or array)."""
    off = np.broadcast_to(np.asarray(off, float), x.shape)
    n = len(x)
    k = np.arange(n - 1)
    parts = [(*_ribbon(x, y, z, nx, ny, off - w / 2, off + w / 2, h, h), None)]
    for side, o in ((-1, off - w / 2), (1, off + w / 2)):
        P0 = np.c_[x + nx * o, y + ny * o, z]
        P1 = np.c_[x + nx * o, y + ny * o, z + h]
        pos = np.empty((2 * n, 3))
        pos[0::2] = P0
        pos[1::2] = P1
        idx = np.c_[2 * k, 2 * k + 2, 2 * k + 1, 2 * k + 1, 2 * k + 2, 2 * k + 3].ravel()  # faces right of travel
        if side < 0:
            idx = idx.reshape(-1, 3)[:, ::-1].ravel()
        parts.append((pos, idx, None))
    return _merge(parts)


def _building(ring: np.ndarray, z0: float, h: float, roof: str, lod: int):
    """Extruded footprint with flat or gabled roof. Returns (walls, roof) as (pos, idx, col)."""
    ring = np.asarray(ring, float)
    poly = shapely.Polygon(ring)
    if not poly.is_valid or poly.area < 4:
        return None
    if poly.exterior.is_ccw is False:
        ring = ring[::-1]
    gable = roof in ("gabled", "hipped", "pitched") and lod < 2
    mrr = poly.minimum_rotated_rectangle
    rect_like = poly.area / max(mrr.area, 1e-6) > 0.9
    if gable and rect_like:
        c = np.asarray(mrr.exterior.coords)[:4]
        e0 = np.linalg.norm(c[1] - c[0])
        e1 = np.linalg.norm(c[2] - c[1])
        if e0 < e1:
            c = np.roll(c, -1, axis=0)
            e0, e1 = e1, e0
        roof_h = min(0.4 * e1, h * 0.45)
        eave = max(h - roof_h, 2.5)
        ring = c
        if shapely.Polygon(ring).exterior.is_ccw is False:
            ring = ring[::-1]
    else:
        gable = False
        eave = h
    n = len(ring)
    # Walls: quads per edge, AO darker at the bottom
    wp, wi, wc = [], [], []
    for k in range(n):
        a, b = ring[k], ring[(k + 1) % n]
        base = len(wp)
        wp += [[a[0], a[1], z0], [b[0], b[1], z0], [b[0], b[1], z0 + eave], [a[0], a[1], z0 + eave]]
        wc += [[0.65] * 3, [0.65] * 3, [1.0] * 3, [1.0] * 3]
        wi += [base, base + 1, base + 2, base, base + 2, base + 3]
    rp, ri = [], []
    if gable:
        # ridge along the long axis (edges 0→1 and 2→3 are the long eaves)
        m03 = (ring[0] + ring[3]) / 2
        m12 = (ring[1] + ring[2]) / 2
        top = z0 + eave + roof_h
        P = [[*ring[0], z0 + eave], [*ring[1], z0 + eave], [*m12, top], [*m03, top], [*ring[2], z0 + eave], [*ring[3], z0 + eave]]
        rp = P
        ri = [0, 1, 2, 0, 2, 3, 4, 5, 3, 4, 3, 2]
        # gable end triangles (walls)
        base = len(wp)
        wp += [[*ring[1], z0 + eave], [*ring[2], z0 + eave], [*m12, top], [*ring[3], z0 + eave], [*ring[0], z0 + eave], [*m03, top]]
        wc += [[1.0] * 3] * 6
        wi += [base, base + 1, base + 2, base + 3, base + 4, base + 5]
    else:
        tris = shapely.constrained_delaunay_triangles(shapely.Polygon(ring)) if lod < 2 else None
        if tris is not None and not tris.is_empty:
            for t in tris.geoms:
                co = np.asarray(t.exterior.coords)[:3]
                if shapely.Polygon(co).exterior.is_ccw is False:
                    co = co[::-1]
                base = len(rp)
                rp += [[c[0], c[1], z0 + eave] for c in co]
                ri += [base, base + 1, base + 2]
        else:
            # fan (fine for convex/near-convex boxes at LOD2)
            base = len(rp)
            rp += [[c[0], c[1], z0 + eave] for c in ring]
            for k in range(1, n - 1):
                ri += [base, base + k, base + k + 1]
    walls = (np.array(wp), np.array(wi, np.uint32), np.array(wc))
    roofm = (np.array(rp).reshape(-1, 3), np.array(ri, np.uint32), np.ones((len(rp), 3)))
    return walls, roofm, gable


FACADE = {"house": "facade_brick", "detached": "facade_brick", "terrace": "facade_brick", "church": "facade_brick", "barn": "facade_barn",
          "farm_auxiliary": "facade_barn", "shed": "facade_barn", "apartments": "facade_plaster", "commercial": "facade_plaster"}


def bake_chunk(spec: dict, out_dir: Path, materials: dict) -> list[str]:
    ox, oy, oz = spec["origin"]
    rt = spec["route"]
    x = np.array(rt["x"]) - ox
    y = np.array(rt["y"]) - oy
    z = np.array(rt["z"]) - oz
    hd = np.array(rt["heading"])
    w = np.array(rt["width"], float)
    surf = np.array(rt["surface"], int)
    bridge = np.array(rt["bridge"], bool)
    terr = np.array(rt["terrainZ"]) - oz
    nx, ny = np.cos(hd), -np.sin(hd)
    s2m = materials.get("surfaceCodeToMaterial", {})
    red = spec.get("redCycleways", False)
    cyc = np.array(rt["cycleway"], bool)
    files = []
    for lod in (0, 1, 2):
        step = (1, 2, 4)[lod]
        sel = np.arange(0, len(x), step)
        if sel[-1] != len(x) - 1:
            sel = np.append(sel, len(x) - 1)
        X, Y, Z, NX, NY, W = x[sel], y[sel], z[sel], nx[sel], ny[sel], w[sel]
        meshes: list[Mesh] = []
        # Road surface split into runs by material
        mats = np.array([("road_asphalt_red" if (red and cyc[i] and surf[i] in (0, 1)) else s2m.get(str(surf[i]), "road_asphalt")) for i in sel])
        a = 0
        for i in range(1, len(sel) + 1):
            if i == len(sel) or mats[i] != mats[a]:
                b = min(i, len(sel) - 1)
                if b > a:
                    cs = slice(a, b + 1)
                    hw = W[cs] / 2
                    # camber: edges 2 % lower; two halves so the crown is in the middle
                    p1, i1 = _ribbon(X[cs], Y[cs], Z[cs] + 0.03, NX[cs], NY[cs], -hw, np.zeros_like(hw), -0.02 * hw, 0.0)
                    p2, i2 = _ribbon(X[cs], Y[cs], Z[cs] + 0.03, NX[cs], NY[cs], np.zeros_like(hw), hw, 0.0, -0.02 * hw)
                    pos, idx, col = _merge([(p1, i1, None), (p2, i2, None)])
                    meshes.append(Mesh(f"road_{a}", str(mats[a]), enu_to_gltf(pos[:, 0], pos[:, 1], pos[:, 2]), idx, colors=col))
                a = i
        # Markings (LOD0 only), per regional style: edge lines solid/dashed/none, centre dashed/none
        mk = spec.get("markings") or {"edge": "solid", "centre": "dashed"}
        if lod == 0:
            wide = W >= 5.0
            parts = []
            ss_all = np.array(rt["s"])[sel]
            for side in (-1, 1) if mk.get("edge", "solid") != "none" else ():
                off = side * (W / 2 - 0.35)
                m = wide & ~np.array([cyc[i] for i in sel])
                if mk.get("edge") == "dashed":
                    m &= np.mod(ss_all, 4.5) < 3.0
                if m.sum() > 1:
                    for run in _runs(m):
                        cs = slice(run[0], run[1])
                        if run[1] - run[0] > 1:
                            parts.append(_ribbon(X[cs], Y[cs], Z[cs] + 0.045, NX[cs], NY[cs], off[cs] - 0.06, off[cs] + 0.06) + (None,))
            centre = (W >= 5.5) & (mk.get("centre", "dashed") != "none")
            ss = np.array(rt["s"])[sel]
            dash = (np.mod(ss, 12.0) < 3.0) & centre
            for run in _runs(dash):
                if run[1] - run[0] >= 1:
                    cs = slice(run[0], min(run[1] + 1, len(sel)))
                    if cs.stop - cs.start > 1:
                        parts.append(_ribbon(X[cs], Y[cs], Z[cs] + 0.05, NX[cs], NY[cs], -0.06, 0.06) + (None,))
            if parts:
                pos, idx, col = _merge(parts)
                meshes.append(Mesh("markings", "marking_white", enu_to_gltf(pos[:, 0], pos[:, 1], pos[:, 2]), idx))
        # Verges: 3 m strip from road edge down/up to the terrain
        if lod < 2:
            T = terr[sel]
            parts = []
            for side in (-1, 1):
                hw = W / 2
                inner = side * hw
                outer = side * (hw + 3.0)
                lo, hi = (outer, inner) if side < 0 else (inner, outer)
                dz_in = np.zeros_like(hw) - 0.02 * hw
                dz_out = (T - Z) * 0.9
                p, i = _ribbon(X, Y, Z, NX, NY, lo, hi, dz_out if side < 0 else dz_in, dz_in if side < 0 else dz_out)
                parts.append((p, i, np.full((len(p), 3), 0.9)))
            pos, idx, col = _merge(parts)
            meshes.append(Mesh("verges", "verge_grass", enu_to_gltf(pos[:, 0], pos[:, 1], pos[:, 2]), idx, colors=col))
        # Bridge railings
        if lod < 2 and bridge[sel].any():
            for run in _runs(bridge[sel]):
                cs = slice(max(run[0] - 1, 0), min(run[1] + 1, len(sel)))
                if cs.stop - cs.start < 2:
                    continue
                parts = []
                for side in (-1, 1):
                    parts.append(_box_along(X[cs], Y[cs], Z[cs], NX[cs], NY[cs], side * (W[cs] / 2 + 0.3), 0.08, 1.1))
                pos, idx, col = _merge([(p, i, c) for p, i, c in parts])
                meshes.append(Mesh("railing", "metal_rail", enu_to_gltf(pos[:, 0], pos[:, 1], pos[:, 2]), idx))
        # Buildings
        groups: dict[str, list] = {}
        for bi, b in enumerate(spec["buildings"]):
            if lod == 2 and b["h"] < 5:
                continue
            ring = np.array(b["ring"]) - [ox, oy]
            res = _building(ring, b["z"] - oz, b["h"], b.get("roof", "flat"), lod)
            if res is None:
                continue
            walls, roofm, gable = res
            groups.setdefault(FACADE.get(b.get("type", "yes"), "facade_plaster"), []).append(walls)
            groups.setdefault("roof_tile" if gable else "roof_flat", []).append(roofm)
        for mat, parts in sorted(groups.items()):
            pos, idx, col = _merge(parts)
            if len(idx):
                meshes.append(Mesh(f"buildings_{mat}", mat, enu_to_gltf(pos[:, 0], pos[:, 1], pos[:, 2]), idx, colors=col))
        glb = write_glb(meshes, materials.get("materials", {}), extras={"chunk": spec["id"], "lod": lod, "origin": spec["origin"],
                                                                         "frame": "glTF Y-up; position = ENU(x, z, -y) relative to origin",
                                                                         "baker": BAKER_VERSION})
        name = f"c{spec['id']}_lod{lod}.glb"
        tmp = out_dir / f".{name}.tmp"
        tmp.write_bytes(glb)
        tmp.replace(out_dir / name)
        files.append(name)
    return files


def _runs(mask):
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            yield (i, j)
            i = j
        else:
            i += 1


def bake_far_terrain(z: np.ndarray, bounds, origin, max_verts: int = 200) -> bytes:
    h, w = z.shape
    step = max(1, int(math.ceil(max(h, w) / max_verts)))
    zz = z[::step, ::step]
    hh, ww = zz.shape
    minx, miny, maxx, maxy = bounds
    xs = np.linspace(minx, maxx, ww)
    ys = np.linspace(maxy, miny, hh)
    X, Y = np.meshgrid(xs, ys)
    pos = np.c_[X.ravel() - origin[0], Y.ravel() - origin[1], zz.ravel() - origin[2] - 0.5]
    k = np.arange((hh - 1) * (ww - 1))
    r, c = k // (ww - 1), k % (ww - 1)
    a = r * ww + c
    idx = np.c_[a, a + ww, a + 1, a + 1, a + ww, a + ww + 1].ravel().astype(np.uint32)
    m = Mesh("far_terrain", "terrain_grass", enu_to_gltf(pos[:, 0], pos[:, 1], pos[:, 2]), idx)
    mats = json.loads((Path(__file__).parent / "data" / "materials.json").read_text())["materials"]
    return write_glb([m], mats, extras={"origin": list(origin), "kind": "far_terrain"})
