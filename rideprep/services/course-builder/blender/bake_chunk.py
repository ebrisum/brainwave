"""Headless Blender chunk bake (spec §10.2). Blender 5.2 LTS.

  blender -b --factory-startup --python bake_chunk.py -- --input chunks/.inputs/c12.json --out chunks/

Reads the same chunk spec as gpx2course/litebake.py (route samples, buildings, origin) and writes c{id}_lod{0,1,2}.glb:
cambered road with markings, verges, bridge railings and kerbs in built-up areas, extruded buildings with gabled/flat
roofs, AO baked into vertex colours (Cycles), LODs via Decimate. Vegetation stays as instance lists (engines use their
own instancing / Nanite foliage). Geometry is built in ENU metres relative to the chunk origin; the glTF exporter's +Y-up
conversion gives exactly the package convention (x, z, −y). Deterministic: no randomness without the spec seed.
"""
import argparse
import json
import math
import os
import random
import sys

import bpy  # noqa: I001 — bpy first: bmesh/mathutils become importable after it (bpy as a Python module)
import bmesh
import mathutils

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOGUE = os.path.join(HERE, "..", "gpx2course", "data", "materials.json")
FACADE = {"house": "facade_brick", "detached": "facade_brick", "terrace": "facade_brick", "church": "facade_brick", "barn": "facade_barn",
          "farm_auxiliary": "facade_barn", "shed": "facade_barn", "apartments": "facade_plaster", "commercial": "facade_plaster"}


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--no-ao", action="store_true")
    p.add_argument("--materials", default=CATALOGUE, help="package materials.json (regional style applied)")
    return p.parse_args(argv)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 16
    bpy.context.scene.cycles.device = "CPU"


_mats = {}


def material(cat, mid):
    if mid in _mats:
        return _mats[mid]
    spec = cat["materials"].get(mid, {"baseColor": [0.6, 0.6, 0.6], "roughness": 0.9, "metallic": 0})
    m = bpy.data.materials.new(mid)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*spec["baseColor"], 1)
    bsdf.inputs["Roughness"].default_value = spec["roughness"]
    bsdf.inputs["Metallic"].default_value = spec["metallic"]
    # Multiply by baked AO (colour attribute "AO")
    attr = m.node_tree.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "AO"
    mix = m.node_tree.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    mix.inputs[6].default_value = (*spec["baseColor"], 1)
    m.node_tree.links.new(attr.outputs["Color"], mix.inputs[7])
    m.node_tree.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    m["materialId"] = mid
    _mats[mid] = m
    return m


def new_object(name, bm, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob["materialId"] = mat["materialId"]
    return ob


def ribbon(bm, pts, left, right, dz_left=0.0, dz_right=0.0):
    """pts: list of (x, y, z, nx, ny); offsets in metres (+ right of travel)."""
    prev = None
    for k, (x, y, z, nx, ny) in enumerate(pts):
        l_off = left[k] if isinstance(left, list) else left
        r_off = right[k] if isinstance(right, list) else right
        dzl = dz_left[k] if isinstance(dz_left, list) else dz_left
        dzr = dz_right[k] if isinstance(dz_right, list) else dz_right
        a = bm.verts.new((x + nx * l_off, y + ny * l_off, z + dzl))
        b = bm.verts.new((x + nx * r_off, y + ny * r_off, z + dzr))
        if prev:
            bm.faces.new((prev[0], prev[1], b, a))
        prev = (a, b)


def build_road(spec, cat, ox, oy, oz):
    rt = spec["route"]
    pts, widths, terr, surf = [], [], [], []
    for i in range(len(rt["x"])):
        h = rt["heading"][i]
        pts.append((rt["x"][i] - ox, rt["y"][i] - oy, rt["z"][i] - oz + 0.03, math.cos(h), -math.sin(h)))
        widths.append(rt["width"][i] / 2)
        terr.append(rt["terrainZ"][i] - oz)
        surf.append(rt["surface"][i])
    objs = []
    s2m = cat["surfaceCodeToMaterial"]
    # Road by surface run, crowned (two halves, edges 2 % lower)
    start = 0
    for i in range(1, len(pts) + 1):
        if i == len(pts) or surf[i] != surf[start]:
            seg = pts[max(start - 1, 0):i]
            hw = widths[max(start - 1, 0):i]
            mid = s2m.get(str(surf[start]), "road_asphalt")
            if spec.get("redCycleways") and rt["cycleway"][start] and surf[start] in (0, 1):
                mid = "road_asphalt_red"
            bm = bmesh.new()
            ribbon(bm, seg, [-w for w in hw], 0.0, [-0.02 * w for w in hw], 0.0)
            ribbon(bm, seg, 0.0, hw, 0.0, [-0.02 * w for w in hw])
            objs.append(new_object(f"road_{start}", bm, material(cat, mid)))
            start = i
    # Edge lines on roads ≥ 5 m, centre line ≥ 5.5 m — per regional marking style
    mk = spec.get("markings") or {"edge": "solid", "centre": "dashed"}
    bm = bmesh.new()
    for side in ((-1, 1) if mk.get("edge", "solid") != "none" else ()):
        run = [k for k in range(len(pts)) if widths[k] * 2 >= 5 and not rt["cycleway"][k]
               and (mk.get("edge") != "dashed" or (rt["s"][k] % 4.5) < 3.0)]
        if len(run) > 1:
            ribbon(bm, [pts[k] for k in run], [side * (widths[k] - 0.35) - 0.06 for k in run], [side * (widths[k] - 0.35) + 0.06 for k in run], 0.015, 0.015)
    for k in range(len(pts) - 1):
        if mk.get("centre", "dashed") != "none" and widths[k] * 2 >= 5.5 and (rt["s"][k] % 12.0) < 3.0:
            ribbon(bm, [pts[k], pts[k + 1]], -0.06, 0.06, 0.02, 0.02)
    if bm.faces:
        objs.append(new_object("markings", bm, material(cat, "marking_white")))
    else:
        bm.free()
    # Verges sloping to the terrain
    bm = bmesh.new()
    ribbon(bm, pts, [-(w + 3.0) for w in widths], [-w for w in widths], [(terr[k] - pts[k][2]) * 0.9 for k in range(len(pts))], [-0.02 * w for w in widths])
    ribbon(bm, pts, widths, [w + 3.0 for w in widths], [-0.02 * w for w in widths], [(terr[k] - pts[k][2]) * 0.9 for k in range(len(pts))])
    objs.append(new_object("verges", bm, material(cat, "verge_grass")))
    # Bridge railings
    bridge = rt["bridge"]
    if any(bridge):
        bm = bmesh.new()
        idx = [k for k in range(len(pts)) if bridge[k]]
        for side in (-1, 1):
            rail = [pts[k] for k in idx]
            for h in (0.0, 1.1):
                ribbon(bm, rail, [side * (widths[k] + 0.3) - 0.04 for k in idx], [side * (widths[k] + 0.3) + 0.04 for k in idx], h, h)
            for k in idx[::4]:
                x, y, z, nx, ny = pts[k]
                off = side * (widths[k] + 0.3)
                bmesh.ops.create_cube(bm, size=1, matrix=mathutils.Matrix.LocRotScale((x + nx * off, y + ny * off, z + 0.55), None, (0.06, 0.06, 1.1)))
        objs.append(new_object("railings", bm, material(cat, "metal_rail")))
    return objs


def build_buildings(spec, cat, ox, oy, oz):
    objs = []
    by_mat = {}
    for b in spec["buildings"]:
        ring = [(p[0] - ox, p[1] - oy) for p in b["ring"]]
        area = sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring))) / 2
        if area < 0:
            ring = ring[::-1]
        if abs(area) < 4:
            continue
        z0 = b["z"] - oz
        h = b["h"]
        fac = FACADE.get(b.get("type"), "facade_plaster")
        gable = b.get("roof") in ("gabled", "hipped", "pitched") and len(ring) == 4
        bm = by_mat.setdefault(fac, bmesh.new())
        rbm = by_mat.setdefault("roof_tile" if gable else "roof_flat", bmesh.new())
        if gable:
            e0 = math.dist(ring[0], ring[1])
            e1 = math.dist(ring[1], ring[2])
            if e0 < e1:
                ring = ring[1:] + ring[:1]
                e0, e1 = e1, e0
            roof_h = min(0.4 * e1, h * 0.45)
            eave = max(h - roof_h, 2.5)
        else:
            eave = h
        bot = [bm.verts.new((x, y, z0)) for x, y in ring]
        top = [bm.verts.new((x, y, z0 + eave)) for x, y in ring]
        for i in range(len(ring)):
            j = (i + 1) % len(ring)
            bm.faces.new((bot[i], bot[j], top[j], top[i]))
        if gable:
            m03 = ((ring[0][0] + ring[3][0]) / 2, (ring[0][1] + ring[3][1]) / 2, z0 + eave + roof_h)
            m12 = ((ring[1][0] + ring[2][0]) / 2, (ring[1][1] + ring[2][1]) / 2, z0 + eave + roof_h)
            r = [rbm.verts.new((x, y, z0 + eave)) for x, y in ring]
            a, c = rbm.verts.new(m03), rbm.verts.new(m12)
            rbm.faces.new((r[0], r[1], c, a))
            rbm.faces.new((r[2], r[3], a, c))
            g1 = [bm.verts.new(v.co) for v in (top[1], top[2])] + [bm.verts.new(m12)]
            g2 = [bm.verts.new(v.co) for v in (top[3], top[0])] + [bm.verts.new(m03)]
            bm.faces.new(g1)
            bm.faces.new(g2)
        else:
            rv = [rbm.verts.new((x, y, z0 + eave)) for x, y in ring]
            rbm.faces.new(rv)
    for mid, bm in sorted(by_mat.items()):
        if bm.faces:
            bmesh.ops.triangulate(bm, faces=bm.faces[:])
            objs.append(new_object(f"buildings_{mid}", bm, material(cat, mid)))
        else:
            bm.free()
    return objs


def bake_ao(objs):
    """AO into vertex colours for buildings (contact shadows); flat ground (road, verges) keeps a white AO layer —
    large ribbon triangles would otherwise show blotches."""
    for ob in objs:
        me = ob.data
        if "AO" not in me.color_attributes:
            me.color_attributes.new("AO", "BYTE_COLOR", "CORNER")
        attr = me.color_attributes["AO"]
        for d in attr.data:
            d.color = (1, 1, 1, 1)
        me.color_attributes.active_color = attr
    targets = [o for o in objs if o.name.startswith("buildings_") and o.data.polygons]
    if not targets:
        return
    bpy.ops.object.select_all(action="DESELECT")
    for ob in targets:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = targets[0]
    bpy.context.scene.render.bake.target = "VERTEX_COLORS"
    bpy.ops.object.bake(type="AO")


def bake_ao_white(objs):
    for ob in objs:
        me = ob.data
        if "AO" not in me.color_attributes:
            attr = me.color_attributes.new("AO", "BYTE_COLOR", "CORNER")
            for d in attr.data:
                d.color = (1, 1, 1, 1)
            me.color_attributes.active_color = attr


def export(path, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objs:
        ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_yup=True, export_extras=True,
                              export_apply=True, export_vertex_color="ACTIVE", export_normals=True, export_texcoords=False)


def main():
    a = args()
    spec = json.load(open(a.input))
    cat = json.load(open(a.materials))
    random.seed(spec.get("seed", 0))
    ox, oy, oz = spec["origin"]
    for lod, ratio in ((0, 1.0), (1, 0.5), (2, 0.2)):
        reset()
        _mats.clear()
        objs = build_road(spec, cat, ox, oy, oz) + build_buildings(spec, cat, ox, oy, oz)
        if lod > 0:
            objs = [o for o in objs if o.name not in ("markings", "railings")] if lod == 2 else [o for o in objs if o.name != "markings"]
            for o in objs:
                mod = o.modifiers.new("decimate", "DECIMATE")
                mod.ratio = ratio
        if objs:
            if a.no_ao or lod > 0:
                bake_ao_white(objs)
            else:
                bake_ao(objs)
        export(os.path.join(a.out, f"c{spec['id']}_lod{lod}.glb"), objs)


if __name__ == "__main__":
    main()
