"""Game-art chunk bake (headless Blender 5.x). One process bakes many chunks:

  blender -b --factory-startup --python bake_game_chunk.py -- --kit <kit_dir> --specs <game_dir> --out <game_dir> [--ids 0,1,2]

For each g<id>.json (gpx2course/gamekit/prep.py) writes g<id>.glb: terrain (multi-material, 6 m lattice), the course
road (crowned, UV along the road, Italian markings, kerbs + porphyry sidewalks in towns), side roads, buildings
(stucco/brick facades with window bays and persiane, ground-floor shopfronts in towns, hipped/gabled coppi roofs with
eaves). Materials carry kit material ids as names; no images are embedded — engines bind the shared kit textures
(UVs in metres, `repeat = 1/tileM`). Kit instances are not baked in: they ship as g<id>.json "instances" lists.
Also writes far.glb (textured far field) when --far is given.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402,I001
import bmesh  # noqa: E402
import mathutils  # noqa: E402

import kitlib  # noqa: E402
from kitlib import MeshBuilder  # noqa: E402


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True)
    p.add_argument("--specs", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--ids", default="")
    p.add_argument("--far", action="store_true")
    return p.parse_args(argv)


# ---- terrain ------------------------------------------------------------------------------------------------------


def build_terrain(spec, textured, col=None):
    t = spec["terrain"]
    G = t["gridM"]
    ox, oy, _ = spec["origin"]
    vz = {(v[0], v[1]): v[2] for v in t["vertices"]}
    mb = MeshBuilder(f"terrain_{spec['id']}")
    verts = {}

    def vert(i, j):
        key = (i, j)
        v = verts.get(key)
        if v is None:
            v = verts[key] = mb.bm.verts.new((i * G - ox, j * G - oy, vz[key]))
        return v

    mats = t["materials"]
    for i, j, m in t["cells"]:
        a, b, c, d = vert(i, j), vert(i + 1, j), vert(i + 1, j + 1), vert(i, j + 1)
        # Split along the shorter diagonal in height for a smoother surface
        if abs(a.co.z - c.co.z) <= abs(b.co.z - d.co.z):
            tris = ((a, b, c), (a, c, d))
        else:
            tris = ((a, b, d), (b, c, d))
        for tri in tris:
            try:
                f = mb.bm.faces.new(tri)
            except ValueError:
                continue
            f.material_index = mb.slot(mats[m])
            f.smooth = True
            for loop in f.loops:
                # World-metre UVs, wrapped per 96 m so chunk-local values stay small but continuous across chunks
                wx, wy = loop.vert.co.x + ox, loop.vert.co.y + oy
                loop[mb.uv].uv = (wx - math.floor(ox / 96) * 96, wy - math.floor(oy / 96) * 96)
    return mb.build(textured, col)


# ---- roads --------------------------------------------------------------------------------------------------------


def _frames(xs, ys):
    """Unit tangents and right normals along a polyline."""
    n = len(xs)
    out = []
    for k in range(n):
        a, b = max(0, k - 1), min(n - 1, k + 1)
        dx, dy = xs[b] - xs[a], ys[b] - ys[a]
        L = math.hypot(dx, dy) or 1.0
        out.append((dx / L, dy / L, dy / L, -dx / L))
    return out


def strip(mb, pts, offs_l, offs_r, dz_l, dz_r, mid, v0=0.0, u_l=None, u_r=None):
    """Ribbon between lateral offsets (metres, + = right of travel); UV: u across (metres), v along (metres)."""
    fr = _frames([p[0] for p in pts], [p[1] for p in pts])
    v = v0
    prev = None
    for k, (x, y, z) in enumerate(pts):
        if k:
            v += math.dist(pts[k - 1][:2], (x, y))
        _, _, nx, ny = fr[k]
        ol = offs_l[k] if isinstance(offs_l, list) else offs_l
        orr = offs_r[k] if isinstance(offs_r, list) else offs_r
        zl = dz_l[k] if isinstance(dz_l, list) else dz_l
        zr = dz_r[k] if isinstance(dz_r, list) else dz_r
        A = (x + nx * ol, y + ny * ol, z + zl)
        B = (x + nx * orr, y + ny * orr, z + zr)
        ua = ol if u_l is None else u_l
        ub = orr if u_r is None else u_r
        if prev:
            pa, pb, pv, pua, pub = prev
            mb.face([pa, pb, B, A], [(pua, pv), (pub, pv), (ub, v), (ua, v)], mid)
        prev = (A, B, v, ua, ub)
    return v


def cs(off, bank_deg, crown=0.02):
    """Cross-slope height at a lateral offset (+ right): crown blended into superelevation (gpx2course/roadgeom.py)."""
    t = math.tan(math.radians(bank_deg))
    w = min(1.0, abs(t) / 0.025)
    return (1 - w) * (-crown * abs(off)) + w * (-t * off)


def build_course_road(spec, textured, col=None):
    rd = spec["road"]
    n = len(rd["x"])
    bank = rd.get("bankDeg") or [0.0] * n
    pts = [(rd["x"][k], rd["y"][k], rd["z"][k] + 0.04) for k in range(n)]
    hw = [w / 2 for w in rd["width"]]
    v0 = rd["s"][0] % 96
    mb = MeshBuilder(f"road_{spec['id']}")
    # Surface runs by material; crowned 2 %
    start = 0
    for k in range(1, n + 1):
        if k == n or rd["material"][k] != rd["material"][start]:
            sl = slice(max(start - 1, 0), k)
            seg, h, bk = pts[sl], hw[sl], bank[sl]
            mid = rd["material"][start]
            v = (rd["s"][max(start - 1, 0)] % 96)
            strip(mb, seg, [-w for w in h], 0.0, [cs(-w, q) for w, q in zip(h, bk)], 0.0, mid, v)
            strip(mb, seg, 0.0, h, 0.0, [cs(w, q) for w, q in zip(h, bk)], mid, v)
            start = k
    # Italian markings: continuous white edge lines (12 cm, 25 cm in from the edge), dashed centre 4.5 m / 7.5 m gaps
    mk = MeshBuilder(f"markings_{spec['id']}")
    for side in (-1, 1):
        run = [k for k in range(n) if hw[k] * 2 >= 5.0]
        if len(run) > 1:
            groups, cur = [], [run[0]]
            for k in run[1:]:
                if k == cur[-1] + 1:
                    cur.append(k)
                else:
                    groups.append(cur)
                    cur = [k]
            groups.append(cur)
            for gk in groups:
                if len(gk) < 2:
                    continue
                strip(mk, [pts[k] for k in gk], [side * (hw[k] - 0.25) - 0.06 for k in gk], [side * (hw[k] - 0.25) + 0.06 for k in gk],
                      [cs(side * (hw[k] - 0.25) - 0.06, bank[k]) + 0.012 for k in gk], [cs(side * (hw[k] - 0.25) + 0.06, bank[k]) + 0.012 for k in gk],
                      "marking_white")
    for k in range(n - 1):
        if hw[k] * 2 >= 5.5 and (rd["s"][k] % 12.0) < 4.5:
            strip(mk, [pts[k], pts[k + 1]], -0.06, 0.06, 0.012, 0.012, "marking_white")
    # Verges to the terrain (rural) or kerb + porphyry sidewalk (towns)
    ter = rd["terrainZ"]
    vz = [ter[k] - pts[k][2] for k in range(n)]
    for side in (-1, 1):
        k = 0
        while k < n:
            j = k
            urb = rd["urban"][k] and not rd["bridge"][k]
            while j < n and (rd["urban"][j] and not rd["bridge"][j]) == urb:
                j += 1
            sl = list(range(max(k - 1, 0), j))
            seg = [pts[q] for q in sl]
            if len(seg) >= 2:
                e = [side * hw[q] for q in sl]
                edge_dz = [cs(side * hw[q], bank[q]) for q in sl]
                if urb:
                    # kerb face (15 cm), sidewalk 1.6 m, then down to terrain
                    o1 = [side * (hw[q] + 0.0) for q in sl]
                    o2 = [side * (hw[q] + 0.15) for q in sl]
                    o3 = [side * (hw[q] + 1.75) for q in sl]
                    o4 = [side * (hw[q] + 2.6) for q in sl]
                    top = [edge_dz[i] + 0.15 for i in range(len(sl))]
                    if side < 0:
                        strip(mb, seg, o2, o1, top, edge_dz, "kerb")
                        strip(mb, seg, o3, o2, top, top, "paving_porphyry")
                        strip(mb, seg, o4, o3, [vz[q] for q in sl], top, "urban_ground")
                    else:
                        strip(mb, seg, o1, o2, edge_dz, top, "kerb")
                        strip(mb, seg, o2, o3, top, top, "paving_porphyry")
                        strip(mb, seg, o3, o4, top, [vz[q] for q in sl], "urban_ground")
                else:
                    o_out = [side * (hw[q] + 2.2) for q in sl]
                    o_sh = [side * (hw[q] + 0.6) for q in sl]
                    # gravel shoulder then grass verge down to the terrain
                    if side < 0:
                        strip(mb, seg, o_sh, e, edge_dz, edge_dz, "gravel")
                        strip(mb, seg, o_out, o_sh, [vz[q] * 0.9 for q in sl], edge_dz, "grass_dry")
                    else:
                        strip(mb, seg, e, o_sh, edge_dz, edge_dz, "gravel")
                        strip(mb, seg, o_sh, o_out, edge_dz, [vz[q] * 0.9 for q in sl], "grass_dry")
            k = j
    objs = [mb.build(textured, col)]
    if mk.bm.faces:
        objs.append(mk.build(textured, col))
    else:
        mk.bm.free()
    return objs


def build_side_roads(spec, textured, col=None):
    mb = MeshBuilder(f"sideroads_{spec['id']}")
    for sr in spec["sideRoads"]:
        p = [tuple(q) for q in sr["pts"]]
        if len(p) < 2:
            continue
        w = sr["width"] / 2
        strip(mb, p, -w, w, 0.0, 0.0, sr["material"])
    if not mb.bm.faces:
        mb.bm.free()
        return []
    return [mb.build(textured, col)]


# ---- buildings ----------------------------------------------------------------------------------------------------


def _ccw(ring):
    a = sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring)))
    return ring if a > 0 else ring[::-1]


def build_buildings(spec, textured, col=None):
    mb = MeshBuilder(f"buildings_{spec['id']}")
    for b in spec["buildings"]:
        ring = _ccw([tuple(p) for p in b["ring"]])
        n = len(ring)
        z0 = b["z"]
        H = b["height"]
        pitch = math.radians(b.get("pitchDeg", 22))
        roof_type = b["roofType"]
        # Eave height: total height minus roof rise (approx. from the short side)
        area = abs(sum(ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1] for i in range(n)) / 2)
        perim = sum(math.dist(ring[i], ring[(i + 1) % n]) for i in range(n))
        inr = area / max(perim, 1e-6)
        rise = 0.0 if roof_type == "flat" else min(math.tan(pitch) * inr * 1.6, H * 0.35)
        eave = z0 + 0.3 + max(H - rise, 2.6)
        ground_split = z0 + 0.3 + 3.2 if b["wall"] != b["wallUpper"] else None
        # Walls: u = running length around the building, v = height above the ground floor line
        u = 0.0
        for i in range(n):
            a, c = ring[i], ring[(i + 1) % n]
            L = math.dist(a, c)
            if L < 0.05:
                continue
            bands = [(z0, ground_split, b["wall"]), (ground_split, eave, b["wallUpper"])] if ground_split and eave > ground_split + 0.3 else [(z0, eave, b["wallUpper"] if not ground_split else b["wall"])]
            for lo, hi, mid in bands:
                v_lo, v_hi = lo - (z0 + 0.3), hi - (z0 + 0.3)
                mb.face([(a[0], a[1], lo), (c[0], c[1], lo), (c[0], c[1], hi), (a[0], a[1], hi)], [(u, v_lo), (u + L, v_lo), (u + L, v_hi), (u, v_hi)], mid)
            u += L
        # Roof
        rr = _ccw([tuple(p) for p in b["roofRing"]]) if b["roofRing"] else ring
        roof_z = eave - (0.15 if rr is not ring else 0.0)
        tmp = bmesh.new()
        vs = [tmp.verts.new((p[0], p[1], roof_z)) for p in rr]
        try:
            top = tmp.faces.new(vs)
        except ValueError:
            tmp.free()
            continue
        if roof_type == "gabled" and len(rr) == 4:
            # Ridge along the long axis; gable ends closed with the upper wall material
            e0, e1 = math.dist(rr[0], rr[1]), math.dist(rr[1], rr[2])
            q = rr if e0 >= e1 else rr[1:] + rr[:1]
            short = min(e0, e1)
            rz = roof_z + math.tan(pitch) * short / 2
            m03 = ((q[0][0] + q[3][0]) / 2, (q[0][1] + q[3][1]) / 2, rz)
            m12 = ((q[1][0] + q[2][0]) / 2, (q[1][1] + q[2][1]) / 2, rz)
            bmesh.ops.delete(tmp, geom=[top], context="FACES_ONLY")
            A, C = tmp.verts.new(m03), tmp.verts.new(m12)
            V = [vs[rr.index(p)] for p in q]
            tmp.faces.new((V[0], V[1], C, A))
            tmp.faces.new((V[2], V[3], A, C))
            gable_ends = [(V[1], V[2], C), (V[3], V[0], A)]
        elif roof_type in ("hipped", "gabled") and len(rr) >= 3:
            r_area = abs(sum(rr[i][0] * rr[(i + 1) % len(rr)][1] - rr[(i + 1) % len(rr)][0] * rr[i][1] for i in range(len(rr))) / 2)
            r_per = sum(math.dist(rr[i], rr[(i + 1) % len(rr)]) for i in range(len(rr)))
            thick = 0.97 * r_area / max(r_per, 1e-6)
            bmesh.ops.inset_region(tmp, faces=[top], thickness=thick, depth=math.tan(pitch) * thick, use_even_offset=True)
            gable_ends = []
        else:
            gable_ends = []
        for tri in gable_ends:
            pts = [v.co.copy() for v in tri]
            base = (pts[1] - pts[0]).length
            mb.face([tuple(p) for p in pts], [(0, 0), (base, 0), (base / 2, pts[2].z - pts[0].z)], b["wallUpper"])
        # Underside/eave soffit (so eaves aren't see-through)
        for f in list(tmp.faces):
            nrm = f.normal
            mid = b["roof"]
            if nrm.z < 0.2 and roof_type != "flat":
                mid = b["wallUpper"] if b["roof"] != "greenhouse" else "greenhouse"
            # UV: u along the face's horizontal direction, v up the slope (metres)
            hdir = mathutils.Vector((-nrm.y, nrm.x, 0))
            if hdir.length < 1e-6:
                hdir = mathutils.Vector((1, 0, 0))
            hdir.normalize()
            vdir = nrm.cross(hdir).normalized()
            pts = [l.vert.co.copy() for l in f.loops]
            uvs = [(p.dot(hdir), p.dot(vdir)) for p in pts]
            mb.face([tuple(p) for p in pts], uvs, mid)
        tmp.free()
    if not mb.bm.faces:
        mb.bm.free()
        return []
    ob = mb.build(textured, col)
    return [ob]


# ---- far field ----------------------------------------------------------------------------------------------------


def build_far(far, textured, col=None, origin=(0.0, 0.0, 0.0), fills=True):
    """far_base: cells outside the near corridor; farfill_<chunk>: corridor cells per chunk (shown while that chunk's
    near geometry is not loaded — web streaming; Unreal loads every chunk and skips them)."""
    w, h = far["w"], far["h"]
    Z = far["z"]
    fill = far.get("fill") or [-1] * (w * h)
    builders = {}

    def mb_for(key):
        b = builders.get(key)
        if b is None:
            b = builders[key] = (MeshBuilder("far_base" if key < 0 else f"farfill_{key}"), {})
        return b

    for j in range(h):
        for i in range(w):
            c = j * w + i
            key = int(fill[c]) if far["skip"][c] else -1
            if key >= 0 and not fills:
                continue
            mb, verts = mb_for(key)

            def vert(ii, jj):
                k = (ii, jj)
                v = verts.get(k)
                if v is None:
                    v = verts[k] = mb.bm.verts.new((far["x0"] + ii * far["dx"] - origin[0], far["y0"] + jj * far["dy"] - origin[1],
                                                    Z[jj * (w + 1) + ii] - origin[2] - (0.6 if key >= 0 else 0.0)))
                return v

            q = [vert(i, j), vert(i + 1, j), vert(i + 1, j + 1), vert(i, j + 1)]
            try:
                f = mb.bm.faces.new(q[::-1] if far["dy"] < 0 else q)
            except ValueError:
                continue
            f.material_index = mb.slot(far["materials"][far["mat"][c]])
            f.smooth = True
            for loop in f.loops:
                loop[mb.uv].uv = (loop.vert.co.x, loop.vert.co.y)
    return [mb.build(textured, col) for mb, _ in builders.values() if mb.bm.faces]


def export(path, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_yup=True, export_extras=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_image_format="NONE", export_materials="EXPORT")


def build_chunk(spec, textured, col=None):
    objs = [build_terrain(spec, textured, col)]
    objs += build_course_road(spec, textured, col)
    objs += build_side_roads(spec, textured, col)
    objs += build_buildings(spec, textured, col)
    return objs


def main():
    a = args()
    index = json.load(open(os.path.join(a.specs, "index.json")))
    ids = [int(x) for x in a.ids.split(",") if x] or [c["id"] for c in index["chunks"]]
    os.makedirs(a.out, exist_ok=True)
    for cid in ids:
        kitlib.reset_scene()
        kitlib.load_kit(a.kit)
        spec = json.load(open(os.path.join(a.specs, f"g{cid}.json")))
        objs = build_chunk(spec, textured=False)
        export(os.path.join(a.out, f"g{cid}.glb"), objs)
        print(f"baked g{cid}", flush=True)
    if a.far:
        kitlib.reset_scene()
        kitlib.load_kit(a.kit)
        far = json.load(open(os.path.join(a.specs, "far.json")))
        export(os.path.join(a.out, "far.glb"), build_far(far, textured=False))
        print("baked far", flush=True)


if __name__ == "__main__":
    main()
