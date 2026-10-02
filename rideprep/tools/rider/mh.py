"""MakeHuman (CC0, hm08 base mesh + default skeleton) loader for headless Blender.

Builds a morphed body (race/gender/age, muscle/weight, height, proportions targets), its armature from the skeleton's
joint vertex groups, and skin weights from the .mhw file — with the 163-bone skeleton reduced to a 74-bone real-time
rig (facial bones merged into the head, toes into the feet). Units: MakeHuman decimetres, Y-up → Blender metres, Z-up.
"""
import json
import os

import bpy  # noqa: I001
import mathutils
import numpy as np

SCALE = 0.1
DROP_PREFIX = ("levator", "oculi", "orbicularis", "oris", "risorius", "temporalis", "tongue", "special", "eye.", "jaw", "toe", "breast")
MERGE_INTO = {"breast.L": "spine02", "breast.R": "spine02"}


def _to_blender(p):
    p = np.asarray(p, float)
    return np.stack([p[..., 0], -p[..., 2], p[..., 1]], axis=-1) * SCALE


def read_obj(path):
    verts, uvs, faces = [], [], []
    group = None
    for line in open(path, encoding="utf8"):
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("vt "):
            uvs.append([float(x) for x in line.split()[1:3]])
        elif line.startswith("g "):
            group = line.split()[1]
        elif line.startswith("f "):
            vi, ti = [], []
            for tok in line.split()[1:]:
                parts = tok.split("/")
                vi.append(int(parts[0]) - 1)
                ti.append(int(parts[1]) - 1 if len(parts) > 1 and parts[1] else -1)
            faces.append((group, vi, ti))
    return np.array(verts), np.array(uvs), faces


def read_target(path):
    idx, d = [], []
    for line in open(path, encoding="utf8"):
        if not line.strip() or line.startswith("#"):
            continue
        a = line.split()
        idx.append(int(a[0]))
        d.append([float(a[1]), float(a[2]), float(a[3])])
    return np.array(idx, int), np.array(d)


def morph(verts, mh_dir, targets):
    out = verts.copy()
    for name, w in targets.items():
        if not w:
            continue
        p = os.path.join(mh_dir, name + ".target")
        if not os.path.exists(p):
            print(f"[mh] target missing: {name}")
            continue
        i, d = read_target(p)
        out[i] += w * d
    return out


def build_body(mh_dir, targets, name="Rider"):
    """Returns (mesh object, armature object, joints dict in Blender coords)."""
    verts, uvs, faces = read_obj(os.path.join(mh_dir, "base.obj"))
    verts = morph(verts, mh_dir, targets)
    skel = json.load(open(os.path.join(mh_dir, "default.mhskel")))
    joints = {k: _to_blender(verts[v].mean(axis=0)) for k, v in skel["joints"].items()}
    # Body faces only (drop helper geometry and joint cubes); keep the original indices for the weights
    body = [(vi, ti) for g, vi, ti in faces if g == "body"]
    used = sorted({i for vi, _ in body for i in vi})
    remap = {old: new for new, old in enumerate(used)}
    bv = _to_blender(verts[used])
    me = bpy.data.meshes.new(name + "Mesh")
    me.from_pydata(bv.tolist(), [], [[remap[i] for i in vi] for vi, _ in body])
    uv = me.uv_layers.new(name="UVMap")
    k = 0
    for (vi, ti) in body:
        for t in ti:
            uv.data[k].uv = uvs[t] if t >= 0 else (0, 0)
            k += 1
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    # Armature
    arm_data = bpy.data.armatures.new(name + "Rig")
    arm = bpy.data.objects.new(name + "Rig", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    keep = [b for b in skel["bones"] if not b.startswith(DROP_PREFIX)]
    eb = {}
    for b in keep:
        spec = skel["bones"][b]
        e = arm_data.edit_bones.new(b)
        e.head = mathutils.Vector(joints[spec["head"]])
        e.tail = mathutils.Vector(joints[spec["tail"]])
        if (e.tail - e.head).length < 1e-4:
            e.tail = e.head + mathutils.Vector((0, 0, 0.02))
        eb[b] = e
    for b in keep:
        par = skel["bones"][b]["parent"]
        while par and par not in eb:
            par = skel["bones"][par]["parent"]
        if par:
            eb[b].parent = eb[par]
    for b in keep:
        pl = skel["bones"][b].get("rotation_plane")
        if pl and pl in skel["planes"]:
            a, b2, c = (mathutils.Vector(joints[j]) for j in skel["planes"][pl])
            n = (b2 - a).cross(c - a)
            if n.length > 1e-8:
                eb[b].align_roll(n.normalized())
    bpy.ops.object.mode_set(mode="OBJECT")
    # Weights (dropped bones → nearest kept ancestor)
    w = json.load(open(os.path.join(mh_dir, skel["weights_file"])))["weights"]

    def target_bone(b):
        if b in MERGE_INTO:
            return MERGE_INTO[b]
        while b and b not in eb:
            b = skel["bones"][b]["parent"]
        return b

    groups = {}
    acc = {}
    for b, lst in w.items():
        tb = target_bone(b) or "head"
        for vi, wt in lst:
            if vi in remap:
                acc.setdefault(tb, {}).setdefault(remap[vi], 0.0)
                acc[tb][remap[vi]] += wt
    for b, d in acc.items():
        g = groups[b] = ob.vertex_groups.new(name=b)
        for vi, wt in d.items():
            g.add([vi], min(1.0, wt), "REPLACE")
    ob.parent = arm
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return ob, arm, joints


def dominant_bone(ob):
    """Per vertex: the bone with the largest weight."""
    names = {g.index: g.name for g in ob.vertex_groups}
    dom = []
    for v in ob.data.vertices:
        best = max(v.groups, key=lambda g: g.weight, default=None)
        dom.append(names[best.group] if best else "")
    return dom
