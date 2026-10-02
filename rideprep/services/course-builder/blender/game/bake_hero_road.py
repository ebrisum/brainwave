"""Hero road for Unreal (Nanite): the course carriageway and gravel shoulders as dense, displaced geometry.

  blender -b --factory-startup --python bake_hero_road.py -- --kit <kit_dir> --specs <specs_dir> --out <game/unreal/hero>
      [--ids 88,89,90] [--along 0.24] [--fine 0.03] [--shoulder 0.05] [--render <shot.jpg> [--at <s>]]

The streaming chunks (bake_game_chunk.py) carry a light road with decals; this bake is what Nanite is for. Per chunk:
  h<id>.glb           hero_road_<id>     carriageway on a 24 × ~12 cm lattice, refined to ~3 × 1.5 cm wherever a defect
                                         is: potholes (bowls with steep walls and a rough bottom), repair patches
                                         (raised, bevelled), sealed and open cracks, crumbled edges; edge lines and
                                         centre dashes are faces of the surface, so paint follows every dip
                      hero_shoulder_<id> gravel shoulders (shoulder_gravel) on a 5 cm lattice with stone relief, tucked 3 cm under the
                                         road edge and the verge so there are no seams
  h<id>_pebbles.json  loose stones on the shoulders and around potholes: {"pebble_a": [[x, y, z, rotZ, scale], …], …}
  pebbles.glb         the three pebble meshes (kit material "gravel")
Same frame and material naming as g<id>.glb (chunk-local ENU, kit material ids). The chunk range is exactly
[sStart, sEnd] and defects of the neighbouring chunks are included, so hero chunks join without seams. Engines swap
the chunk's road_/markings_/defects_/shoulder_ meshes for these.
"""
import argparse
import bisect
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402,I001
import bmesh  # noqa: E402

import kitlib  # noqa: E402
import roadfx  # noqa: E402
from kitlib import MeshBuilder  # noqa: E402

EDGE_LINE = (0.19, 0.31)   # edge line: 12 cm wide, its centre 25 cm in from the edge (same as the chunk bake)
CENTRE_HALF = 0.06          # centre dashes: 12 cm wide
DASH, PERIOD = 4.5, 12.0     # 4.5 m dashes every 12 m


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True)
    p.add_argument("--specs", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--ids", default="")
    p.add_argument("--along", type=float, default=0.24)
    p.add_argument("--across", type=float, default=0.125)
    p.add_argument("--fine", type=float, default=0.03)
    p.add_argument("--shoulder", type=float, default=0.05)
    p.add_argument("--render", default="")
    p.add_argument("--at", type=float, default=None, help="render: route distance to look at (default: the chunk's deepest pothole)")
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--view", default="low", choices=["low", "rider"])
    p.add_argument("--sun-elev", type=float, default=30.0)
    p.add_argument("--sun-az", type=float, default=115.0)
    return p.parse_args(argv)


# ---- carriageway -----------------------------------------------------------------------------------------------------


def columns(hw_max, across):
    """Lateral columns as functions of the local half-width: edge-anchored ones keep the edge lines exact as the road
    narrows or widens, the rest are spread evenly between the edge lines and the centre dashes."""
    cols = []
    for side in (-1, 1):
        for d in (0.0, 0.05, EDGE_LINE[0], EDGE_LINE[1]):
            cols.append(("edge", side, d))
        n_in = max(1, math.ceil((hw_max - EDGE_LINE[1] - CENTRE_HALF) / across))
        for k in range(1, n_in):
            cols.append(("frac", side, k / n_in))
        cols.append(("centre", side, CENTRE_HALF))
    return cols


def col_off(c, hw):
    kind, side, v = c
    if kind == "edge":
        return side * (hw - v)
    if kind == "centre":
        return side * v
    inner, outer = CENTRE_HALF, hw - EDGE_LINE[1]
    return side * (outer + (inner - outer) * v)


def marking_at(s, off, hw):
    a = abs(off)
    if hw * 2 >= 5.0 and hw - EDGE_LINE[1] <= a <= hw - EDGE_LINE[0]:
        return True
    return hw * 2 >= 5.5 and a <= CENTRE_HALF and (s % PERIOD) < DASH


def build_carriageway(cid, rd, cl, surf, s0, s1, a):
    hw_at = lambda s: cl.frame(s)[8]  # noqa: E731
    mats_s = rd["s"]

    def base_mat(s):
        k = min(max(bisect.bisect_right(mats_s, s) - 1, 0), len(mats_s) - 1)
        return rd["material"][k]

    hw_max = max(rd["width"]) / 2
    cols = sorted(columns(hw_max, a.across), key=lambda c: col_off(c, hw_max))
    n_rows = max(1, math.ceil((s1 - s0) / a.along))
    rows = [s0 + (s1 - s0) * k / n_rows for k in range(n_rows + 1)]
    bm = bmesh.new()
    grid = []
    for s in rows:
        hw = hw_at(s)
        grid.append([bm.verts.new((s, col_off(c, hw), 0.0)) for c in cols])
    faces = []
    for r in range(n_rows):
        for q in range(len(cols) - 1):
            v = (grid[r][q], grid[r][q + 1], grid[r + 1][q + 1], grid[r + 1][q])
            faces.append(bm.faces.new(v))
    # Refine every lattice cell a defect touches (never the first/last row: chunk seams stay identical)
    fine_edges = set()
    for f in faces:
        ss = [v.co.x for v in f.verts]
        oo = [v.co.y for v in f.verts]
        if min(ss) <= s0 + 1e-6 or max(ss) >= s1 - 1e-6:
            continue
        if surf.overlaps(min(ss), max(ss), min(oo) - 0.01, max(oo) + 0.01):
            fine_edges.update(f.edges)
    if fine_edges:
        cuts = max(1, math.ceil(a.along / a.fine) - 1)
        bmesh.ops.subdivide_edges(bm, edges=list(fine_edges), cuts=cuts, use_grid_fill=True)
    # Materials from the flat (s, off) layout, then displace and map onto the road
    slots = []

    def slot(mid):
        if mid not in slots:
            slots.append(mid)
        return slots.index(mid)

    uv = bm.loops.layers.uv.new("UVMap")
    v_base = 96.0 * math.floor(s0 / 96.0)  # metre UVs, continuous inside the chunk (same wrap as the chunk bake)
    for f in bm.faces:
        c = f.calc_center_median()
        s, o = c.x, c.y
        hw = hw_at(s)
        mid = surf.material(s, o)
        if mid is None and marking_at(s, o, hw):
            mid = "marking_white"
        f.material_index = slot(mid or base_mat(s))
        f.smooth = True
        for loop in f.loops:
            loop[uv].uv = (loop.vert.co.y, loop.vert.co.x - v_base)
    for v in bm.verts:
        s, o = v.co.x, v.co.y
        v.co = cl.point(s, o, surf.height(s, o))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:  # all up
        if f.normal.z < 0:
            f.normal_flip()
    return _object(f"hero_road_{cid}", bm, slots)


# ---- shoulders --------------------------------------------------------------------------------------------------------


def build_shoulders(cid, rd, cl, surf, s0, s1, a, seed):
    widths = rd.get("shoulder") or []
    if not widths or max(widths) < 0.1:
        return None
    ss_ = rd["s"]
    w_at = lambda s: widths[min(max(bisect.bisect_right(ss_, s) - 1, 0), len(widths) - 1)]  # noqa: E731
    step = a.shoulder
    n_rows = max(1, math.ceil((s1 - s0) / step))
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    v_base = 96.0 * math.floor(s0 / 96.0)
    tuck = 0.03
    for side in (-1, 1):
        prev = None
        for k in range(n_rows + 1):
            s = s0 + (s1 - s0) * k / n_rows
            w = w_at(s)
            if w < 0.1:
                prev = None
                continue
            x, y, z, _, _, nx, ny, bank, hw = cl.frame(s)
            n_c = max(2, math.ceil((w + 2 * tuck) / step) + 1)
            row = []
            for j in range(n_c):
                d = -tuck + (w + 2 * tuck) * j / (n_c - 1)   # metres out from the road edge
                off = side * (hw + d)
                fade = max(0.0, min(1.0, d / 0.06, (w - d) / 0.06))
                dz = roadfx.stone_height(s, off, seed) * fade + surf.height(s, side * hw) * max(0.0, 1 - d / 0.12)
                if d < 0 or d > w:
                    dz -= 0.003  # tucked under the road edge / the verge
                z_edge = z + roadfx.Centreline.LIFT + roadfx.cs(side * hw, bank)
                row.append((bm.verts.new((x + nx * off, y + ny * off, z_edge + dz)), off, s))
            if prev is not None and len(prev) == len(row):
                for j in range(len(row) - 1):
                    q = [prev[j], prev[j + 1], row[j + 1], row[j]]
                    try:
                        f = bm.faces.new([t[0] for t in q])
                    except ValueError:
                        continue
                    f.smooth = True
                    for loop, t in zip(f.loops, q):
                        loop[uv].uv = (t[1], t[2] - v_base)
            prev = row
    if not bm.faces:
        bm.free()
        return None
    for f in bm.faces:
        if f.normal.z < 0:
            f.normal_flip()
    return _object(f"hero_shoulder_{cid}", bm, ["shoulder_gravel"])


# ---- loose stones -----------------------------------------------------------------------------------------------------


def pebbles(rd, cl, surf, s0, s1, seed, per_m2=4.0):
    """Instance rows for loose stones: on the shoulders, and kicked out of potholes and crumbled edges."""
    out = {"pebble_a": [], "pebble_b": [], "pebble_c": []}
    rnd = random.Random(seed)
    keys = list(out)
    widths = rd.get("shoulder") or []
    ss_ = rd["s"]

    def put(s, off, lift=0.0):
        px, py, pz = cl.point(s, off, surf.height(s, off) + lift)
        k = rnd.randrange(3)
        sc = 0.6 + 0.8 * rnd.random()
        # sit on the surface: the meshes' flat bottoms are 0.35 × their half-height below their origin
        out[keys[k]].append([round(px, 3), round(py, 3), round(pz + 0.3 * PEBBLE_HALF[k][2] * sc, 4), round(rnd.random() * math.tau, 3), round(sc, 2)])

    if widths:
        s = s0
        while s < s1:
            w = widths[min(max(bisect.bisect_right(ss_, s) - 1, 0), len(widths) - 1)]
            if w >= 0.1:
                hw = cl.frame(s)[8]
                for side in (-1, 1):
                    n = int(per_m2 * w + rnd.random())
                    for _ in range(n):
                        d = rnd.random() * w
                        put(s + rnd.random(), side * (hw + d), roadfx.stone_height(s, side * (hw + d), seed))
            s += 1.0
    for kind, d, geo, _ in surf.items:
        if not (s0 <= d["s"] < s1):
            continue
        if kind == "pothole":
            for _ in range(rnd.randint(6, 14)):
                ang, r = rnd.random() * math.tau, d["len"] / 2 + 0.05 + rnd.random() * 0.5
                put(d["s"] + math.cos(ang) * r, d["off"] + math.sin(ang) * r)
        elif kind == "edge":
            side = 1 if d["off"] > 0 else -1
            for _ in range(int(d["len"] * 1.5)):
                s = d["s"] + rnd.random() * d["len"]
                put(s, side * (cl.frame(s)[8] - rnd.random() * 0.4))
    return {k: v for k, v in out.items() if v}


PEBBLE_HALF = ((0.022, 0.017, 0.011, 3), (0.03, 0.02, 0.015, 5), (0.015, 0.014, 0.01, 7))  # half-extents (m), seed


def pebble_meshes():
    """Three rounded, slightly flattened stones (3–6 cm across), ~300 triangles each — Nanite-friendly."""
    objs = []
    for k, (sx, sy, sz, sd) in enumerate(PEBBLE_HALF):
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
        rnd = random.Random(sd)
        for v in bm.verts:
            n = v.co.normalized()
            j = 1.0 + 0.12 * math.sin(n.x * 5 + sd) * math.sin(n.y * 4 - sd) + rnd.uniform(-0.04, 0.04)
            v.co = (n.x * sx * j, n.y * sy * j, max(n.z * sz * j, -sz * 0.35))
        uvl = bm.loops.layers.uv.new("UVMap")
        for f in bm.faces:
            for loop in f.loops:
                loop[uvl].uv = (loop.vert.co.x * 4 + loop.vert.co.z * 2, loop.vert.co.y * 4 + loop.vert.co.z * 2)
        objs.append(_object(f"pebble_{'abc'[k]}", bm, ["stone"], smooth=True))
    return objs


def _object(name, bm, slots, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for mid in slots:
        me.materials.append(kitlib.material(mid, TEXTURED))
    for p in me.polygons:
        p.use_smooth = smooth
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob["materialIds"] = ",".join(slots)
    return ob


TEXTURED = False


def export(path, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_image_format="NONE", export_materials="EXPORT")


def load_defects(specs, ids):
    out = []
    for i in ids:
        p = os.path.join(specs, f"g{i}.json")
        if os.path.exists(p):
            out += json.load(open(p))["road"].get("defects", [])
    return out


def bake(cid, a, index_by_id):
    spec = json.load(open(os.path.join(a.specs, f"g{cid}.json")))
    rd = spec["road"]
    c = index_by_id[cid]
    s0, s1 = float(c["sStart"]), float(c["sEnd"])
    cl = roadfx.Centreline(rd)
    defects = load_defects(a.specs, (cid - 1, cid, cid + 1))
    surf = roadfx.Surface([d for d in defects if s0 - 30 <= d["s"] <= s1 + 30], lambda s: cl.frame(s)[8])
    seed = 7919 * (cid + 1)
    road = build_carriageway(cid, rd, cl, surf, s0, s1, a)
    shoulder = build_shoulders(cid, rd, cl, surf, s0, s1, a, seed)
    objs = [o for o in (road, shoulder) if o is not None]
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs)
    return spec, objs, pebbles(rd, cl, surf, s0, s1, seed), surf, tris


def main():
    global TEXTURED
    a = args()
    TEXTURED = bool(a.render)
    index = json.load(open(os.path.join(a.specs, "index.json")))
    by_id = {c["id"]: c for c in index["chunks"]}
    ids = [int(x) for x in a.ids.split(",") if x] or sorted(by_id)
    os.makedirs(a.out, exist_ok=True)
    report = []
    if not a.render:
        kitlib.reset_scene()
        kitlib.load_kit(a.kit)
        export(os.path.join(a.out, "pebbles.glb"), pebble_meshes())
        for cid in ids:
            kitlib.reset_scene()
            kitlib.load_kit(a.kit)
            spec, objs, peb, surf, tris = bake(cid, a, by_id)
            export(os.path.join(a.out, f"h{cid}.glb"), objs)
            with open(os.path.join(a.out, f"h{cid}_pebbles.json"), "w") as f:
                json.dump({"instances": peb}, f, separators=(",", ":"))
            report.append({"id": cid, "triangles": tris, "pebbles": sum(len(v) for v in peb.values()), "defects": len(surf.items),
                           "bytes": os.path.getsize(os.path.join(a.out, f"h{cid}.glb"))})
            print(f"hero h{cid}: {tris} triangles, {report[-1]['pebbles']} pebbles", flush=True)
        prev = {}
        ip = os.path.join(a.out, "index.json")
        if os.path.exists(ip):
            prev = {r["id"]: r for r in json.load(open(ip)).get("chunks", [])}
        prev.update({r["id"]: r for r in report})
        with open(ip, "w") as f:
            json.dump({"chunks": [prev[k] for k in sorted(prev)], "along": a.along, "fine": a.fine, "shoulder": a.shoulder}, f, indent=1)
        return
    render(a, ids[0], by_id)


def render(a, cid, by_id):
    """Cycles shot of the hero road in context (its chunk and the neighbours, kit instances, far terrain) to check the
    detail: --view low (a pothole up close) or rider (eye height, looking down the road)."""
    import render_common as rc
    import render_course as rcse

    import bake_game_chunk as bg

    kitlib.reset_scene()
    kitlib.load_kit(a.kit)
    spec, objs, peb, surf, tris = bake(cid, a, by_id)
    rd = spec["road"]
    cl = roadfx.Centreline(rd)
    W0 = spec["origin"]
    col = bpy.context.scene.collection
    meshes = rcse.load_kit_meshes(a.kit)
    peb_meshes = {}
    for o in pebble_meshes():
        peb_meshes[o.name] = o.data
        bpy.data.objects.remove(o)

    def inst(me, x, y, z, rot, sc):
        ob = bpy.data.objects.new("i", me)
        ob.location = (x, y, z)
        ob.rotation_euler = (0, 0, rot)
        ob.scale = (sc, sc, sc)
        col.objects.link(ob)

    lo, hi = by_id[cid]["sStart"], by_id[cid]["sEnd"]
    pots = sorted([d for k, d, _, _ in surf.items if k == "pothole" and lo <= d["s"] < hi], key=lambda d: d["depth"])
    if a.at is not None:
        s_t, o_t = a.at, 1.0
    elif pots:
        s_t, o_t = pots[0]["s"], pots[0]["off"]
    else:
        s_t, o_t = (lo + hi) / 2, 1.0
    tx, ty, tz = cl.point(s_t, o_t)
    for k in (cid - 1, cid, cid + 1):
        path = os.path.join(a.specs, f"g{k}.json")
        if not os.path.exists(path):
            continue
        sp = spec if k == cid else json.load(open(path))
        off = [sp["origin"][i] - W0[i] for i in range(3)]
        for o in bg.build_chunk(sp, textured=True):
            if k == cid and o.name.split("_")[0] in ("road", "markings", "defects", "shoulder"):
                bpy.data.objects.remove(o)
                continue
            o.location = off
        for asset, rows in sp["instances"].items():
            me = meshes.get(asset)
            if me is None:
                continue
            for x, y, z, rot, sc in rows:
                wx, wy = x + off[0], y + off[1]
                if math.hypot(wx - tx, wy - ty) < 350:
                    inst(me, wx, wy, z + off[2], rot, sc)
    for asset, rows in peb.items():
        for x, y, z, rot, sc in rows:
            if math.hypot(x - tx, y - ty) < 60:
                inst(peb_meshes[asset], x, y, z, rot, sc)
    far = os.path.join(a.specs, "far.json")
    if os.path.exists(far):
        # corridor fills stand in for the chunks that are not built here (else the sky's ground shows through)
        built = {f"farfill_{k}" for k in (cid - 1, cid, cid + 1)}
        for o in bg.build_far(json.load(open(far)), textured=True, col=col, origin=tuple(W0), fills=True):
            if o.name in built:
                bpy.data.objects.remove(o)
    _, _, _, ux, uy, _, _, _, _ = cl.frame(s_t)
    if a.view == "rider":
        cx, cy, cz = cl.point(s_t - 7.0, min(max(o_t, -1.2), 1.2))
        tgt = cl.point(s_t + 22.0, 0.3)
        rc.camera((cx, cy, cz + 1.45), (tgt[0], tgt[1], tgt[2] + 0.2), lens=26)
    else:
        side = 1 if o_t < 0 else -1
        cx, cy, cz = cl.point(s_t - 2.6, o_t + 0.5 * side)
        rc.camera((cx, cy, cz + 0.85), (tx + ux * 0.5, ty + uy * 0.5, tz - 0.05), lens=32)
    rc.sky_and_sun(a.sun_elev, a.sun_az)
    rc.render(a.render, 1600, 900, a.samples)
    print(f"render: hero h{cid} at s={s_t:.1f} ({tris} triangles, view {a.view})", flush=True)


if __name__ == "__main__":
    main()
