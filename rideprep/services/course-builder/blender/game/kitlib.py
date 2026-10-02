"""Shared Blender helpers for the game-art path: kit materials (from <kit>/materials.json), mesh building utilities.

UV convention for every kit mesh and chunk mesh: TEXCOORD_0 is in **metres** for materials with a `tileM`, so an
engine applies `repeat = 1 / tileM` (three.js texture.repeat, Unreal material-instance UV scale, a Mapping node here).
Materials without `tileM` (leaf cards, sign atlas) use plain 0–1 texture coordinates.
"""
import json
import math
import os

import bpy  # noqa: I001
import bmesh
import mathutils

_mats = {}
_kit = {"dir": None, "table": {}}


def load_kit(kit_dir):
    _kit["dir"] = kit_dir
    _kit["table"] = json.load(open(os.path.join(kit_dir, "materials.json")))["materials"]
    _mats.clear()
    return _kit["table"]


def _hex(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _lin(c):
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def material(mid, textured=True):
    """Principled material for a kit material id. textured=False → no image nodes (chunk export: engines bind the kit
    textures themselves by `materialId`), but colour/roughness stay representative for any glTF viewer."""
    key = (mid, textured)
    if key in _mats:
        return _mats[key]
    spec = _kit["table"].get(mid) or {"color": "#888888", "roughness": 0.9}
    m = bpy.data.materials.new(mid)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = float(spec.get("roughness", 0.9))
    bsdf.inputs["Metallic"].default_value = float(spec.get("metallic", 0.0))
    col = _lin(_hex(spec["color"])) if "color" in spec else [0.5, 0.5, 0.5]
    bsdf.inputs["Base Color"].default_value = (*col, 1)
    if spec.get("emissive"):
        bsdf.inputs["Emission Color"].default_value = (*col, 1)
        bsdf.inputs["Emission Strength"].default_value = float(spec["emissive"])
    if "alpha" in spec:
        bsdf.inputs["Alpha"].default_value = float(spec["alpha"])
    tile = spec.get("tileM")
    if textured and spec.get("albedo") and _kit["dir"]:
        uv = nt.nodes.new("ShaderNodeTexCoord")
        mapping = nt.nodes.new("ShaderNodeMapping")
        if tile:
            sx, sy = (tile, tile) if not isinstance(tile, list) else tile
            mapping.inputs["Scale"].default_value = (1 / sx, 1 / sy, 1)
        nt.links.new(uv.outputs["UV"], mapping.inputs["Vector"])
        img = nt.nodes.new("ShaderNodeTexImage")
        img.image = bpy.data.images.load(os.path.join(_kit["dir"], "textures", spec["albedo"]), check_existing=True)
        nt.links.new(mapping.outputs["Vector"], img.inputs["Vector"])
        nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
        if spec.get("alphaCutoff") is not None:
            # glTF MASK: alpha → (alpha ≥ cutoff)
            lt = nt.nodes.new("ShaderNodeMath")
            lt.operation = "LESS_THAN"
            lt.inputs[1].default_value = float(spec["alphaCutoff"])
            inv = nt.nodes.new("ShaderNodeMath")
            inv.operation = "SUBTRACT"
            inv.inputs[0].default_value = 1.0
            nt.links.new(img.outputs["Alpha"], lt.inputs[0])
            nt.links.new(lt.outputs[0], inv.inputs[1])
            nt.links.new(inv.outputs[0], bsdf.inputs["Alpha"])
        if spec.get("normal"):
            nimg = nt.nodes.new("ShaderNodeTexImage")
            nimg.image = bpy.data.images.load(os.path.join(_kit["dir"], "textures", spec["normal"]), check_existing=True)
            nimg.image.colorspace_settings.name = "Non-Color"
            nt.links.new(mapping.outputs["Vector"], nimg.inputs["Vector"])
            nm = nt.nodes.new("ShaderNodeNormalMap")
            nm.inputs["Strength"].default_value = 0.8
            nt.links.new(nimg.outputs["Color"], nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    elif spec.get("albedo"):
        # Untextured stand-in colour: mean of the albedo
        try:
            img = bpy.data.images.load(os.path.join(_kit["dir"], "textures", spec["albedo"]), check_existing=True)
            px = list(img.pixels[: 4 * 4096])
            n = len(px) // 4
            avg = [sum(px[c::4]) / n for c in range(3)]
            bsdf.inputs["Base Color"].default_value = (*avg, 1)
        except Exception:  # noqa: BLE001
            pass
    if spec.get("alphaCutoff") is not None or "alpha" in spec:
        try:
            m.surface_render_method = "DITHERED"
        except AttributeError:
            pass
        m.use_backface_culling = False
    m["materialId"] = mid
    _mats[key] = m
    return m


class MeshBuilder:
    """Accumulates geometry per material and emits one object with material slots and a metre-based UV layer."""

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.slots = []

    def slot(self, mid):
        if mid not in self.slots:
            self.slots.append(mid)
        return self.slots.index(mid)

    def face(self, verts, uvs, mid, smooth=False):
        vs = [self.bm.verts.new(v) for v in verts]
        try:
            f = self.bm.faces.new(vs)
        except ValueError:
            return None
        f.material_index = self.slot(mid)
        f.smooth = smooth
        for loop, uv in zip(f.loops, uvs):
            loop[self.uv].uv = uv
        return f

    def quad(self, a, b, c, d, mid, uv=None, smooth=False):
        uv = uv or [(0, 0), (1, 0), (1, 1), (0, 1)]
        return self.face([a, b, c, d], uv, mid, smooth)

    def box(self, center, size, mid, rot_z=0.0):
        cx, cy, cz = center
        sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
        R = mathutils.Matrix.Rotation(rot_z, 3, "Z")
        c = [R @ mathutils.Vector(p) + mathutils.Vector(center) for p in
             [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz), (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]]
        W, D, H = size
        faces = [((0, 1, 5, 4), W, H), ((1, 2, 6, 5), D, H), ((2, 3, 7, 6), W, H), ((3, 0, 4, 7), D, H), ((4, 5, 6, 7), W, D), ((3, 2, 1, 0), W, D)]
        for idx, u, v in faces:
            self.face([c[i] for i in idx], [(0, 0), (u, 0), (u, v), (0, v)], mid)

    def cylinder(self, base, top, r0, r1, sides, mid, cap=True, uv_scale=1.0):
        base, top = mathutils.Vector(base), mathutils.Vector(top)
        axis = (top - base)
        L = axis.length
        q = axis.normalized().to_track_quat("Z", "X")
        ring0, ring1 = [], []
        for k in range(sides + 1):
            a = k / sides * math.tau
            d = q @ mathutils.Vector((math.cos(a), math.sin(a), 0))
            ring0.append(base + d * r0)
            ring1.append(top + d * r1)
        circ = math.tau * max(r0, r1)
        for k in range(sides):
            u0, u1 = k / sides * circ * uv_scale, (k + 1) / sides * circ * uv_scale
            self.face([ring0[k], ring0[k + 1], ring1[k + 1], ring1[k]], [(u0, 0), (u1, 0), (u1, L * uv_scale), (u0, L * uv_scale)], mid, smooth=True)
        if cap and r1 > 0.01:
            self.face(ring1[:-1], [(0.5 + 0.5 * math.cos(k / sides * math.tau), 0.5 + 0.5 * math.sin(k / sides * math.tau)) for k in range(sides)], mid)

    def card(self, center, w, h, yaw, pitch, mid, uv_rect=(0, 0, 1, 1)):
        R = mathutils.Euler((pitch, 0, yaw), "XYZ").to_matrix()
        c = mathutils.Vector(center)
        pts = [c + R @ mathutils.Vector(p) for p in ((-w / 2, 0, -h / 2), (w / 2, 0, -h / 2), (w / 2, 0, h / 2), (-w / 2, 0, h / 2))]
        u0, v0, u1, v1 = uv_rect
        self.face(pts, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], mid)

    def blob(self, center, radii, mid, subdiv=2):
        tmp = bmesh.new()
        bmesh.ops.create_icosphere(tmp, subdivisions=subdiv, radius=1.0)
        cx, cy, cz = center
        for f in tmp.faces:
            vs = [(cx + v.co.x * radii[0], cy + v.co.y * radii[1], cz + v.co.z * radii[2]) for v in f.verts]
            self.face(vs, [(v[0], v[2]) for v in vs], mid, smooth=True)
        tmp.free()

    def build(self, textured=True, collection=None, crown_normals=False):
        me = bpy.data.meshes.new(self.name)
        bmesh.ops.remove_doubles(self.bm, verts=self.bm.verts, dist=1e-5)
        self.bm.to_mesh(me)
        self.bm.free()
        for mid in self.slots:
            me.materials.append(material(mid, textured))
        if crown_normals:
            set_crown_normals(me, [i for i, m in enumerate(self.slots) if m.startswith(("leaf_", "foliage_core", "reed"))])
        ob = bpy.data.objects.new(self.name, me)
        (collection or bpy.context.scene.collection).objects.link(ob)
        ob["materialIds"] = ",".join(self.slots)
        return ob


def set_crown_normals(me, foliage_slots):
    """Game-foliage lighting: foliage cards and crown cores get normals pointing out of the crown (gradient of the
    foliage's bounding ellipsoid) instead of their face normals, so crowns shade like volumes from any side."""
    if not foliage_slots:
        return
    fol = [p for p in me.polygons if p.material_index in foliage_slots]
    if not fol:
        return
    vs = {i for p in fol for i in p.vertices}
    co = [me.vertices[i].co for i in vs]
    lo = mathutils.Vector([min(c[k] for c in co) for k in range(3)])
    hi = mathutils.Vector([max(c[k] for c in co) for k in range(3)])
    c = (lo + hi) / 2
    r = [max((hi[k] - lo[k]) / 2, 0.3) for k in range(3)]
    corner = [mathutils.Vector(n.vector) for n in me.corner_normals]
    for p in fol:
        for li in p.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            g = mathutils.Vector(((v.x - c.x) / r[0] ** 2, (v.y - c.y) / r[1] ** 2, (v.z - c.z) / r[2] ** 2 + 0.15 / r[2]))
            corner[li] = g.normalized() if g.length > 1e-9 else mathutils.Vector((0, 0, 1))
    me.normals_split_custom_set([tuple(n) for n in corner])


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mats.clear()
