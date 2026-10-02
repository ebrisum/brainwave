"""Cycling kit for the MakeHuman rider: material regions on the body (jersey, bib shorts, socks, shoes, gloves, skin)
from dominant bones, plus a helmet and sunglasses bone-parented to the head."""
import math

import bpy  # noqa: I001
import bmesh
import mathutils

import mh

JERSEY = {"spine05", "spine04", "spine03", "spine02", "spine01", "clavicle.L", "clavicle.R", "shoulder01.L", "shoulder01.R",
          "upperarm01.L", "upperarm01.R"}
SHORTS = {"root", "pelvis.L", "pelvis.R", "upperleg01.L", "upperleg01.R", "upperleg02.L", "upperleg02.R"}
GLOVES = {"wrist.L", "wrist.R"} | {f"metacarpal{i}.{s}" for i in range(1, 5) for s in "LR"} | {f"finger{i}-1.{s}" for i in range(1, 6) for s in "LR"}


def principled(name, rgb, rough=0.6, metal=0.0, sss=0.0, coat=0.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Specular IOR Level"].default_value = spec
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
        b.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
        b.inputs["Subsurface Scale"].default_value = 0.01
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    return m


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def cut_hems(body, arm):
    """Straight hems: bisect the limbs with planes perpendicular to their bones (sleeves, shorts legs, sock tops),
    each cut restricted to the faces of that limb so other body parts at the same height stay untouched."""
    bones = arm.data.bones
    dom = mh.dominant_bone(body)
    cuts = []
    for s in "LR":
        ua, la = bones[f"upperarm01.{s}"], bones[f"upperarm02.{s}"]
        cuts.append(({f"upperarm01.{s}", f"upperarm02.{s}"}, ua.head_local.lerp(la.tail_local, 0.42), (la.tail_local - ua.head_local).normalized()))
        th, kn = bones[f"upperleg01.{s}"], bones[f"lowerleg01.{s}"]
        cuts.append(({f"upperleg01.{s}", f"upperleg02.{s}", f"lowerleg01.{s}"}, th.head_local.lerp(kn.head_local, 0.84),
                     (kn.head_local - th.head_local).normalized()))
        sh, ft = bones[f"lowerleg01.{s}"], bones[f"foot.{s}"]
        cuts.append(({f"lowerleg01.{s}", f"lowerleg02.{s}"}, ft.head_local + (sh.head_local - ft.head_local).normalized() * 0.13,
                     (sh.head_local - ft.head_local).normalized()))
    # Waist (jersey over the bib shorts) and neckline: planes perpendicular to the spine / neck
    hip = (bones["upperleg01.L"].head_local + bones["upperleg01.R"].head_local) / 2
    sp = bones["spine05"]
    up = (bones["spine03"].head_local - sp.head_local).normalized()
    cuts.append(({"root", "pelvis.L", "pelvis.R", "spine05", "spine04"}, hip + up * 0.12, up))
    nk = bones["neck01"]
    nd = (nk.tail_local - nk.head_local).normalized()
    cuts.append(({"neck01", "neck02", "spine01", "clavicle.L", "clavicle.R"}, nk.head_local + nd * 0.01, nd))
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    deform = bm.verts.layers.deform.active
    names = {g.index: g.name for g in body.vertex_groups}

    def dom_of(v):
        d = v[deform] if deform else {}
        return names[max(d.items(), key=lambda kv: kv[1])[0]] if d else ""
    for limb, co, n in cuts:
        faces = [f for f in bm.faces if sum(dom_of(v) in limb for v in f.verts) >= 2]
        geom = list({e for f in faces for e in f.edges}) + faces + list({v for f in faces for v in f.verts})
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=n, clear_inner=False, clear_outer=False)
    bm.to_mesh(body.data)
    bm.free()
    return cuts


def apply_kit(body, arm, kit):
    """kit: {jersey, jerseyAccent, shorts, socks, shoes, skin} hex colours."""
    mats = {
        "skin": principled("skin", srgb(kit.get("skin", "#c58c6b")), 0.48, sss=0.12),
        "jersey": principled("jersey", srgb(kit["jersey"]), 0.55),
        "shorts": principled("shorts", srgb(kit.get("shorts", "#15171a")), 0.42),
        "socks": principled("socks", srgb(kit.get("socks", "#f2f2f2")), 0.8),
        "shoes": principled("shoes", srgb(kit.get("shoes", "#f5f5f5")), 0.3, coat=0.4),
        "gloves": principled("gloves", srgb(kit.get("gloves", "#1b1c1f")), 0.7),
    }
    me = body.data
    for k in ("skin", "jersey", "shorts", "socks", "shoes", "gloves"):
        me.materials.append(mats[k])
    slot = {k: i for i, k in enumerate(("skin", "jersey", "shorts", "socks", "shoes", "gloves"))}
    cuts = cut_hems(body, arm)
    dom = mh.dominant_bone(body)
    bones = arm.data.bones

    def side_of(p, limb_bones):
        for limb, co, n in cuts:
            if limb_bones & limb:
                return (p - co).dot(n)
        return 0.0

    for p in me.polygons:
        c = p.center
        votes = {}
        for vi in p.vertices:
            votes[dom[vi]] = votes.get(dom[vi], 0) + 1
        b = max(votes, key=votes.get)
        s = b[-1] if b[-2:] in (".L", ".R") else "L"
        if b.startswith("foot"):
            r = "shoes"
        elif b.startswith(("lowerleg01", "lowerleg02")):
            ft = bones[f"foot.{s}"].head_local
            n = (bones[f"lowerleg01.{s}"].head_local - ft).normalized()
            h = (c - ft).dot(n)
            r = "shoes" if h < 0.035 else "socks" if h < 0.13 else ("shorts" if side_of(c, {f"lowerleg01.{s}"}) < 0 else "skin")
        elif b in SHORTS or b in ("spine05", "spine04"):
            waist = cuts[-2]
            above = (c - waist[1]).dot(waist[2]) > 0
            if b in ("root", "pelvis.L", "pelvis.R", "spine05", "spine04"):
                r = "jersey" if above else "shorts"
            else:
                r = "shorts" if side_of(c, {f"upperleg01.{s}"}) < 0 else "skin"
        elif b.startswith("upperarm"):
            r = "jersey" if side_of(c, {f"upperarm01.{s}"}) < 0 else "skin"
        elif b in JERSEY or b.startswith("neck"):
            neck = cuts[-1]
            r = "jersey" if (c - neck[1]).dot(neck[2]) < 0 else "skin"
        elif b in GLOVES:
            r = "gloves"
        else:
            r = "skin"
        p.material_index = slot[r]
    return mats


def head_frame(body, arm):
    """Head centre and size from vertices weighted mostly to the head (rest pose)."""
    dom = mh.dominant_bone(body)
    pts = [v.co.copy() for i, v in enumerate(body.data.vertices) if dom[i] == "head"]
    lo = mathutils.Vector([min(p[k] for p in pts) for k in range(3)])
    hi = mathutils.Vector([max(p[k] for p in pts) for k in range(3)])
    return (lo + hi) / 2, hi - lo, lo, hi


def add_helmet(body, arm, colour="#f2f2f2", accent="#1a1a1a"):
    c, size, lo, hi = head_frame(body, arm)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=72, v_segments=36, radius=1.0)
    # Elongated road helmet: longer to the back, covers the top 55 % of the head
    for v in bm.verts:
        x, y, z = v.co
        v.co = mathutils.Vector((x * size.x * 0.62, y * size.y * 0.7 - (0.018 if y > 0 else 0.0) * (y), z * size.z * 0.52))
        if v.co.y > 0:
            v.co.y *= 1.12  # tail toward the back (+Y is the back of the head here: MakeHuman faces −Y in Blender)
    cut = -size.z * 0.06
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < cut], context="VERTS")
    # Vents: lower a few longitudinal strips (as an accent material), shell thickness via solidify
    me = bpy.data.meshes.new("Helmet")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Helmet", me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(principled("helmet", srgb(colour), 0.25, coat=0.6))
    me.materials.append(principled("helmet_vents", srgb(accent), 0.6))
    for p in me.polygons:
        p.use_smooth = True
        cx = p.center.x / max(size.x * 0.62, 1e-6)
        zz = p.center.z / max(size.z * 0.52, 1e-6)
        if zz < 0.14:  # dark lower rim band; clean shell above
            p.material_index = 1
    sol = ob.modifiers.new("shell", "SOLIDIFY")
    sol.thickness = 0.022
    sol.offset = 1.0
    ob.location = c + mathutils.Vector((0, 0.006, size.z * 0.17))
    _parent_to_bone(ob, arm, "head")
    return ob


def add_glasses(body, arm, lens="#20262b", frame="#f4f4f4"):
    c, size, lo, hi = head_frame(body, arm)
    bm = bmesh.new()
    # Wrap lens: a band of a vertical cylinder in front of the eyes
    r = size.x * 0.5 + 0.012
    h = size.z * 0.12
    segs = 24
    ring_lo, ring_hi = [], []
    for k in range(segs + 1):
        a = math.radians(-75 + 150 * k / segs)
        x, y = math.sin(a) * r, -math.cos(a) * r * 0.95
        ring_lo.append(bm.verts.new((x, y, -h / 2)))
        ring_hi.append(bm.verts.new((x, y, h / 2 * (1 - 0.25 * abs(math.sin(a))))))
    for k in range(segs):
        bm.faces.new((ring_lo[k], ring_lo[k + 1], ring_hi[k + 1], ring_hi[k]))
    me = bpy.data.meshes.new("Glasses")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Glasses", me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(principled("lens", srgb(lens), 0.05, metal=0.6, coat=1.0))
    sol = ob.modifiers.new("t", "SOLIDIFY")
    sol.thickness = 0.003
    ob.location = mathutils.Vector((c.x, c.y - 0.004, lo.z + size.z * 0.6))
    _parent_to_bone(ob, arm, "head")
    return ob


def add_shoes(body, arm, colour="#f7f7f7", sole="#151515"):
    """Road shoes: a lofted shell around each foot (heel cup → toe box), skinned 100 % to the foot bone."""
    shell = principled("shoe_shell", srgb(colour), 0.32, coat=0.5)
    sole_m = principled("shoe_sole", srgb(sole), 0.5)
    out = []
    for s in "LR":
        fb = arm.data.bones[f"foot.{s}"]
        ankle = fb.head_local.copy()
        fwd = (fb.tail_local - fb.head_local)
        fwd.z = 0
        fwd.normalize()
        lat = fwd.cross(mathutils.Vector((0, 0, 1))).normalized()
        ground = min(v.co.z for v in body.data.vertices if (v.co - ankle).length < 0.3)
        # (distance along the foot from the heel, half width, top height) sections; heel 7 cm behind the ankle
        prof = [(-0.075, 0.032, 0.085), (-0.06, 0.04, 0.095), (-0.02, 0.045, 0.1), (0.04, 0.05, 0.085), (0.09, 0.053, 0.06),
                (0.14, 0.05, 0.045), (0.175, 0.04, 0.035), (0.2, 0.024, 0.025), (0.212, 0.008, 0.016)]
        bm = bmesh.new()
        rings = []
        for d, w, h in prof:
            ring = []
            for k in range(16):
                t = k / 16 * math.tau
                y = math.cos(t) * w
                z = (math.sin(t) * 0.5 + 0.5) * h
                p = ankle + fwd * d + lat * y
                p.z = ground + z - 0.004
                ring.append(bm.verts.new(p))
            rings.append(ring)
        for a, b in zip(rings[:-1], rings[1:]):
            for k in range(16):
                f = bm.faces.new((a[k], a[(k + 1) % 16], b[(k + 1) % 16], b[k]))
                f.smooth = True
                f.material_index = 1 if (math.sin((k + 0.5) / 16 * math.tau) < -0.6) else 0
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
        me = bpy.data.meshes.new(f"Shoe.{s}")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(shell)
        me.materials.append(sole_m)
        ob = bpy.data.objects.new(f"Shoe.{s}", me)
        bpy.context.scene.collection.objects.link(ob)
        g = ob.vertex_groups.new(name=f"foot.{s}")
        g.add(list(range(len(me.vertices))), 1.0, "REPLACE")
        ob.parent = arm
        mod = ob.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
        out.append(ob)
    # Hide the bare feet inside the shoes: drop the faces below the sock line
    me = body.data
    shoes_slot = [i for i, m in enumerate(me.materials) if m.name.startswith("shoes")]
    if shoes_slot:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index == shoes_slot[0]], context="FACES")
        bm.to_mesh(me)
        bm.free()
    return out


def _parent_to_bone(ob, arm, bone):
    """Bone-parent keeping the current world transform (a bone parent's origin is the bone's tail)."""
    b = arm.data.bones[bone]
    ob.parent = arm
    ob.parent_type = "BONE"
    ob.parent_bone = bone
    ob.matrix_parent_inverse = (arm.matrix_world @ b.matrix_local @ mathutils.Matrix.Translation((0, b.length, 0))).inverted()
