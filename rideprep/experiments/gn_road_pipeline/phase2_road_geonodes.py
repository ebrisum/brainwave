"""Proposed structure — Phase 2 (Blender Geometry Nodes): road sweep with superelevation + UCX collision + FBX export.

  blender -b --python phase2_road_geonodes.py -- --blend phase1.blend --out-dir out/ [--design-kmh 60] [--emax 0.07]

Builds two node groups programmatically and applies them to copies of the Phase 1 curve:

GN_RoadVisual
  Resample Curve (2 m) → Set Curve Normal (Z Up) → Set Curve Tilt (superelevation) → Curve to Mesh (road profile:
  ditch | grass | gravel shoulder | asphalt 2×3.5 m | …) → materials by profile position → UVMap (u across, v along).
  Superelevation: signed horizontal curvature κ from the circumcircle of P[i−k], P[i], P[i+k] (Evaluate at Index),
  e = clamp(v²·κ/g, ±e_max), tilt = atan(e), blurred along the curve.
GN_RoadCollision
  Resample (10 m) → same banking → Curve to Points (rotation) → Instance on Points (one 10.4 × 9.2 × 0.6 m box per
  segment, top face on the road surface) → Realize. Each box is a convex island; UE's FBX importer splits a UCX_ mesh
  into connected islands (one convex element each).
Also builds the literal "single convex hull" variant for measurement only (GN_ConvexHull) — not exported.

Exports out/SM_Road_ER703.fbx (SM_Road_ER703 + UCX_SM_Road_ER703) and out/phase2_metrics.json.
"""
import argparse
import json
import math
import os
import sys
import time

import bpy  # noqa: I001
import bmesh
import mathutils
from mathutils.bvhtree import BVHTree

G = 9.81


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--blend", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--design-kmh", type=float, default=60.0)
    p.add_argument("--emax", type=float, default=0.07)
    p.add_argument("--no-export", action="store_true")
    return p.parse_args(argv)


# ---- node helpers -----------------------------------------------------------------------------------------------------


class T:
    def __init__(self, name):
        self.ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
        self.ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        self.ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        self.n = self.ng.nodes
        self.l = self.ng.links
        self.gin = self.n.new("NodeGroupInput")
        self.gout = self.n.new("NodeGroupOutput")

    def node(self, t, **props):
        nd = self.n.new(t)
        for k, v in props.items():
            setattr(nd, k, v)
        return nd

    def link(self, a, b):
        self.l.new(a, b)

    def math(self, op, a, b=None, c=None):
        m = self.node("ShaderNodeMath", operation=op)
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                m.inputs[i].default_value = v
            else:
                self.link(v, m.inputs[i])
        return m.outputs[0]

    def vmath(self, op, a, b=None):
        m = self.node("ShaderNodeVectorMath", operation=op)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (tuple, list)):
                m.inputs[i].default_value = v
            else:
                self.link(v, m.inputs[i])
        return m.outputs["Value"] if op in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else m.outputs["Vector"]


def bank_tilt(t, curve_socket, spacing_m, chord_m, design_kmh, emax):
    """Superelevation tilt field, evaluated on the curve passed to Set Curve Tilt."""
    k = max(1, int(round(chord_m / 2 / spacing_m)))
    idx = t.node("GeometryNodeInputIndex").outputs[0]
    size = t.node("GeometryNodeAttributeDomainSize", component="CURVE")
    t.link(curve_socket, size.inputs[0])
    last = t.math("SUBTRACT", size.outputs["Point Count"], 1)
    im = t.math("MAXIMUM", t.math("SUBTRACT", idx, k), 0)
    ip = t.math("MINIMUM", t.math("ADD", idx, k), last)
    pos = t.node("GeometryNodeInputPosition").outputs[0]
    flat = t.vmath("MULTIPLY", pos, (1, 1, 0))

    def at(i):
        f = t.node("GeometryNodeFieldAtIndex", data_type="FLOAT_VECTOR", domain="POINT")
        t.link(flat, f.inputs["Value"])
        t.link(i, f.inputs["Index"])
        return f.outputs[0]

    A, B, C = at(im), flat, at(ip)
    AB, AC, BC = t.vmath("SUBTRACT", B, A), t.vmath("SUBTRACT", C, A), t.vmath("SUBTRACT", C, B)
    cz = t.node("ShaderNodeSeparateXYZ")
    t.link(t.vmath("CROSS_PRODUCT", AB, AC), cz.inputs[0])
    denom = t.math("MAXIMUM", t.math("MULTIPLY", t.math("MULTIPLY", t.vmath("LENGTH", AB), t.vmath("LENGTH", BC)), t.vmath("LENGTH", AC)), 1e-3)
    kappa = t.math("DIVIDE", t.math("MULTIPLY", cz.outputs["Z"], 2.0), denom)  # signed 1/R (left turn > 0)
    v = design_kmh / 3.6
    e = t.math("MINIMUM", t.math("MAXIMUM", t.math("MULTIPLY", kappa, v * v / G), -emax), emax)
    tilt = t.math("ARCTANGENT", e)
    blur = t.node("GeometryNodeBlurAttribute", data_type="FLOAT")
    t.link(tilt, blur.inputs["Value"])
    blur.inputs["Iterations"].default_value = 6
    return blur.outputs[0]


def banked_curve(t, spacing, chord, design_kmh, emax, sign):
    rs = t.node("GeometryNodeResampleCurve")
    rs.inputs["Mode"].default_value = "Length"
    rs.inputs["Length"].default_value = spacing
    t.link(t.gin.outputs[0], rs.inputs["Curve"])
    nm = t.node("GeometryNodeSetCurveNormal")
    nm.inputs["Mode"].default_value = "Z Up"
    t.link(rs.outputs[0], nm.inputs["Curve"])
    st = t.node("GeometryNodeSetCurveTilt")
    t.link(nm.outputs[0], st.inputs["Curve"])
    tilt = bank_tilt(t, nm.outputs[0], spacing, chord, design_kmh, emax)
    t.link(t.math("MULTIPLY", tilt, sign), st.inputs["Tilt"])
    # Expose the tilt for measurement
    sa = t.node("GeometryNodeStoreNamedAttribute", data_type="FLOAT", domain="POINT")
    sa.inputs["Name"].default_value = "bank"
    t.link(st.outputs[0], sa.inputs["Geometry"])
    t.link(t.math("MULTIPLY", tilt, sign), sa.inputs["Value"])
    return sa.outputs[0]


def visual_group(profile_obj, mats, design_kmh, emax, sign):
    t = T("GN_RoadVisual")
    curve = banked_curve(t, 2.0, 10.0, design_kmh, emax, sign)
    cap = t.node("GeometryNodeCaptureAttribute", domain="POINT")
    cap.capture_items.new("FLOAT", "v")
    t.link(curve, cap.inputs["Geometry"])
    t.link(t.node("GeometryNodeSplineParameter").outputs["Length"], cap.inputs[1])
    # Profile with its lateral coordinate stored as "u"
    oi = t.node("GeometryNodeObjectInfo", transform_space="ORIGINAL")
    oi.inputs["Object"].default_value = profile_obj
    sep = t.node("ShaderNodeSeparateXYZ")
    t.link(t.node("GeometryNodeInputPosition").outputs[0], sep.inputs[0])
    su = t.node("GeometryNodeStoreNamedAttribute", data_type="FLOAT", domain="POINT")
    su.inputs["Name"].default_value = "u"
    t.link(oi.outputs["Geometry"], su.inputs["Geometry"])
    t.link(sep.outputs["X"], su.inputs["Value"])
    c2m = t.node("GeometryNodeCurveToMesh")
    t.link(cap.outputs["Geometry"], c2m.inputs["Curve"])
    t.link(su.outputs[0], c2m.inputs["Profile Curve"])
    # UVs: u across (m), v along (m)
    na = t.node("GeometryNodeInputNamedAttribute", data_type="FLOAT")
    na.inputs["Name"].default_value = "u"
    comb = t.node("ShaderNodeCombineXYZ")
    t.link(na.outputs["Attribute"], comb.inputs["X"])
    t.link(cap.outputs[1], comb.inputs["Y"])
    uv = t.node("GeometryNodeStoreNamedAttribute", data_type="FLOAT2", domain="CORNER")
    uv.inputs["Name"].default_value = "UVMap"
    t.link(c2m.outputs[0], uv.inputs["Geometry"])
    t.link(comb.outputs[0], uv.inputs["Value"])
    # Materials by |u| (face average)
    absu = t.math("ABSOLUTE", na.outputs["Attribute"])
    geo = uv.outputs[0]
    for limit, mat in ((99.0, mats["grass"]), (4.6, mats["gravel"]), (3.55, mats["asphalt"])):
        sm = t.node("GeometryNodeSetMaterial")
        sm.inputs["Material"].default_value = mat
        t.link(geo, sm.inputs["Geometry"])
        t.link(t.math("LESS_THAN", absu, limit), sm.inputs["Selection"])
        geo = sm.outputs[0]
    t.link(geo, t.gout.inputs[0])
    return t.ng


def collision_group(design_kmh, emax, sign, seg=10.0, width=9.2, thick=0.6):
    t = T("GN_RoadCollision")
    curve = banked_curve(t, seg, 10.0, design_kmh, emax, sign)
    c2p = t.node("GeometryNodeCurveToPoints", mode="EVALUATED")
    t.link(curve, c2p.inputs["Curve"])
    cube = t.node("GeometryNodeMeshCube")
    cube.inputs["Size"].default_value = (thick, width, seg * 1.04)  # local Z = tangent, X = normal (see orientation probe)
    tr = t.node("GeometryNodeTransform")
    t.link(cube.outputs["Mesh"], tr.inputs["Geometry"])
    tr.inputs["Translation"].default_value = (-thick / 2, 0, seg / 2)
    iop = t.node("GeometryNodeInstanceOnPoints")
    t.link(c2p.outputs["Points"], iop.inputs["Points"])
    t.link(tr.outputs[0], iop.inputs["Instance"])
    t.link(c2p.outputs["Rotation"], iop.inputs["Rotation"])
    rl = t.node("GeometryNodeRealizeInstances")
    t.link(iop.outputs[0], rl.inputs["Geometry"])
    t.link(rl.outputs[0], t.gout.inputs[0])
    return t.ng


def hull_group():
    t = T("GN_ConvexHull")
    rs = t.node("GeometryNodeResampleCurve")
    rs.inputs["Mode"].default_value = "Length"
    rs.inputs["Length"].default_value = 10.0
    t.link(t.gin.outputs[0], rs.inputs["Curve"])
    line = t.node("GeometryNodeCurvePrimitiveLine")
    line.inputs["Start"].default_value = (-4.6, 0, 0)
    line.inputs["End"].default_value = (4.6, 0, 0)
    c2m = t.node("GeometryNodeCurveToMesh")
    t.link(rs.outputs[0], c2m.inputs["Curve"])
    t.link(line.outputs[0], c2m.inputs["Profile Curve"])
    hull = t.node("GeometryNodeConvexHull")
    t.link(c2m.outputs[0], hull.inputs[0])
    t.link(hull.outputs[0], t.gout.inputs[0])
    return t.ng


# ---- scene ------------------------------------------------------------------------------------------------------------


def make_profile():
    """Road cross-section in the profile's XY plane (X lateral, Y up): ditch | verge | shoulder | 2×3.5 m asphalt."""
    xs = [-7.6, -6.6, -5.6, -4.6, -3.5, 0.0, 3.5, 4.6, 5.6, 6.6, 7.6]
    ys = [0.4, -0.45, -0.1, -0.03, 0.0, 0.07, 0.0, -0.03, -0.1, -0.45, 0.4]  # 2 % crown, ditch 45 cm
    cu = bpy.data.curves.new("Road_Profile", "CURVE")
    sp = cu.splines.new("POLY")
    sp.points.add(len(xs) - 1)
    for p, x, y in zip(sp.points, xs, ys):
        p.co = (x, y, 0, 1)
    ob = bpy.data.objects.new("Road_Profile", cu)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def material(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*rgb, 1)
    return m


def evaluated_mesh_object(src, name):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(src.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for m in src.evaluated_get(dg).data.materials if hasattr(src.evaluated_get(dg).data, "materials") else []:
        pass
    return ob


def orientation_probe(profile, mats, design_kmh, emax):
    """Which way do the profile's +X and the tilt sign go? Build a left-turning arc and look at the result."""
    cu = bpy.data.curves.new("probe", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    pts = [(200 * math.sin(a), 200 - 200 * math.cos(a), 0) for a in [i * 0.01 for i in range(60)]]  # CCW (left turn), R 200 m
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (*c, 1)
    ob = bpy.data.objects.new("probe", cu)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("v", "NODES")
    mod.node_group = visual_group(profile, mats, design_kmh, emax, 1.0)
    m = evaluated_mesh_object(ob, "probe_mesh")
    u = m.data.attributes["u"].data
    mid = [v for v in m.data.vertices if 0.2 < math.atan2(v.co.x, 200 - v.co.y) < 0.4]
    left = [v for i, v in enumerate(m.data.vertices) if v in mid and u[v.index].value > 3]
    right = [v for i, v in enumerate(m.data.vertices) if v in mid and u[v.index].value < -3]
    # +u side radius vs centre (inner side of a left turn is closer to (0, 200))
    r_plus = sum(math.dist((v.co.x, v.co.y), (0, 200)) for v in left) / max(len(left), 1)
    r_minus = sum(math.dist((v.co.x, v.co.y), (0, 200)) for v in right) / max(len(right), 1)
    plus_is_inner = r_plus < r_minus
    z_plus = sum(v.co.z for v in left) / max(len(left), 1)
    z_minus = sum(v.co.z for v in right) / max(len(right), 1)
    inner_lower = (z_plus < z_minus) if plus_is_inner else (z_minus < z_plus)
    for o in (ob, m):
        bpy.data.objects.remove(o)
    bpy.data.node_groups.remove(mod.node_group) if mod.node_group else None
    return plus_is_inner, inner_lower


def main():
    a = args()
    bpy.ops.wm.open_mainfile(filepath=a.blend)
    os.makedirs(a.out_dir, exist_ok=True)
    route = bpy.data.objects["GPX_Route"]
    mats = {"asphalt": material("M_Road_Asphalt", (0.05, 0.05, 0.05)), "gravel": material("M_Road_Gravel", (0.3, 0.27, 0.22)),
            "grass": material("M_Road_Verge", (0.1, 0.16, 0.04))}
    profile = make_profile()
    plus_inner, inner_lower = orientation_probe(profile, mats, a.design_kmh, a.emax)
    sign = 1.0 if inner_lower else -1.0
    metrics = {"profilePlusXIsInnerOnLeftTurn": plus_inner, "tiltSign": sign}
    # Visual
    t0 = time.time()
    vis_src = route.copy()
    vis_src.data = route.data.copy()
    bpy.context.scene.collection.objects.link(vis_src)
    mod = vis_src.modifiers.new("GN_RoadVisual", "NODES")
    mod.node_group = visual_group(profile, mats, a.design_kmh, a.emax, sign)
    vis = evaluated_mesh_object(vis_src, "SM_Road_ER703")
    metrics["visualEvalS"] = round(time.time() - t0, 2)
    metrics["visualTriangles"] = sum(len(p.vertices) - 2 for p in vis.data.polygons)
    bank = [d.value for d in vis.data.attributes["bank"].data] if "bank" in vis.data.attributes else []
    if bank:
        e = [abs(math.tan(b)) for b in bank]
        metrics["bank"] = {"maxPct": round(100 * max(e), 2), "shareOver2Pct": round(sum(x > 0.02 for x in e) / len(e), 3),
                           "shareAtMax": round(sum(x > a.emax - 1e-3 for x in e) / len(e), 3)}
    # Collision (per-segment convex boxes)
    t0 = time.time()
    col_src = route.copy()
    col_src.data = route.data.copy()
    bpy.context.scene.collection.objects.link(col_src)
    mod = col_src.modifiers.new("GN_RoadCollision", "NODES")
    mod.node_group = collision_group(a.design_kmh, a.emax, sign)
    ucx = evaluated_mesh_object(col_src, "UCX_SM_Road_ER703")
    metrics["collisionEvalS"] = round(time.time() - t0, 2)
    bm = bmesh.new()
    bm.from_mesh(ucx.data)
    islands = 0
    seen = set()
    for v in bm.verts:
        if v.index in seen:
            continue
        islands += 1
        stack = [v]
        while stack:
            q = stack.pop()
            if q.index in seen:
                continue
            seen.add(q.index)
            stack.extend(e.other_vert(q) for e in q.link_edges)
    bm.free()
    metrics["ucxIslands"] = islands
    metrics["ucxTriangles"] = sum(len(p.vertices) - 2 for p in ucx.data.polygons)
    # Literal single convex hull: how far above the road would a tyre ray hit it?
    hull_src = route.copy()
    hull_src.data = route.data.copy()
    bpy.context.scene.collection.objects.link(hull_src)
    mod = hull_src.modifiers.new("GN_ConvexHull", "NODES")
    mod.node_group = hull_group()
    hull = evaluated_mesh_object(hull_src, "UCX_naive_hull")
    bvh = BVHTree.FromObject(hull, bpy.context.evaluated_depsgraph_get())
    gaps = []
    for sp in route.data.splines:
        for bp in list(sp.bezier_points)[::20]:
            o = mathutils.Vector((bp.co.x, bp.co.y, 5000))
            hit = bvh.ray_cast(o, mathutils.Vector((0, 0, -1)))
            if hit[0] is not None:
                gaps.append(hit[0].z - bp.co.z)
    gaps.sort()
    metrics["singleHull"] = {"vertices": len(hull.data.vertices), "rayHitAboveRoadM": {"median": round(gaps[len(gaps) // 2], 1),
                             "p90": round(gaps[int(len(gaps) * 0.9)], 1), "max": round(gaps[-1], 1)}}
    bm = bmesh.new()
    bm.from_mesh(hull.data)
    metrics["singleHull"]["volumeKm3"] = round(bm.calc_volume() / 1e9, 3)
    bm.free()
    # Export
    for o in (vis_src, col_src, hull_src, profile):
        o.hide_set(True)
    if not a.no_export:
        bpy.ops.object.select_all(action="DESELECT")
        vis.select_set(True)
        ucx.select_set(True)
        bpy.context.view_layer.objects.active = vis
        path = os.path.join(a.out_dir, "SM_Road_ER703.fbx")
        t0 = time.time()
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True, apply_scale_options="FBX_SCALE_UNITS", axis_forward="-Y", axis_up="Z",
                                 mesh_smooth_type="FACE", use_mesh_modifiers=False, add_leaf_bones=False, bake_anim=False, path_mode="AUTO")
        metrics["fbxExportS"] = round(time.time() - t0, 2)
        metrics["fbxMB"] = round(os.path.getsize(path) / 1e6, 1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(a.out_dir, "phase2.blend"))
    json.dump(metrics, open(os.path.join(a.out_dir, "phase2_metrics.json"), "w"), indent=1)
    print(json.dumps(metrics, indent=1))


if __name__ == "__main__":
    main()
