"""Build a kit's meshes in headless Blender (5.x):

  blender -b --factory-startup --python build_kit_meshes.py -- --kit <kit_dir> [--showcase showcase.png]

Writes <kit_dir>/kit.glb (all assets, textured, one root node per asset + `<asset>__lod1`), <kit_dir>/kit.blend and
<kit_dir>/assets.json (asset → bounds, triangle counts, LODs, material ids). Assets are low-poly, card-based foliage
in the style of real-time games; Z-up metres with the origin at the base (row assets extend along +X).
Deterministic: every random choice comes from a per-asset seeded generator.
"""
import argparse
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402,I001
import mathutils  # noqa: E402

import kitlib  # noqa: E402
from kitlib import MeshBuilder  # noqa: E402


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True)
    p.add_argument("--showcase", default=None)
    p.add_argument("--samples", type=int, default=48)
    return p.parse_args(argv)


# ---- foliage helpers ----------------------------------------------------------------------------------------------


def cards_in_ellipsoid(mb, rnd, center, radii, n, size, mid, droop=0.35):
    cx, cy, cz = center
    for _ in range(n):
        # Bias towards the shell: foliage lives on the outside of a crown
        while True:
            v = mathutils.Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)))
            if 0.45 < v.length <= 1.0:
                break
        p = (cx + v.x * radii[0], cy + v.y * radii[1], cz + v.z * radii[2])
        yaw = math.atan2(v.y, v.x) + math.pi / 2 + rnd.uniform(-0.6, 0.6)
        pitch = rnd.uniform(-droop, droop) + (0.6 if v.z > 0.5 else 0)
        s = size * rnd.uniform(0.75, 1.25)
        mb.card(p, s, s, yaw, pitch, mid)


def trunk(mb, rnd, h, r, mid, lean=0.03, sides=7, bend=0.0):
    pts = [mathutils.Vector((0, 0, 0))]
    segs = 4
    dx, dy = rnd.uniform(-lean, lean), rnd.uniform(-lean, lean)
    for k in range(1, segs + 1):
        t = k / segs
        pts.append(mathutils.Vector((dx * h * t + bend * h * t * t, dy * h * t, h * t)))
    for k in range(segs):
        t0, t1 = k / segs, (k + 1) / segs
        mb.cylinder(pts[k], pts[k + 1], r * (1 - 0.45 * t0), r * (1 - 0.45 * t1), sides, mid, cap=(k == segs - 1))
    return pts[-1]


def branches(mb, rnd, origin, n, length, r, mid, up=0.6):
    for k in range(n):
        a = k / n * math.tau + rnd.uniform(-0.3, 0.3)
        d = mathutils.Vector((math.cos(a), math.sin(a), up + rnd.uniform(-0.2, 0.2))).normalized()
        mb.cylinder(origin, mathutils.Vector(origin) + d * length * rnd.uniform(0.7, 1.1), r, r * 0.4, 5, mid, cap=False)


# ---- assets -------------------------------------------------------------------------------------------------------


def tree_stone_pine(lod):
    """Pinus pinea — tall clean trunk, flat umbrella crown (Cervia pinewood, promenades)."""
    rnd = random.Random(11)
    mb = MeshBuilder("tree_stone_pine" + ("__lod1" if lod else ""))
    top = trunk(mb, rnd, 9.5, 0.32, "bark_pine", lean=0.06, sides=8 if not lod else 5)
    if not lod:
        for k in range(5):
            a = k / 5 * math.tau
            mb.cylinder(top - mathutils.Vector((0, 0, 1.5)), top + mathutils.Vector((math.cos(a) * 3.2, math.sin(a) * 3.2, 1.2)), 0.14, 0.06, 5, "bark_pine", cap=False)
    c = (top.x, top.y, top.z + 1.6)
    mb.blob(c, (5.0, 5.0, 1.3), "foliage_core", 2 if not lod else 1)
    if not lod:
        cards_in_ellipsoid(mb, rnd, c, (5.9, 5.9, 1.7), 110, 2.8, "leaf_pine", droop=0.25)
    return mb


def tree_cypress(lod):
    """Cupressus sempervirens — narrow dark column (villas, cemeteries, Bertinoro hills)."""
    rnd = random.Random(12)
    mb = MeshBuilder("tree_cypress" + ("__lod1" if lod else ""))
    mb.cylinder((0, 0, 0), (0, 0, 1.2), 0.18, 0.15, 6, "bark", cap=False)
    # Column core (smooth spindle)
    rings, sides = 9, 8 if not lod else 5
    prof = [(0.8, 0.0), (1.15, 2.0), (1.25, 4.5), (1.15, 7.0), (0.95, 9.5), (0.65, 11.5), (0.35, 13.0), (0.12, 14.0), (0.0, 14.6)]
    prev = None
    for r, z in prof[:rings]:
        ring = [(r * math.cos(k / sides * math.tau), r * math.sin(k / sides * math.tau), z + 0.8) for k in range(sides)]
        if prev:
            for k in range(sides):
                a, b = prev[k], prev[(k + 1) % sides]
                c, d = ring[(k + 1) % sides], ring[k]
                mb.face([a, b, c, d], [(a[0], a[2]), (b[0], b[2]), (c[0], c[2]), (d[0], d[2])], "foliage_core_dark", smooth=True)
        prev = ring
    if not lod:
        for k in range(46):
            z = rnd.uniform(1.5, 13.5)
            r = 1.2 * (1 - abs(z - 5) / 11) + 0.2
            a = rnd.uniform(0, math.tau)
            mb.card((r * math.cos(a), r * math.sin(a), z), 1.4, 2.2, a + math.pi / 2, rnd.uniform(-0.2, 0.2), "leaf_cypress")
    return mb


def tree_poplar(lod):
    """Populus nigra 'Italica' — Lombardy poplar lines along canals and field edges."""
    rnd = random.Random(13)
    mb = MeshBuilder("tree_poplar" + ("__lod1" if lod else ""))
    trunk(mb, rnd, 4, 0.28, "bark", lean=0.01)
    mb.blob((0, 0, 11.0), (1.5, 1.5, 9.0), "foliage_core", 2 if not lod else 1)
    if not lod:
        cards_in_ellipsoid(mb, rnd, (0, 0, 11.0), (1.9, 1.9, 9.6), 120, 1.8, "leaf_poplar", droop=0.3)
    return mb


def tree_broadleaf(lod, name="tree_broadleaf", seed=14, h=5.0, crown=(4.2, 4.2, 3.6), mid="leaf_broad"):
    rnd = random.Random(seed)
    mb = MeshBuilder(name + ("__lod1" if lod else ""))
    top = trunk(mb, rnd, h, 0.3, "bark", lean=0.05)
    if not lod:
        branches(mb, rnd, top - mathutils.Vector((0, 0, 0.8)), 5, crown[0] * 0.8, 0.13, "bark")
    c = (top.x, top.y, top.z + crown[2] * 0.6)
    mb.blob(c, tuple(r * 0.72 for r in crown), "foliage_core", 2 if not lod else 1)
    if not lod:
        cards_in_ellipsoid(mb, rnd, c, crown, 150, 2.4, mid, droop=0.5)
    return mb


def tree_olive(lod):
    rnd = random.Random(15)
    mb = MeshBuilder("tree_olive" + ("__lod1" if lod else ""))
    for k in range(2 if not lod else 1):  # twin gnarled trunks
        top = trunk(mb, rnd, 1.9, 0.22, "bark", lean=0.25)
    c = (top.x, top.y, 3.0)
    mb.blob(c, (2.0, 2.0, 1.3), "foliage_core_olive", 2 if not lod else 1)
    if not lod:
        cards_in_ellipsoid(mb, rnd, c, (2.5, 2.5, 1.6), 80, 1.5, "leaf_olive", droop=0.5)
    return mb


def tree_fruit(lod):
    """Peach/apricot/nectarine — open-vase orchard tree, ~3.5 m (Romagna stone-fruit orchards)."""
    rnd = random.Random(16)
    mb = MeshBuilder("tree_fruit" + ("__lod1" if lod else ""))
    mb.cylinder((0, 0, 0), (0, 0, 0.9), 0.12, 0.1, 6, "bark")
    if not lod:
        branches(mb, rnd, (0, 0, 0.9), 4, 1.6, 0.07, "bark", up=1.3)
    mb.blob((0, 0, 2.5), (1.5, 1.5, 1.0), "foliage_core", 1)
    if not lod:
        cards_in_ellipsoid(mb, rnd, (0, 0, 2.5), (2.0, 2.0, 1.3), 60, 1.3, "leaf_fruit", droop=0.5)
    return mb


def tree_palm(lod):
    rnd = random.Random(17)
    mb = MeshBuilder("tree_palm" + ("__lod1" if lod else ""))
    top = trunk(mb, rnd, 7.5, 0.3, "bark", lean=0.02, bend=0.05)
    for k in range(12 if not lod else 6):
        a = k / (12 if not lod else 6) * math.tau
        L = 3.6
        # A drooping frond as two quads
        p0 = top
        p1 = top + mathutils.Vector((math.cos(a) * L * 0.55, math.sin(a) * L * 0.55, 0.9))
        p2 = top + mathutils.Vector((math.cos(a) * L, math.sin(a) * L, -0.4))
        side = mathutils.Vector((-math.sin(a), math.cos(a), 0)) * 0.55
        mb.quad(p0 - side * 0.3, p0 + side * 0.3, p1 + side, p1 - side, "leaf_palm", [(0, 0), (1, 0), (1, 0.5), (0, 0.5)])
        mb.quad(p1 - side, p1 + side, p2 + side * 0.3, p2 - side * 0.3, "leaf_palm", [(0, 0.5), (1, 0.5), (1, 1), (0, 1)])
    return mb


def vine_row_5m(lod):
    """5 m of a trellised (spalliera) Sangiovese row along +X: posts, wires, leafy canopy with grapes."""
    rnd = random.Random(18)
    mb = MeshBuilder("vine_row_5m" + ("__lod1" if lod else ""))
    mb.box((0, 0, 1.0), (0.08, 0.08, 2.0), "wood_post")
    # canopy core: tapered hedge 0.7–1.9 m
    mb.quad((0, -0.22, 0.7), (5, -0.22, 0.7), (5, -0.3, 1.9), (0, -0.3, 1.9), "foliage_core", [(0, 0.7), (5, 0.7), (5, 1.9), (0, 1.9)])
    mb.quad((5, 0.22, 0.7), (0, 0.22, 0.7), (0, 0.3, 1.9), (5, 0.3, 1.9), "foliage_core", [(0, 0.7), (5, 0.7), (5, 1.9), (0, 1.9)])
    mb.quad((0, -0.3, 1.9), (5, -0.3, 1.9), (5, 0.3, 1.9), (0, 0.3, 1.9), "foliage_core", [(0, 0), (5, 0), (5, 0.6), (0, 0.6)])
    if not lod:
        for k in range(14):
            x = (k + 0.5) * 5 / 14
            for side in (-1, 1):
                mb.card((x + rnd.uniform(-0.1, 0.1), side * 0.32, rnd.uniform(1.0, 1.6)), 0.9, 0.9, rnd.uniform(-0.3, 0.3), 0.0, "leaf_vine")
        # Trunk stubs and the fruiting wire
        for k in range(5):
            mb.cylinder((k + 0.5, 0, 0), (k + 0.5, 0, 0.75), 0.04, 0.035, 4, "bark", cap=False)
        mb.cylinder((0, 0, 0.75), (5, 0, 0.75), 0.006, 0.006, 3, "metal_galvanised", cap=False)
    return mb


def hedge_4m(lod):
    rnd = random.Random(19)
    mb = MeshBuilder("hedge_4m" + ("__lod1" if lod else ""))
    mb.box((2, 0, 0.75), (4, 0.9, 1.5), "foliage_core")
    if not lod:
        for k in range(16):
            mb.card((rnd.uniform(0, 4), rnd.choice((-0.47, 0.47)), rnd.uniform(0.3, 1.3)), 0.9, 0.9, rnd.uniform(-0.4, 0.4), 0, "leaf_broad")
    return mb


def reeds(lod):
    rnd = random.Random(20)
    mb = MeshBuilder("reeds" + ("__lod1" if lod else ""))
    for k in range(6 if not lod else 3):
        a = k / 6 * math.pi + rnd.uniform(-0.2, 0.2)
        mb.card((rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3), 1.1), 1.6, 2.2, a, 0, "reed")
    return mb


def guardrail_4m(lod):
    """Italian W-beam (lama a doppia onda) on a C-post; 4 m along +X, traffic side −Y."""
    mb = MeshBuilder("guardrail_4m" + ("__lod1" if lod else ""))
    mb.box((0.2, 0.08, 0.38), (0.12, 0.08, 0.76), "metal_galvanised")
    prof = [(-0.0, 0.42), (-0.05, 0.47), (-0.05, 0.55), (0.0, 0.6), (-0.05, 0.65), (-0.05, 0.73), (0.0, 0.78)]
    if lod:
        prof = [prof[0], prof[3], prof[-1]]
    for (y0, z0), (y1, z1) in zip(prof[:-1], prof[1:]):
        mb.quad((0, y0, z0), (4, y0, z0), (4, y1, z1), (0, y1, z1), "metal_galvanised", [(0, z0), (4, z0), (4, z1), (0, z1)])
        mb.quad((4, y0 + 0.004, z0), (0, y0 + 0.004, z0), (0, y1 + 0.004, z1), (4, y1 + 0.004, z1), "metal_galvanised", [(0, z0), (4, z0), (4, z1), (0, z1)])
    return mb


def delineator(lod):
    """Delineatore normale di margine: white post, black band, red reflector (right-hand side)."""
    mb = MeshBuilder("delineator" + ("__lod1" if lod else ""))
    mb.box((0, 0, 0.45), (0.1, 0.12, 0.9), "paint_white")
    mb.box((0, 0, 0.98), (0.1, 0.12, 0.16), "paint_black")
    if not lod:
        mb.box((0, -0.062, 0.98), (0.05, 0.005, 0.1), "reflector_red")
    return mb


def sign(cell, plate="tri", name=None, w=0.9, h=0.9, pole=2.4):
    """Sign on a galvanised pole; the plate maps one 4×4 atlas cell."""
    def make(lod):
        mb = MeshBuilder((name or f"sign_{cell}") + ("__lod1" if lod else ""))
        mb.cylinder((0, 0, 0), (0, 0, pole + h * 0.5), 0.03, 0.03, 6 if not lod else 4, "metal_galvanised")
        cx, cy = cell % 4, cell // 4
        u0, u1 = cx / 4, (cx + 1) / 4
        v1, v0 = 1 - cy / 4, 1 - (cy + 1) / 4
        z = pole
        mb.quad((-w / 2, -0.04, z - h / 2), (w / 2, -0.04, z - h / 2), (w / 2, -0.04, z + h / 2), (-w / 2, -0.04, z + h / 2), "signs",
                [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
        mb.quad((w / 2, -0.035, z - h / 2), (-w / 2, -0.035, z - h / 2), (-w / 2, -0.035, z + h / 2), (w / 2, -0.035, z + h / 2), "metal_galvanised")
        return mb
    return make


def town_sign(k):
    def make(lod):
        mb = MeshBuilder(f"town_sign_{k}" + ("__lod1" if lod else ""))
        for x in (-0.7, 0.7):
            mb.cylinder((x, 0, 0), (x, 0, 2.6), 0.035, 0.035, 6, "metal_galvanised")
        cell = 8 + k
        cx, cy = cell % 4, cell // 4
        u0, u1 = cx / 4, (cx + 1) / 4
        v1, v0 = 1 - (cy + 0.3) / 4, 1 - (cy + 0.7) / 4
        mb.quad((-0.9, -0.05, 1.9), (0.9, -0.05, 1.9), (0.9, -0.05, 2.62), (-0.9, -0.05, 2.62), "signs", [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
        mb.quad((0.9, -0.045, 1.9), (-0.9, -0.045, 1.9), (-0.9, -0.045, 2.62), (0.9, -0.045, 2.62), "metal_galvanised")
        return mb
    return make


def streetlight(lod):
    mb = MeshBuilder("streetlight" + ("__lod1" if lod else ""))
    mb.cylinder((0, 0, 0), (0, 0, 8), 0.09, 0.06, 8 if not lod else 5, "metal_galvanised")
    mb.cylinder((0, 0, 7.8), (0, -1.6, 8.1), 0.04, 0.04, 5, "metal_galvanised", cap=False)
    mb.box((0, -1.8, 8.05), (0.3, 0.6, 0.15), "metal_galvanised")
    return mb


def flamingo(lod):
    """Greater flamingo, standing; ~1.3 m (Saline di Cervia colonies)."""
    mb = MeshBuilder("flamingo" + ("__lod1" if lod else ""))
    mb.blob((0, 0, 0.95), (0.32, 0.17, 0.17), "flamingo", 2 if not lod else 1)
    mb.cylinder((0.25, 0, 1.0), (0.3, 0, 1.45), 0.035, 0.03, 5, "flamingo", cap=False)
    mb.cylinder((0.3, 0, 1.45), (0.42, 0, 1.38), 0.03, 0.02, 5, "flamingo", cap=False)
    mb.cylinder((0.42, 0, 1.38), (0.48, 0, 1.3), 0.025, 0.01, 5, "paint_black")
    for y in (-0.05, 0.05):
        mb.cylinder((0, y, 0), (0, y, 0.85), 0.012, 0.012, 4, "flamingo", cap=False)
    return mb


def salt_heap(lod):
    mb = MeshBuilder("salt_heap" + ("__lod1" if lod else ""))
    mb.cylinder((0, 0, 0), (0, 0, 2.2), 3.0, 0.15, 12 if not lod else 6, "salt")
    return mb


def campanile(lod):
    """Romanesque brick bell tower with a belfry and pyramidal coppi roof (instanced beside churches)."""
    mb = MeshBuilder("campanile" + ("__lod1" if lod else ""))
    s, H = 4.2, 22.0
    mb.box((0, 0, H / 2), (s, s, H), "brick")
    # Belfry: open arches suggested by dark recesses
    for k in range(4):
        a = k * math.pi / 2
        d = mathutils.Vector((math.cos(a), math.sin(a), 0))
        t = mathutils.Vector((-math.sin(a), math.cos(a), 0))
        c = d * (s / 2 + 0.01)
        for off in (-0.8, 0.8):
            p = c + t * off
            mb.quad(p - t * 0.45 + mathutils.Vector((0, 0, H - 4.5)), p + t * 0.45 + mathutils.Vector((0, 0, H - 4.5)),
                    p + t * 0.45 + mathutils.Vector((0, 0, H - 1.5)), p - t * 0.45 + mathutils.Vector((0, 0, H - 1.5)), "paint_black")
    apex = (0, 0, H + 3.2)
    corners = [(-s / 2 - 0.2, -s / 2 - 0.2, H), (s / 2 + 0.2, -s / 2 - 0.2, H), (s / 2 + 0.2, s / 2 + 0.2, H), (-s / 2 - 0.2, s / 2 + 0.2, H)]
    for k in range(4):
        a, b = corners[k], corners[(k + 1) % 4]
        mb.face([a, b, apex], [(0, 0), (s, 0), (s / 2, 3.6)], "roof_coppi")
    return mb


def race_barrier_2m(lod):
    mb = MeshBuilder("race_barrier_2m" + ("__lod1" if lod else ""))
    for x in (0.05, 1.95):
        mb.box((x, 0, 0.55), (0.04, 0.04, 1.1), "plastic_barrier")
        mb.box((x, 0, 0.02), (0.06, 0.6, 0.04), "plastic_barrier")
    for z in (0.15, 1.08):
        mb.box((1.0, 0, z), (1.9, 0.03, 0.04), "plastic_barrier")
    if not lod:
        for k in range(14):
            mb.box((0.18 + k * 0.125, 0, 0.6), (0.015, 0.015, 0.9), "plastic_barrier")
    # Generic blue mesh banner on the barrier (no brand marks)
    mb.quad((0.05, -0.03, 0.2), (1.95, -0.03, 0.2), (1.95, -0.03, 1.0), (0.05, -0.03, 1.0), "fabric_banner")
    return mb


ASSETS = {
    "tree_stone_pine": tree_stone_pine, "tree_cypress": tree_cypress, "tree_poplar": tree_poplar,
    "tree_broadleaf": tree_broadleaf,
    "tree_oak": lambda lod: tree_broadleaf(lod, "tree_oak", 21, 3.2, (5.0, 5.0, 3.4), "leaf_broad"),
    "tree_olive": tree_olive, "tree_fruit": tree_fruit, "tree_palm": tree_palm, "vine_row_5m": vine_row_5m, "hedge_4m": hedge_4m,
    "reeds": reeds, "guardrail_4m": guardrail_4m, "delineator": delineator, "streetlight": streetlight, "flamingo": flamingo,
    "salt_heap": salt_heap, "campanile": campanile, "race_barrier_2m": race_barrier_2m,
    "sign_danger": sign(0, name="sign_danger"), "sign_50": sign(1, name="sign_50"), "sign_70": sign(2, name="sign_70"),
    "sign_giveway": sign(4, name="sign_giveway"), "sign_roundabout": sign(5, name="sign_roundabout"),
    "sign_tourist": sign(6, name="sign_tourist", w=1.2, h=0.6), "km_marker": sign(7, name="km_marker", w=0.35, h=0.6, pole=0.5),
}
for _k in range(8):
    ASSETS[f"town_sign_{_k}"] = town_sign(_k)


def main():
    a = args()
    kitlib.reset_scene()
    kitlib.load_kit(a.kit)
    col = bpy.context.scene.collection
    info = {}
    objs = []
    for name, fn in ASSETS.items():
        entry = {"lods": []}
        for lod in (0, 1):
            mb = fn(lod)
            ob = mb.build(textured=True, collection=col)
            objs.append(ob)
            tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
            bb = [ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
            entry["lods"].append({"node": ob.name, "triangles": tris})
            if lod == 0:
                entry["bounds"] = [[round(min(v[i] for v in bb), 3) for i in range(3)], [round(max(v[i] for v in bb), 3) for i in range(3)]]
                entry["materials"] = mb.slots
        info[name] = entry
    out_glb = os.path.join(a.kit, "kit.glb")
    bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB", export_yup=True, export_extras=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_image_format="AUTO")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(a.kit, "kit.blend"), compress=True)
    json.dump({"assets": info, "uv": "metres for materials with tileM; 0–1 otherwise", "up": "Z (Blender) / +Y (glTF)"},
              open(os.path.join(a.kit, "assets.json"), "w"), indent=1)
    print(f"kit: {len(info)} assets → {out_glb}")
    if a.showcase:
        showcase(a, objs)


def showcase(a, objs):
    """Line the LOD0 assets up on a ground plate and render with Cycles (documentation image)."""
    import render_common as rc

    lod0 = [o for o in objs if "__lod1" not in o.name]
    for o in objs:
        o.hide_render = "__lod1" in o.name
    x = 0.0
    row_y = {0: 0.0, 1: 12.0}
    big = {"tree_stone_pine", "tree_cypress", "tree_poplar", "tree_broadleaf", "tree_oak", "tree_palm", "campanile"}
    xs = {0: 0.0, 1: 0.0}
    for o in lod0:
        r = 0 if o.name in big else 1
        w = (o.dimensions.x if o.dimensions.x > 0 else 2) + (3.0 if r == 0 else 1.2)
        o.location = (xs[r] + w / 2, row_y[r], 0)
        xs[r] += w
    x = max(xs.values())
    rc.ground_plate((x / 2, 6, 0), (x + 30, 60), "grass_dry")
    rc.sky_and_sun(elevation_deg=38, azimuth_deg=135)
    cam = rc.camera((x * 0.42, -34, 5), (x * 0.42, 8, 7), lens=24)
    rc.render(a.showcase, 1600, 700, a.samples)


if __name__ == "__main__":
    main()
