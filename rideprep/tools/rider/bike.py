"""Procedural road / TT bike for the rider rig (headless Blender). Real-world geometry, metres.

Bike space: origin on the ground under the bottom bracket, +X forward, +Y left, +Z up. Parts are separate objects
with pivots where they move: frame (rigid), fork+cockpit+front wheel ("cockpit" mesh, pivot on the steering axis), rear wheel
(pivot at the axle), crankset (pivot at the BB, rotates about Y), pedals (pivot at the spindle, kept level by the rig).
`build_bike()` returns the objects plus the fit points the rider poses against (saddle, hoods/drops/pads, pedals).
"""
import math

import bpy  # noqa: I001
import bmesh
import mathutils
from mathutils import Vector

from kit import principled, srgb

WHEEL_R = 0.3345      # 700x25
TYRE_R = 0.0125
BB_H = 0.265          # 70 mm BB drop
CRANK = 0.1725


def geometry(kind, saddle_height, inseam=0.82, aero_fit=None):
    """Key frame points for a road or TT frame sized to the rider's inseam (56 cm road frame at 82 cm), plus fit points
    for a saddle height (BB→saddle top)."""
    bb = Vector((0, 0, BB_H))
    cs = 0.405
    rear = Vector((-math.sqrt(cs * cs - (WHEEL_R - BB_H) ** 2), 0, WHEEL_R))
    grow = inseam - 0.82
    if kind == "tt":
        stack, reach, ha, sa, ht = 0.53 + 0.5 * grow, 0.42 + 0.15 * grow, math.radians(72.5), math.radians(78.0), 0.11 + 0.4 * grow
    else:
        stack, reach, ha, sa, ht = 0.57 + 0.6 * grow, 0.39 + 0.15 * grow, math.radians(73.0), math.radians(73.5), 0.16 + 0.6 * grow
    ht_top = bb + Vector((reach, 0, stack))
    axis_up = Vector((-math.cos(ha), 0, math.sin(ha)))          # steering axis, pointing up/back
    ht_bot = ht_top - axis_up * ht
    rake = 0.045
    # fork length so the axle sits at wheel height
    nrm = Vector((math.sin(ha), 0, math.cos(ha)))               # perpendicular to the axis, forward
    L = (ht_bot.z + nrm.z * rake - WHEEL_R) / axis_up.z
    front = ht_bot - axis_up * L + nrm * rake
    seat_dir = Vector((-math.cos(sa), 0, math.sin(sa)))
    st_top = bb + seat_dir * ((0.53 if kind == "road" else 0.48) + 0.7 * grow)
    saddle = bb + seat_dir * saddle_height
    pts = {"bb": bb, "rear": rear, "front": front, "ht_top": ht_top, "ht_bot": ht_bot, "axis_up": axis_up, "st_top": st_top,
           "seat_dir": seat_dir, "saddle": saddle}
    # Cockpit: 20 mm spacer + 110 mm stem at −6°, 420 mm bar (c-c), 80 mm reach, 125 mm drop
    clamp_base = ht_top + axis_up * 0.02
    stem_dir = Vector((math.cos(math.radians(-6)), 0, math.sin(math.radians(-6))))
    bar = clamp_base + stem_dir * ((0.11 if kind == "road" else 0.09) + 0.25 * grow)
    pts.update({"stem_base": clamp_base, "bar": bar})
    if kind == "road":
        pts["hoods"] = bar + Vector((0.075, 0, 0.03))
        pts["drops"] = bar + Vector((0.03, 0, -0.11))
        pts["bar_half"] = 0.21
    else:
        pts["pads"] = bar + Vector((-0.01, 0, 0.07))        # elbow pads
        pts["ext"] = bar + Vector((0.30, 0, 0.09))          # extension ends
        pts["grip"] = pts["ext"] + Vector((-0.07, 0, 0.035))  # wrists, hands wrapped round the extension ends
        pts["bar_half"] = 0.2
        if aero_fit:  # cockpit fitted to the rider: pads under the elbows, wrists a forearm length ahead
            pts["pads"], pts["ext"], pts["grip"] = aero_fit["pads"], aero_fit["ext"], aero_fit["grip"]
            pts["bar"] = pts["pads"] + Vector((0.02, 0, -0.07))
        pts["horns"] = pts["bar"] + Vector((0.06, 0, 0.012))   # base-bar ends (climbing, out of the saddle)
    return pts


def _tube(bm, a, b, rx, ry=None, sides=16, mat=0, taper=1.0):
    """Tube from a to b with an elliptical section: rx in the frame plane, ry lateral (Y)."""
    ry = ry or rx
    a, b = Vector(a), Vector(b)
    d = (b - a).normalized()
    lat = Vector((0, 1, 0))
    if abs(d.dot(lat)) > 0.95:
        lat = Vector((1, 0, 0))
    n = d.cross(lat).normalized()
    lat = n.cross(d).normalized()
    rings = []
    for k, (p, s) in enumerate(((a, 1.0), (b, taper))):
        ring = []
        for i in range(sides):
            t = i / sides * math.tau
            ring.append(bm.verts.new(p + n * (math.cos(t) * rx * s) + lat * (math.sin(t) * ry * s)))
        rings.append(ring)
    for i in range(sides):
        f = bm.faces.new((rings[0][i], rings[0][(i + 1) % sides], rings[1][(i + 1) % sides], rings[1][i]))
        f.material_index = mat
        f.smooth = True
    for ring, rev in ((rings[0], True), (rings[1], False)):
        f = bm.faces.new(ring[::-1] if rev else ring)
        f.material_index = mat


def _lathe(bm, profile, centre, axis_y=True, segs=48, mat=0):
    """Revolve (radius, y-offset) profile points around the Y axis through `centre`."""
    rings = []
    for k in range(segs):
        t = k / segs * math.tau
        ring = [bm.verts.new(centre + Vector((math.cos(t) * r, y, math.sin(t) * r))) for r, y in profile]
        rings.append(ring)
    for k in range(segs):
        a, b = rings[k], rings[(k + 1) % segs]
        for i in range(len(profile) - 1):
            f = bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
            f.material_index = mat
            f.smooth = True


def _object(name, bm, mats, origin=Vector((0, 0, 0))):
    me = bpy.data.meshes.new(name)
    for v in bm.verts:
        v.co -= origin
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    ob.location = origin
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _wheel(name, centre, mats, disc=False, deep=0.05, spokes=20):
    bm = bmesh.new()
    # Tyre (torus) and deep carbon rim
    tyre = [(WHEEL_R - TYRE_R + TYRE_R * math.cos(t), TYRE_R * math.sin(t) * 0.95) for t in [i / 16 * math.tau for i in range(17)]]
    _lathe(bm, tyre, centre, segs=64, mat=0)
    rim = [(WHEEL_R - 2 * TYRE_R + 0.002, 0.0105), (WHEEL_R - 2 * TYRE_R - deep * 0.5, 0.0135), (WHEEL_R - 2 * TYRE_R - deep, 0.006),
           (WHEEL_R - 2 * TYRE_R - deep - 0.004, 0.0), (WHEEL_R - 2 * TYRE_R - deep, -0.006), (WHEEL_R - 2 * TYRE_R - deep * 0.5, -0.0135),
           (WHEEL_R - 2 * TYRE_R + 0.002, -0.0105)]
    _lathe(bm, rim, centre, segs=64, mat=1)
    hub_r = 0.022
    _tube(bm, centre + Vector((0, -0.05, 0)), centre + Vector((0, 0.05, 0)), 0.012, sides=12, mat=2)
    if disc:
        prof = [(hub_r, 0.03), (WHEEL_R - 2 * TYRE_R - deep * 0.6, 0.012), (WHEEL_R - 2 * TYRE_R - deep * 0.6, -0.012), (hub_r, -0.03)]
        _lathe(bm, prof, centre, segs=48, mat=1)
    else:
        for side in (-1, 1):
            _tube(bm, centre + Vector((0, side * 0.035, 0)), centre + Vector((0, side * 0.025, 0)), hub_r, sides=14, mat=2)
        for k in range(spokes):
            t = (k + 0.5 * (k % 2)) / spokes * math.tau
            side = 1 if k % 2 else -1
            a = centre + Vector((math.cos(t) * hub_r, side * 0.03, math.sin(t) * hub_r))
            b = centre + Vector((math.cos(t + 0.06) * (WHEEL_R - 2 * TYRE_R - deep), 0, math.sin(t + 0.06) * (WHEEL_R - 2 * TYRE_R - deep)))
            _tube(bm, a, b, 0.0012, sides=4, mat=2)
    return _object(name, bm, [mats["tyre"], mats["carbon"], mats["metal"]], origin=centre)


def build_bike(kind="road", frame_colour="#1d4ed8", saddle_height=0.74, inseam=0.82, aero_fit=None):
    pts = geometry(kind, saddle_height, inseam, aero_fit)
    mats = {"frame": principled("frame", srgb(frame_colour), 0.22, coat=1.0), "carbon": principled("carbon", (0.006, 0.006, 0.007), 0.35, coat=0.5, spec=0.3),
            "tyre": principled("tyre", (0.012, 0.012, 0.012), 0.85, spec=0.15), "metal": principled("alloy", (0.55, 0.56, 0.58), 0.28, metal=1.0),
            "dark": principled("dark", (0.03, 0.03, 0.035), 0.45), "tape": principled("bar_tape", (0.012, 0.012, 0.012), 0.9, spec=0.15),
            "saddle": principled("saddle", (0.012, 0.012, 0.013), 0.6, spec=0.25)}
    bb, rear, front, ht_top, ht_bot, st_top = (pts[k] for k in ("bb", "rear", "front", "ht_top", "ht_bot", "st_top"))
    aero = kind == "tt"
    # ---- frame
    bm = bmesh.new()
    _tube(bm, st_top + Vector((0.0, 0, 0.0)), ht_top - pts["axis_up"] * 0.03, 0.017 if not aero else 0.03, 0.016 if not aero else 0.012)
    _tube(bm, bb, ht_bot + pts["axis_up"] * 0.02, 0.024 if not aero else 0.035, 0.022 if not aero else 0.016)
    _tube(bm, bb + Vector((0, 0, 0)), st_top + pts["seat_dir"] * 0.02, 0.016 if not aero else 0.03, 0.015 if not aero else 0.012)
    _tube(bm, ht_bot - pts["axis_up"] * 0.01, ht_top + pts["axis_up"] * 0.005, 0.022 if not aero else 0.03, 0.021 if not aero else 0.015)
    for side in (-1, 1):
        y = Vector((0, side * 0.055, 0))
        _tube(bm, bb + Vector((0, side * 0.035, 0)), rear + y, 0.012, 0.009, sides=12, taper=0.75)
        _tube(bm, st_top - pts["seat_dir"] * 0.06 + Vector((0, side * 0.012, 0)), rear + y, 0.009, 0.008, sides=12, taper=0.8)
    _tube(bm, bb + Vector((0, -0.045, 0)), bb + Vector((0, 0.045, 0)), 0.021, sides=18)  # BB shell
    frame = _object("frame", bm, [mats["frame"]])
    # ---- rear wheel, cassette, derailleur, chain (frame-attached parts are part of the frame object below)
    rear_wheel = _wheel("wheel_rear", rear, mats, disc=aero, deep=0.06 if aero else 0.05, spokes=24)
    bm = bmesh.new()
    for k, r in enumerate((0.058, 0.052, 0.046, 0.041, 0.036, 0.032, 0.028, 0.025, 0.022, 0.02, 0.018)):
        _tube(bm, rear + Vector((0, -0.024 - k * 0.0038, 0)), rear + Vector((0, -0.0262 - k * 0.0038, 0)), r, sides=24, mat=0)
    rd = rear + Vector((0.01, -0.055, -0.065))
    _tube(bm, rear + Vector((0, -0.06, -0.01)), rd, 0.008, sides=8, mat=1)
    for dz in (0.0, -0.06):
        _tube(bm, rd + Vector((0, -0.006, dz)), rd + Vector((0, 0.006, dz)), 0.018, sides=16, mat=1)
    # chain: upper run (big ring top → cassette top) and lower run (via the derailleur) as thin bands
    ring_r = 0.105
    up_a, up_b = bb + Vector((0.0, -0.045, ring_r)), rear + Vector((0, -0.045, 0.045))
    lo_a, lo_b = bb + Vector((0.0, -0.045, -ring_r)), rd + Vector((0, -0.045, -0.06))
    for a, b in ((up_a, up_b), (lo_a, lo_b), (lo_b, rear + Vector((0, -0.045, -0.04)))):
        _tube(bm, a, b, 0.004, 0.0035, sides=6, mat=1)
    # front derailleur, bottle cage + bottle on the down tube, brake calipers
    _tube(bm, st_top.lerp(bb, 0.62) + Vector((0.04, -0.03, 0)), st_top.lerp(bb, 0.62) + Vector((0.075, -0.03, 0.01)), 0.012, 0.004, sides=8, mat=1)
    dt_mid = bb.lerp(ht_bot, 0.5)
    dt_dir = (ht_bot - bb).normalized()
    up = dt_dir.cross(Vector((0, 1, 0))).normalized() * -1
    _tube(bm, dt_mid - dt_dir * 0.1 + up * 0.04, dt_mid + dt_dir * 0.1 + up * 0.04, 0.036, sides=20, mat=2)
    drive = _object("drivetrain_static", bm, [mats["metal"], mats["dark"], principled("bottle", (0.8, 0.82, 0.85), 0.35)])
    # ---- crankset (pivot at the BB axis): chainrings, spider, arms, spindle
    bm = bmesh.new()
    for r, w in ((0.105, 0.0035), (0.078, 0.0035)):
        _tube(bm, bb + Vector((0, -0.043 + (0.006 if r < 0.1 else 0), 0)), bb + Vector((0, -0.043 - w + (0.006 if r < 0.1 else 0), 0)), r, sides=48, mat=1)
    _tube(bm, bb + Vector((0, -0.066, 0)), bb + Vector((0, 0.066, 0)), 0.012, sides=12, mat=0)
    for side in (-1, 1):
        y = side * 0.066
        # arms point opposite each other: right (drive, −Y) forward at 0°, left backward
        d = Vector((1, 0, 0)) if side < 0 else Vector((-1, 0, 0))
        _tube(bm, bb + Vector((0, y, 0)), bb + Vector((0, y, 0)) + d * CRANK, 0.014, 0.008, sides=10, mat=0, taper=0.7)
    cranks = _object("crankset", bm, [mats["dark"], mats["carbon"]], origin=bb)
    pedals = []
    for side in (-1, 1):
        d = Vector((1, 0, 0)) if side < 0 else Vector((-1, 0, 0))
        spindle = bb + Vector((0, side * 0.075, 0)) + d * CRANK
        bm = bmesh.new()
        body = spindle + Vector((0, side * 0.03, 0))
        bmesh.ops.create_cube(bm, size=1, matrix=mathutils.Matrix.LocRotScale(body, None, (0.09, 0.06, 0.016)))
        for f in bm.faces:
            f.material_index = 0
        _tube(bm, spindle, spindle + Vector((0, side * 0.06, 0)), 0.006, sides=8, mat=1)
        pedals.append(_object(f"pedal_{'L' if side > 0 else 'R'}", bm, [mats["dark"], mats["metal"]], origin=spindle))
    # ---- steer group: fork, steerer/stem, bar, hoods/aerobars, front wheel (pivot on the steering axis at the head tube)
    bm = bmesh.new()
    for side in (-1, 1):
        _tube(bm, ht_bot + Vector((0, side * 0.03, 0)), pts["front"] + Vector((0, side * 0.052, 0)), 0.016 if not aero else 0.022,
              0.013 if not aero else 0.009, sides=12, taper=0.6)
    _tube(bm, ht_top, pts["stem_base"], 0.016, sides=14, mat=1)  # spacer
    _tube(bm, pts["stem_base"], pts["bar"], 0.019, 0.017, sides=14, mat=1)  # stem
    half = pts["bar_half"]
    bar = pts["bar"]
    if not aero:
        _tube(bm, bar + Vector((0, -half, 0)), bar + Vector((0, half, 0)), 0.0125, sides=14, mat=2)
        for side in (-1, 1):
            y = Vector((0, side * half, 0))
            ramp = bar + y + Vector((0.07, 0, 0.0))
            _tube(bm, bar + y, ramp, 0.0125, sides=12, mat=2)
            hood = pts["hoods"] + Vector((0, side * half, 0))
            _tube(bm, ramp, hood + Vector((0.035, 0, 0.0)), 0.018, 0.016, sides=12, mat=1)  # lever hood
            prev = ramp
            for k in range(1, 9):  # drop curve
                t = k / 8 * math.pi
                p = bar + y + Vector((0.07 + math.sin(t) * 0.045, 0, -0.0625 + math.cos(t) * 0.0625))
                _tube(bm, prev, p, 0.0125, sides=12, mat=2)
                prev = p
            _tube(bm, prev, prev + Vector((-0.09, 0, 0)), 0.0125, sides=12, mat=2)
    else:
        _tube(bm, bar + Vector((0, -half, 0)), bar + Vector((0, half, 0)), 0.02, 0.008, sides=14, mat=1)  # base bar (aero)
        for side in (-1, 1):
            y = Vector((0, side * 0.1, 0))
            _tube(bm, pts["pads"] + y + Vector((-0.06, 0, 0)), pts["pads"] + y + Vector((0.06, 0, 0)), 0.028, 0.035, sides=12, mat=2)  # pad
            _tube(bm, pts["pads"] + y + Vector((0.0, 0, -0.03)), bar + y, 0.01, sides=8, mat=1)  # riser
            _tube(bm, pts["pads"] + y + Vector((0.04, side * -0.02, -0.01)), pts["ext"] + y * 0.7, 0.011, sides=12, mat=2)  # extension
    # computer on an out-front mount
    bmesh.ops.create_cube(bm, size=1, matrix=mathutils.Matrix.LocRotScale(bar + Vector((0.075, 0, 0.012)), None, (0.06, 0.045, 0.012)))
    steer = _object("cockpit", bm, [mats["frame"], mats["dark"], mats["tape"]], origin=ht_bot)
    front_wheel = _wheel("wheel_front", pts["front"], mats, disc=False, deep=0.06 if aero else 0.05, spokes=20)
    # ---- saddle and seat post
    bm = bmesh.new()
    s = pts["saddle"]
    _tube(bm, st_top, s - Vector((0, 0, 0.025)), 0.0135, sides=14, mat=1)
    rows = []
    for k in range(9):
        t = k / 8
        x = -0.11 + t * 0.27
        w = 0.07 * (1 - t) ** 0.8 + 0.016 if not aero else 0.06 * (1 - t) ** 0.6 + 0.02
        z = 0.012 + 0.004 * math.sin(t * math.pi) - (0.004 if t > 0.9 else 0)
        top = [bm.verts.new(s + Vector((x, y * w, z - (y * y) * 0.016))) for y in (-1, -0.6, 0, 0.6, 1)]
        bot = [bm.verts.new(s + Vector((x, y * w * 0.92, z - 0.03 - (y * y) * 0.006))) for y in (-1, -0.6, 0, 0.6, 1)]
        rows.append((top, bot))
    for k in range(8):
        for layer in (0, 1):
            for i in range(4):
                a, b = rows[k][layer], rows[k + 1][layer]
                f = bm.faces.new((a[i], b[i], b[i + 1], a[i + 1]) if layer == 0 else (a[i], a[i + 1], b[i + 1], b[i]))
                f.smooth = True
        for i in (0, 4):  # sides
            f = bm.faces.new((rows[k][0][i], rows[k][1][i], rows[k + 1][1][i], rows[k + 1][0][i]) if i == 0 else
                             (rows[k][0][i], rows[k + 1][0][i], rows[k + 1][1][i], rows[k][1][i]))
            f.smooth = True
    for k, rev in ((0, True), (8, False)):  # nose and tail caps
        ring = rows[k][0] + rows[k][1][::-1]
        bm.faces.new(ring[::-1] if rev else ring)
    saddle = _object("saddle", bm, [mats["saddle"], mats["dark"]])
    frame.name = "frame"
    parts = {"frame": frame, "drivetrain_static": drive, "wheel_rear": rear_wheel, "crankset": cranks, "pedal_L": pedals[1], "pedal_R": pedals[0],
             "steer": steer, "wheel_front": front_wheel, "saddle": saddle}
    return parts, pts
