"""
VERDIO - Ground Floor - parametric conceptual massing
=====================================================
Boutique high-performance coastal poshtel.  Blender 4.2 LTS or newer.

Run it:  Scripting workspace -> Open this file -> Run Script
         or headless:  blender -b -P verdio_ground_floor.py
Re-running rebuilds the "VERDIO" collection in place.  Materials are rebuilt
under the same names, so nothing piles up as .001 copies.

Plan convention: +X = east, +Y = north, Z up, 1 unit = 1 m.
The coast / sea is SOUTH (-Y).  Plate 25.0 x 16.0 m = 400 m2 gross.

    N  y=16.00
    +-------------------------------------------------+
    |  LIBRARY / COWORK      #  ENDURANCE      | WET  |
    |  dark oak, panelled    #  KICKR + BJJ    | CORE |
    |  80.6 m2               #  58.5 m2        |20.7  |
    +------------------+-----#-----------+-----+------+  y=8.75
    |  CULINARY CORE   |  LOUNGE         | MUDROOM    |
    |  grill + table   |  dark oak       | terracotta |
    |  75.1 m2         |  73.0 m2        | 50.2 m2    |
    +-------------------------------------------------+  y=0
    x=0               9.5   12.5        18.5  21.5   25
                  ~~~~~~~~~  COAST / SEA  ~~~~~~~~~
    #  = steel-and-glass Kamer en suite partition (x = 12.5)
    (areas are net, inside the walls)

Routes: beach -> mudroom (terracotta) -> lounge (oak), or mudroom ->
wet core -> endurance room.  The library is reached from the lounge.  The
library and the endurance room face north on purpose: no solar gain on the
room you climate-control, and no glare on screens.  The coast-facing rooms
get the low sun on oak and plaster.

The en suite leaves are driven by the custom property "open" (0-1) on the
empty "EnSuite_CONTROL".  Drag it to slide all four leaves into their pockets.
"""

import math
import os
import random

import bpy
import bmesh
from mathutils import Vector

# =============================================================================
# 1. PARAMETERS.  Change these and re-run; the model rebuilds from them.
# =============================================================================
PLATE_X, PLATE_Y = 25.0, 16.0   # 400 m2 gross
EXT_T = 0.35                    # exterior wall: solid masonry plus Rotband
INT_T = 0.20                    # internal masonry partitions
H = 3.60                        # floor to ceiling, a generous 1930s height
SLAB_T = 0.25
FINISH_T = 0.03                 # floor finish build-up

# Wall centre-lines that set out the zones
Y_SPLIT = 8.75          # coast band (south) | rear band (north)
X_KITCHEN_LNG = 9.50    # culinary core | lounge
X_LNG_MUD = 18.50       # lounge | mudroom (the wet-to-dry threshold)
X_ENSUITE = 12.50       # library | endurance (Kamer en suite axis)
X_END_WET = 21.50       # endurance | wet core

# Kamer en suite partition
ES_DEPTH = 0.60         # deep 1930s partition: vitrines plus pocket cavity
ES_OPENING = 3.20       # clear width of the sliding-door opening
ES_CABINET = 1.30       # flanking vitrine cabinet, each side
ES_DOOR_HEAD = 2.75     # underside of the steel "kalf" (transom rail)
ES_TRANSOM_TOP = 3.30   # top of the "bovenlicht" glazing; plaster bulkhead above
ES_SKIN_GAP = 0.10      # acoustic cavity between the two glass skins
ES_OPEN = 0.0           # 0 = closed (acoustic and climate seal), 1 = pocketed
ES_LEAF_GRID = (2, 5)   # Crittall-style divided lights per leaf (cols, rows)

LIBRARY_PANEL_H = 2.40  # full-height oak panelling, to picture-rail height
LOUNGE_DADO_H = 1.10    # country-house dado panelling

# Site and light
SITE_ROTATION_DEG = 0.0     # rotate the building against the sun (-90: coast faces west)
SUN_AZIMUTH_DEG = 235.0     # compass bearing of the sun: 0 N, 90 E, 180 S (coast), 270 W
SUN_ELEVATION_DEG = 16.0    # low, late-afternoon raking light
SUN_STRENGTH = 4.5
EXPOSURE = 1.5               # interiors sit ~+1.5 EV over the exterior
HDRI_PATH = ""              # absolute path to an .exr/.hdr; empty = procedural sky
HDRI_STRENGTH = 1.0
HDRI_ROTATION_DEG = 0.0

BUILD_PROPS = True
BUILD_CEILING = True
BUILD_PRACTICALS = True
HERO_PLASTER = False        # voxel-remesh the walls + true displacement (Cycles; heavy)
HERO_VOXEL = 0.04
REMOVE_DEFAULT_OBJECTS = True   # delete the startup Cube / Light / Camera

SPACE_BLUE = "#1D2951"

# Derived interior faces
XI0, XI1 = EXT_T, PLATE_X - EXT_T
YI0, YI1 = EXT_T, PLATE_Y - EXT_T
HT = INT_T / 2
YS0, YS1 = Y_SPLIT - HT, Y_SPLIT + HT
ES_HALF = ES_DEPTH / 2


# =============================================================================
# 2. HELPERS
# =============================================================================
def lin(hex_str):
    """sRGB hex to scene-linear RGBA.  Blender colour sockets are linear, so
    #1D2951 typed straight in as 0.11/0.16/0.32 would render far too light."""
    h = hex_str.lstrip("#")

    def c(v):
        v = int(v, 16) / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return (c(h[0:2]), c(h[2:4]), c(h[4:6]), 1.0)


class MB:
    """Accumulates axis-aligned boxes into one bmesh, one material slot per key."""

    def __init__(self):
        self.bm = bmesh.new()
        self.mats = []

    def box(self, x0, y0, z0, x1, y1, z1, mat):
        xa, xb = sorted((x0, x1))
        ya, yb = sorted((y0, y1))
        za, zb = sorted((z0, z1))
        if xb - xa < 1e-5 or yb - ya < 1e-5 or zb - za < 1e-5:
            return
        if mat not in self.mats:
            self.mats.append(mat)
        idx = self.mats.index(mat)
        v = [self.bm.verts.new(p) for p in (
            (xa, ya, za), (xb, ya, za), (xb, yb, za), (xa, yb, za),
            (xa, ya, zb), (xb, ya, zb), (xb, yb, zb), (xa, yb, zb))]
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                  (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.bm.faces.new([v[i] for i in f]).material_index = idx

    def build(self, name, col, location=(0.0, 0.0, 0.0)):
        if not self.bm.verts:
            self.bm.free()
            return None
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        self.bm.free()
        for key in self.mats:
            me.materials.append(MAT[key])
        ob = bpy.data.objects.new(name, me)
        ob.location = location
        col.objects.link(ob)
        return ob


def abox(mb, axis, p0, p1, a0, a1, z0, z1, mat):
    """Box in wall space: `a` runs along the wall axis, `p` across it."""
    if axis == "x":
        mb.box(a0, p0, z0, a1, p1, z1, mat)
    else:
        mb.box(p0, a0, z0, p1, a1, z1, mat)


def solid_pieces(A0, A1, hmax, openings):
    """Split a run [A0, A1] x [0, hmax] around openings (a0, a1, sill, head)
    into solid rectangles: full-height piers, under-sill aprons, lintels."""
    ops = sorted((max(A0, o0), min(A1, o1), s, h)
                 for o0, o1, s, h in openings if o1 > A0 and o0 < A1)
    out, cur = [], A0
    for o0, o1, s, h in ops:
        if o0 > cur:
            out.append((cur, o0, 0.0, hmax))
        if s > 0:
            out.append((o0, o1, 0.0, min(s, hmax)))
        if h < hmax:
            out.append((o0, o1, h, hmax))
        cur = max(cur, o1)
    if cur < A1:
        out.append((cur, A1, 0.0, hmax))
    return [p for p in out if p[1] - p[0] > 1e-4 and p[3] - p[2] > 1e-4]


def along_gaps(A0, A1, cuts):
    """Solid runs of [A0, A1] left after cutting out the (c0, c1) intervals."""
    return [(p[0], p[1]) for p in solid_pieces(A0, A1, 1.0, [(c0, c1, 0.0, 1.0) for c0, c1 in cuts])]


def steel_grid(mb, axis, p, a0, a1, z0, z1, cols=1, rows=1, frame=0.045,
               bar=0.022, depth=0.05, glass=True, glass_t=0.010):
    """Matte black steel frame with Crittall-style glazing bars and a glass pane."""
    d = depth / 2
    abox(mb, axis, p - d, p + d, a0, a0 + frame, z0, z1, "steel")
    abox(mb, axis, p - d, p + d, a1 - frame, a1, z0, z1, "steel")
    abox(mb, axis, p - d, p + d, a0 + frame, a1 - frame, z1 - frame, z1, "steel")
    abox(mb, axis, p - d, p + d, a0 + frame, a1 - frame, z0, z0 + frame, "steel")
    ia0, ia1, iz0, iz1 = a0 + frame, a1 - frame, z0 + frame, z1 - frame
    bd = d * 0.7
    for i in range(1, cols):
        a = ia0 + (ia1 - ia0) * i / cols
        abox(mb, axis, p - bd, p + bd, a - bar / 2, a + bar / 2, iz0, iz1, "steel")
    for j in range(1, rows):
        z = iz0 + (iz1 - iz0) * j / rows
        abox(mb, axis, p - bd, p + bd, ia0, ia1, z - bar / 2, z + bar / 2, "steel")
    if glass:
        abox(mb, axis, p - glass_t / 2, p + glass_t / 2, ia0, ia1, iz0, iz1, "glass")


# =============================================================================
# 3. MATERIALS
# =============================================================================
MAT = {}


def _inp(node, names, value):
    """Set the first input that exists; Principled names changed in 4.0."""
    for n in (names if isinstance(names, (list, tuple)) else (names,)):
        if n in node.inputs:
            node.inputs[n].default_value = value
            return True
    return False


def _node(nt, kind, loc, **attrs):
    n = nt.nodes.new(kind)
    n.location = loc
    for k, v in attrs.items():
        setattr(n, k, v)
    return n


def _link(nt, a, b):
    nt.links.new(a, b)


def _feed(nt, sock, v):
    if isinstance(v, (int, float, tuple, list)):
        sock.default_value = v
    elif v is not None:
        _link(nt, v, sock)


def _noise(nt, loc, vector, scale, detail=2.0, rough=0.5, distortion=0.0):
    n = _node(nt, "ShaderNodeTexNoise", loc)
    _inp(n, "Scale", scale)
    _inp(n, "Detail", detail)
    _inp(n, "Roughness", rough)
    _inp(n, "Distortion", distortion)
    _link(nt, vector, n.inputs["Vector"])
    return n


def _mapping(nt, loc, vector, scale=(1, 1, 1), rot=(0, 0, 0)):
    m = _node(nt, "ShaderNodeMapping", loc)
    m.inputs["Scale"].default_value = scale
    m.inputs["Rotation"].default_value = rot
    _link(nt, vector, m.inputs["Vector"])
    return m


def _ramp(nt, loc, fac, stops):
    r = _node(nt, "ShaderNodeValToRGB", loc)
    els = r.color_ramp.elements
    els[0].position, els[0].color = stops[0][0], lin(stops[0][1])
    els[1].position, els[1].color = stops[-1][0], lin(stops[-1][1])
    for pos, col in stops[1:-1]:
        els.new(pos).color = lin(col)
    _link(nt, fac, r.inputs["Fac"])
    return r


def _math(nt, loc, op, a, b=None, c=None, clamp=False):
    m = _node(nt, "ShaderNodeMath", loc, operation=op, use_clamp=clamp)
    for i, v in enumerate((a, b, c)):
        _feed(nt, m.inputs[i], v)
    return m


def _maprange(nt, loc, value, f0, f1, t0, t1):
    m = _node(nt, "ShaderNodeMapRange", loc, clamp=True)
    for i, v in enumerate((value, f0, f1, t0, t1)):
        _feed(nt, m.inputs[i], v)
    return m


def _bump(nt, loc, strength, distance, height, normal=None, invert=False):
    b = _node(nt, "ShaderNodeBump", loc, invert=invert)
    _inp(b, "Strength", strength)
    _inp(b, "Distance", distance)
    _link(nt, height, b.inputs["Height"])
    if normal is not None:
        _link(nt, normal, b.inputs["Normal"])
    return b


def _brick(nt, loc, vector, c1, c2, mortar, width, height, mortar_size,
           offset=0.5, bias=0.0):
    b = _node(nt, "ShaderNodeTexBrick", loc, offset=offset, offset_frequency=2)
    b.inputs["Color1"].default_value = lin(c1)
    b.inputs["Color2"].default_value = lin(c2)
    b.inputs["Mortar"].default_value = lin(mortar)
    _inp(b, "Scale", 1.0)
    _inp(b, "Mortar Size", mortar_size)
    _inp(b, "Mortar Smooth", 0.1)
    _inp(b, "Bias", bias)
    _inp(b, "Brick Width", width)
    _inp(b, "Row Height", height)
    _link(nt, vector, b.inputs["Vector"])
    return b


def new_material(key, name, viewport_hex, roughness=0.5):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = lin(viewport_hex)   # solid-view colour for blocking
    mat.roughness = roughness
    nt = mat.node_tree
    nt.nodes.clear()
    out = _node(nt, "ShaderNodeOutputMaterial", (900, 0))
    bsdf = _node(nt, "ShaderNodeBsdfPrincipled", (500, 0))
    _link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    _inp(bsdf, "Roughness", roughness)
    MAT[key] = mat
    return mat, nt, bsdf, out


def set_displacement_method(mat, method):
    try:
        mat.displacement_method = method           # Blender 4.1+
    except (AttributeError, TypeError):
        try:
            mat.cycles.displacement_method = method  # Blender 4.0 and older
        except (AttributeError, TypeError):
            pass


def principled(key, name, hex_col, rough, metallic=0.0, coat=0.0, sheen=0.0):
    mat, nt, bsdf, out = new_material(key, name, hex_col, rough)
    _inp(bsdf, "Base Color", lin(hex_col))
    _inp(bsdf, "Metallic", metallic)
    _inp(bsdf, ["Coat Weight", "Clearcoat"], coat)
    _inp(bsdf, ["Sheen Weight", "Sheen"], sheen)
    return mat, nt, bsdf, out


def mat_plaster():
    """Knauf Rotband, hand-floated.  Three frequencies:
    1. macro: the float-coat undulation, about 1.2 m wavelength and +-2 mm,
       sent to Material Output > Displacement.  Bump-only by default; real
       displacement when HERO_PLASTER is on.
    2. trowel: domain-warped Voronoi, about 0.3 m pads with burnished lap
       ridges where strokes overlap, used as bump.
    3. grain: sub-millimetre gypsum and sand tooth, as a second bump.
    Colour is raw Rotband, a warm pinkish putty with cloudy drying marks."""
    mat, nt, bsdf, out = new_material("plaster", "VRD_Plaster_Rotband", "#D3C5B4", 0.9)
    tc = _node(nt, "ShaderNodeTexCoord", (-1700, 0))
    obj = tc.outputs["Object"]

    macro = _noise(nt, (-1300, 450), obj, 0.8, detail=3.0, rough=0.5)

    warp = _noise(nt, (-1450, -150), obj, 1.5, detail=2.0, rough=0.5)
    warped = _node(nt, "ShaderNodeVectorMath", (-1250, -150), operation="MULTIPLY_ADD")
    _link(nt, warp.outputs["Color"], warped.inputs[0])
    warped.inputs[1].default_value = (0.6, 0.6, 0.6)
    _link(nt, obj, warped.inputs[2])
    stroke_space = _mapping(nt, (-1050, -150), warped.outputs["Vector"], scale=(1.0, 1.0, 1.5))

    edges = _node(nt, "ShaderNodeTexVoronoi", (-850, -50), feature="DISTANCE_TO_EDGE")
    _inp(edges, "Scale", 3.2)
    _link(nt, stroke_space.outputs["Vector"], edges.inputs["Vector"])
    pads = _node(nt, "ShaderNodeTexVoronoi", (-850, -350), feature="SMOOTH_F1")
    _inp(pads, "Scale", 3.2)
    _inp(pads, "Smoothness", 1.0)
    _link(nt, stroke_space.outputs["Vector"], pads.inputs["Vector"])

    ridge = _maprange(nt, (-600, -50), edges.outputs["Distance"], 0.0, 0.035, 1.0, 0.0)
    trowel_h = _math(nt, (-400, -200), "MULTIPLY_ADD", pads.outputs["Distance"], 0.8,
                     _math(nt, (-600, -300), "MULTIPLY", ridge.outputs[0], 0.2).outputs[0])

    grain = _noise(nt, (-600, -550), obj, 600.0, detail=8.0, rough=0.7)
    b1 = _bump(nt, (-150, -250), 0.2, 0.002, trowel_h.outputs[0])
    b2 = _bump(nt, (100, -350), 0.12, 0.0004, grain.outputs["Fac"], normal=b1.outputs["Normal"])
    _link(nt, b2.outputs["Normal"], bsdf.inputs["Normal"])

    tone = _math(nt, (-400, 300), "MULTIPLY_ADD", ridge.outputs[0], 0.05, macro.outputs["Fac"])
    col = _ramp(nt, (-150, 350), tone.outputs[0],
                [(0.35, "#C2B19F"), (0.55, "#D1C3B2"), (0.80, "#DDD2C4")])
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])
    rough = _maprange(nt, (-150, 100), ridge.outputs[0], 0.0, 1.0, 0.92, 0.82)
    _link(nt, rough.outputs[0], bsdf.inputs["Roughness"])
    _inp(bsdf, ["Sheen Weight", "Sheen"], 0.15)     # dusty grazing-angle sheen
    _inp(bsdf, "Sheen Roughness", 0.6)

    disp = _node(nt, "ShaderNodeDisplacement", (500, -350))
    _link(nt, macro.outputs["Fac"], disp.inputs["Height"])
    _inp(disp, "Midlevel", 0.5)
    _inp(disp, "Scale", 0.004)
    _link(nt, disp.outputs["Displacement"], out.inputs["Displacement"])
    set_displacement_method(mat, "BOTH" if HERO_PLASTER else "BUMP")


def mat_oak_floor():
    """Dark-stained, oiled oak boards: 1.6 m x 190 mm, half-bond."""
    mat, nt, bsdf, out = new_material("oak_floor", "VRD_Oak_Floor_DarkStained", "#2A1A10", 0.42)
    tc = _node(nt, "ShaderNodeTexCoord", (-1300, 0))
    planks = _brick(nt, (-900, 250), tc.outputs["Object"], "#2C1B11", "#3D2717", "#0C0805",
                    1.6, 0.19, 0.0015, offset=0.5)
    grain_space = _mapping(nt, (-1000, -150), tc.outputs["Object"], scale=(1.5, 70.0, 70.0))
    grain = _noise(nt, (-800, -150), grain_space.outputs["Vector"], 1.0, detail=6.0, rough=0.6, distortion=0.8)
    shade = _ramp(nt, (-550, -150), grain.outputs["Fac"], [(0.3, "#8A8A8A"), (0.7, "#FFFFFF")])
    tint = _node(nt, "ShaderNodeVectorMath", (-250, 150), operation="MULTIPLY")
    _link(nt, planks.outputs["Color"], tint.inputs[0])
    _link(nt, shade.outputs["Color"], tint.inputs[1])
    _link(nt, tint.outputs["Vector"], bsdf.inputs["Base Color"])
    rough = _maprange(nt, (-250, -150), grain.outputs["Fac"], 0.3, 0.7, 0.36, 0.5)
    _link(nt, rough.outputs[0], bsdf.inputs["Roughness"])
    seam = _bump(nt, (100, -300), 0.4, 0.002, planks.outputs["Fac"], invert=True)
    b2 = _bump(nt, (300, -300), 0.05, 0.0005, grain.outputs["Fac"], normal=seam.outputs["Normal"])
    _link(nt, b2.outputs["Normal"], bsdf.inputs["Normal"])


def mat_oak_joinery():
    """Dark-stained oak for panelling, tables and casings; vertical grain."""
    mat, nt, bsdf, out = new_material("oak", "VRD_Oak_Joinery_DarkStained", "#2B1B11", 0.45)
    tc = _node(nt, "ShaderNodeTexCoord", (-1100, 0))
    space = _mapping(nt, (-900, 0), tc.outputs["Object"], scale=(45.0, 45.0, 1.5))
    grain = _noise(nt, (-700, 0), space.outputs["Vector"], 1.0, detail=6.0, rough=0.6, distortion=0.9)
    col = _ramp(nt, (-450, 150), grain.outputs["Fac"], [(0.3, "#1A100A"), (0.7, "#3B2618")])
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])
    rough = _maprange(nt, (-450, -100), grain.outputs["Fac"], 0.3, 0.7, 0.38, 0.52)
    _link(nt, rough.outputs[0], bsdf.inputs["Roughness"])
    b = _bump(nt, (0, -300), 0.06, 0.0005, grain.outputs["Fac"])
    _link(nt, b.outputs["Normal"], bsdf.inputs["Normal"])


def mat_terracotta():
    """Frisian-style unglazed terracotta plavuizen, 250 x 250 mm, square grid."""
    mat, nt, bsdf, out = new_material("terracotta", "VRD_Terracotta_Frisian", "#9A4B2D", 0.8)
    tc = _node(nt, "ShaderNodeTexCoord", (-1200, 0))
    tiles = _brick(nt, (-850, 250), tc.outputs["Object"], "#A2532F", "#874026", "#76695E",
                   0.25, 0.25, 0.006, offset=0.0)
    mottle = _noise(nt, (-850, -150), tc.outputs["Object"], 6.0, detail=4.0, rough=0.6)
    shade = _ramp(nt, (-600, -150), mottle.outputs["Fac"], [(0.35, "#B8B8B8"), (0.65, "#FFFFFF")])
    tint = _node(nt, "ShaderNodeVectorMath", (-300, 150), operation="MULTIPLY")
    _link(nt, tiles.outputs["Color"], tint.inputs[0])
    _link(nt, shade.outputs["Color"], tint.inputs[1])
    _link(nt, tint.outputs["Vector"], bsdf.inputs["Base Color"])
    rough = _maprange(nt, (-300, -100), tiles.outputs["Fac"], 0.0, 1.0, 0.72, 0.92)
    _link(nt, rough.outputs[0], bsdf.inputs["Roughness"])
    joint = _bump(nt, (100, -300), 0.5, 0.003, tiles.outputs["Fac"], invert=True)
    b2 = _bump(nt, (300, -300), 0.1, 0.0006, mottle.outputs["Fac"], normal=joint.outputs["Normal"])
    _link(nt, b2.outputs["Normal"], bsdf.inputs["Normal"])


def mat_concrete():
    """Polished concrete with soft trowel clouding (wet core, endurance)."""
    mat, nt, bsdf, out = new_material("concrete", "VRD_Concrete_Polished", "#8C8882", 0.3)
    tc = _node(nt, "ShaderNodeTexCoord", (-1000, 0))
    cloud = _noise(nt, (-750, 100), tc.outputs["Object"], 1.2, detail=5.0, rough=0.55)
    col = _ramp(nt, (-450, 200), cloud.outputs["Fac"], [(0.3, "#7A766F"), (0.7, "#9C978F")])
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])
    rough = _maprange(nt, (-450, -50), cloud.outputs["Fac"], 0.3, 0.7, 0.2, 0.38)
    _link(nt, rough.outputs[0], bsdf.inputs["Roughness"])


def mat_glass():
    """Architectural glass.  Shadow rays see a Transparent BSDF, so the sun
    comes through the windows into the room instead of being blocked by
    refraction (caustics are off for interiors)."""
    mat, nt, bsdf, out = new_material("glass", "VRD_Glass_Arch", "#DDE6E2", 0.0)
    _inp(bsdf, "Base Color", lin("#EEF4F1"))
    _inp(bsdf, ["Transmission Weight", "Transmission"], 1.0)
    _inp(bsdf, "IOR", 1.52)
    _inp(bsdf, "Roughness", 0.0)
    lp = _node(nt, "ShaderNodeLightPath", (100, 300))
    clear = _node(nt, "ShaderNodeBsdfTransparent", (300, -200))
    clear.inputs["Color"].default_value = lin("#F4F7F5")
    mix = _node(nt, "ShaderNodeMixShader", (700, 0))
    _link(nt, lp.outputs["Is Shadow Ray"], mix.inputs[0])
    _link(nt, bsdf.outputs["BSDF"], mix.inputs[1])
    _link(nt, clear.outputs["BSDF"], mix.inputs[2])
    _link(nt, mix.outputs["Shader"], out.inputs["Surface"])
    mat.diffuse_color = (0.8, 0.9, 0.9, 0.25)


def mat_books():
    """Book spines on vertical faces facing +/-Y: Brick texture in the XZ plane."""
    mat, nt, bsdf, out = new_material("books", "VRD_Books", "#3A2A22", 0.6)
    tc = _node(nt, "ShaderNodeTexCoord", (-900, 0))
    xz = _mapping(nt, (-700, 0), tc.outputs["Object"], rot=(math.pi / 2, 0, 0))
    spines = _brick(nt, (-450, 0), xz.outputs["Vector"], "#5A2620", "#22362E", "#0B0806",
                    0.035, 0.31, 0.004, offset=0.37, bias=0.0)
    _link(nt, spines.outputs["Color"], bsdf.inputs["Base Color"])


def mat_embers():
    mat, nt, bsdf, out = principled("embers", "VRD_Charcoal_Embers", "#1A0A05", 0.9)
    _inp(bsdf, ["Emission Color", "Emission"], lin("#FF4A12"))
    _inp(bsdf, "Emission Strength", 8.0)


def build_materials():
    mat_plaster()
    mat_oak_floor()
    mat_oak_joinery()
    mat_terracotta()
    mat_concrete()
    mat_glass()
    mat_books()
    mat_embers()
    principled("slab", "VRD_Concrete_Slab", "#6E6A64", 0.9)
    principled("steel", "VRD_Steel_MatteBlack", "#151515", 0.55)
    principled("blue", "VRD_SpaceBlue_Lacquer", SPACE_BLUE, 0.32, coat=0.25)
    principled("bjj", "VRD_BJJ_Tatami", "#2B2D30", 0.65)
    principled("rubber", "VRD_Rubber_Black", "#151515", 0.85)
    principled("trainer", "VRD_Trainer_Plastic", "#2C2C2C", 0.35)
    principled("coir", "VRD_Coir_Mat", "#6E5236", 0.95)
    principled("firebox", "VRD_Firebox_Soot", "#070605", 0.95)
    principled("leather", "VRD_Leather_Oxblood", "#3A1D12", 0.45, coat=0.1)
    principled("rug", "VRD_Wool_Rug", "#4B1F1C", 1.0, sheen=0.5)


# =============================================================================
# 4. PLAN DATA: zones, walls, openings
# =============================================================================
ZONES = [
    # key, label, floor material, finish rect (to wall centre-lines), net rect
    ("Culinary", "CULINARY CORE", "terracotta",
     (0, 0, X_KITCHEN_LNG, Y_SPLIT), (XI0, YI0, X_KITCHEN_LNG - HT, YS0)),
    ("Lounge", "LOUNGE", "oak_floor",
     (X_KITCHEN_LNG, 0, X_LNG_MUD, Y_SPLIT), (X_KITCHEN_LNG + HT, YI0, X_LNG_MUD - HT, YS0)),
    ("Mudroom", "WET-TO-DRY MUDROOM", "terracotta",
     (X_LNG_MUD, 0, PLATE_X, Y_SPLIT), (X_LNG_MUD + HT, YI0, XI1, YS0)),
    ("Library", "LIBRARY / COWORK", "oak_floor",
     (0, Y_SPLIT, X_ENSUITE, PLATE_Y), (XI0, YS1, X_ENSUITE - ES_HALF, YI1)),
    ("Endurance", "ENDURANCE ROOM", "concrete",
     (X_ENSUITE, Y_SPLIT, X_END_WET, PLATE_Y), (X_ENSUITE + ES_HALF, YS1, X_END_WET - HT, YI1)),
    ("WetCore", "WET CORE", "concrete",
     (X_END_WET, Y_SPLIT, PLATE_X, PLATE_Y), (X_END_WET + HT, YS1, XI1, YI1)),
]


def O(at, w, sill, head, kind, **kw):
    """Opening centred at world coordinate `at` along its wall's axis."""
    d = dict(at=at, w=w, sill=sill, head=head, kind=kind)
    d.update(kw)
    return d


# axis "x": wall runs along X at y = c.  axis "y": along Y at x = c.
# outer: -1 / +1 = which side faces outdoors, 0 = internal wall.
WALLS = {
    "S": dict(axis="x", c=EXT_T / 2, t=EXT_T, a0=0.0, a1=PLATE_X, outer=-1, openings=[
        O(3.0, 2.4, 0.0, 3.0, "glazed_door"),           # culinary -> terrace
        O(7.0, 2.4, 0.0, 3.0, "glazed_door"),
        O(12.0, 2.2, 0.45, 3.0, "window"),              # lounge, deep window seats
        O(16.0, 2.2, 0.45, 3.0, "window"),
        O(21.0, 1.8, 0.0, 2.7, "blue_door"),            # main beach entrance
        O(23.4, 1.0, 0.9, 2.7, "window"),
    ]),
    "N": dict(axis="x", c=PLATE_Y - EXT_T / 2, t=EXT_T, a0=0.0, a1=PLATE_X, outer=1, openings=[
        O(2.4, 1.6, 0.9, 2.9, "window"),                # library, north light
        O(6.2, 1.6, 0.9, 2.9, "window"),
        O(10.0, 1.6, 0.9, 2.9, "window"),
        O(15.2, 2.4, 0.7, 3.0, "window"),               # endurance
        O(19.2, 2.4, 0.7, 3.0, "window"),
        O(23.1, 1.2, 1.9, 2.7, "window"),               # wet core clerestory
    ]),
    "W": dict(axis="y", c=EXT_T / 2, t=EXT_T, a0=YI0, a1=YI1, outer=-1, openings=[
        O(7.75, 1.0, 0.0, 2.4, "oak_door"),             # kitchen service door
        O(12.25, 1.6, 0.9, 2.9, "window"),              # library
    ]),
    "E": dict(axis="y", c=PLATE_X - EXT_T / 2, t=EXT_T, a0=YI0, a1=YI1, outer=1, openings=[
        O(4.6, 1.6, 0.9, 2.7, "window"),                # mudroom, boot bench below
        O(12.25, 1.6, 1.9, 2.7, "window"),              # wet core clerestory
    ]),
    "SPLIT": dict(axis="x", c=Y_SPLIT, t=INT_T, a0=XI0, a1=XI1, outer=0, openings=[
        O(10.9, 1.2, 0.0, 2.4, "blue_door"),            # lounge -> library
        O(20.0, 1.2, 0.0, 2.4, "blue_door"),            # mudroom -> endurance
        O(23.1, 0.9, 0.0, 2.2, "oak_door"),             # mudroom -> wet core
    ]),
    "XKL": dict(axis="y", c=X_KITCHEN_LNG, t=INT_T, a0=YI0, a1=YS0, outer=0, openings=[
        O(4.5, 3.6, 0.0, 2.9, "void", lining="oak"),    # cased opening to the culinary core
    ]),
    "XLM": dict(axis="y", c=X_LNG_MUD, t=INT_T, a0=YI0, a1=YS0, outer=0, openings=[
        # the wet-to-dry threshold: steel portal plus a flush steel floor strip
        O(4.6, 2.6, 0.0, 2.75, "void", lining="steel", threshold=True),
    ]),
    "XEW": dict(axis="y", c=X_END_WET, t=INT_T, a0=YS1, a1=YI1, outer=0, openings=[
        O(10.0, 0.9, 0.0, 2.2, "oak_door"),             # wet core -> endurance
    ]),
}


def spans(wall):
    return [(o["at"] - o["w"] / 2, o["at"] + o["w"] / 2, o["sill"], o["head"])
            for o in wall["openings"]]


def frame_plane(wall):
    """Steel windows sit 100 mm in from the outer face, leaving a deep inner reveal."""
    if wall["outer"]:
        return wall["c"] + wall["outer"] * (wall["t"] / 2 - 0.10)
    return wall["c"]


def inner_face(wall):
    return wall["c"] - wall["outer"] * wall["t"] / 2


# =============================================================================
# 5. BUILDERS
# =============================================================================
def build_structure(col):
    mb = MB()
    mb.box(0, 0, -FINISH_T - SLAB_T, PLATE_X, PLATE_Y, -FINISH_T, "slab")
    mb.build("Ground_Slab", col)

    walls = MB()
    for w in WALLS.values():
        for a0, a1, z0, z1 in solid_pieces(w["a0"], w["a1"], H, spans(w)):
            abox(walls, w["axis"], w["c"] - w["t"] / 2, w["c"] + w["t"] / 2, a0, a1, z0, z1, "plaster")
    build_chimney(walls)
    ob = walls.build("Walls_Plaster", col)
    if HERO_PLASTER:
        rm = ob.modifiers.new("Plaster_Remesh", "REMESH")
        rm.mode = "VOXEL"
        rm.voxel_size = HERO_VOXEL
        rm.use_smooth_shade = True

    if BUILD_CEILING:
        c = MB()
        c.box(0, 0, H, PLATE_X, PLATE_Y, H + SLAB_T, "plaster")
        ceiling = c.build("Ceiling_Slab", col)
        ceiling["note"] = "Hidden in the viewport only; it still renders. Exclude it for the plan camera."


CHIMNEY_X = 14.6


def build_chimney(walls):
    """English country-house chimney breast on the lounge's north wall."""
    w, d, fw, fh = 2.0, 0.5, 0.9, 0.85
    y1, y0 = YS0, YS0 - d
    walls.box(CHIMNEY_X - w / 2, y0, 0, CHIMNEY_X - fw / 2, y1, H, "plaster")
    walls.box(CHIMNEY_X + fw / 2, y0, 0, CHIMNEY_X + w / 2, y1, H, "plaster")
    walls.box(CHIMNEY_X - fw / 2, y0, fh, CHIMNEY_X + fw / 2, y1, H, "plaster")


def build_floors(col):
    areas = []
    for key, label, mat, (x0, y0, x1, y1), net in ZONES:
        mb = MB()
        mb.box(x0, y0, -FINISH_T, x1, y1, 0.0, mat)
        ob = mb.build(f"Floor_{key}", col)
        area = (net[2] - net[0]) * (net[3] - net[1])
        ob["net_area_m2"] = round(area, 1)
        areas.append((label, area))
    return areas


def fill_window(mb, w, o):
    ax, p = w["axis"], frame_plane(w)
    a0, a1 = o["at"] - o["w"] / 2, o["at"] + o["w"] / 2
    cols = max(1, round(o["w"] / 0.55))
    rows = max(1, round((o["head"] - o["sill"]) / 0.55))
    steel_grid(mb, ax, p, a0, a1, o["sill"], o["head"], cols, rows)
    if o["sill"] > 0 and w["outer"]:
        room = -w["outer"]
        nose = 0.06 if o["sill"] < 0.6 else 0.03    # low sills become window seats
        q0, q1 = sorted((p + room * 0.03, inner_face(w) + room * nose))
        abox(mb, ax, q0, q1, a0 - 0.03, a1 + 0.03, o["sill"] - 0.045, o["sill"], "oak")


def fill_door(mb, w, o, leaf_mat, lining_mat):
    ax, t, c, p = w["axis"], w["t"], w["c"], frame_plane(w)
    a0, a1, head = o["at"] - o["w"] / 2, o["at"] + o["w"] / 2, o["head"]
    L, gap, lt = 0.015, 0.004, 0.055
    abox(mb, ax, c - t / 2, c + t / 2, a0, a0 + L, 0, head, lining_mat)
    abox(mb, ax, c - t / 2, c + t / 2, a1 - L, a1, 0, head, lining_mat)
    abox(mb, ax, c - t / 2, c + t / 2, a0, a1, head - L, head, lining_mat)
    n = 2 if o["w"] >= 1.6 else 1
    lw = (o["w"] - 2 * L - gap * (n + 1)) / n
    z0, z1 = 0.008, head - L - gap
    zs = z0 + (z1 - z0) * 0.42
    m = 0.11
    for i in range(n):
        la0 = a0 + L + gap + i * (lw + gap)
        la1 = la0 + lw
        abox(mb, ax, p - lt / 2, p + lt / 2, la0, la1, z0, z1, leaf_mat)
        edge = la1 - 0.09 if i == 0 else la0 + 0.09
        for s in (-1, 1):
            # 1930s two-panel leaf: proud fields read as shadow lines in render
            f0, f1 = sorted((p + s * lt / 2, p + s * (lt / 2 + 0.008)))
            abox(mb, ax, f0, f1, la0 + m, la1 - m, z0 + m + 0.1, zs - m / 2, leaf_mat)
            abox(mb, ax, f0, f1, la0 + m, la1 - m, zs + m / 2, z1 - m, leaf_mat)
            b0, b1 = sorted((p + s * (lt / 2 + 0.04), p + s * (lt / 2 + 0.06)))
            abox(mb, ax, b0, b1, edge - 0.012, edge + 0.012, 0.8, 1.5, "steel")


def fill_void(mb, w, o):
    ax, t, c = w["axis"], w["t"], w["c"]
    a0, a1, head = o["at"] - o["w"] / 2, o["at"] + o["w"] / 2, o["head"]
    lining = o.get("lining")
    if lining:
        L = 0.02 if lining == "steel" else 0.03
        abox(mb, ax, c - t / 2 - 0.005, c + t / 2 + 0.005, a0, a0 + L, 0, head, lining)
        abox(mb, ax, c - t / 2 - 0.005, c + t / 2 + 0.005, a1 - L, a1, 0, head, lining)
        abox(mb, ax, c - t / 2 - 0.005, c + t / 2 + 0.005, a0, a1, head - L, head, lining)
    if o.get("threshold"):
        # flush 25 mm matte black steel T-profile on the terracotta/oak seam
        abox(mb, ax, c - 0.0125, c + 0.0125, a0, a1, 0.0, 0.002, "steel")


def build_openings(col):
    mb = MB()
    for w in WALLS.values():
        for o in w["openings"]:
            k = o["kind"]
            if k in ("window", "glazed_door"):
                fill_window(mb, w, o)
            elif k == "blue_door":
                fill_door(mb, w, o, "blue", "steel")
            elif k == "oak_door":
                fill_door(mb, w, o, "oak", "oak")
            elif k == "void":
                fill_void(mb, w, o)
    mb.build("Openings_Steel_Glass_Doors", col)


def build_ensuite(col):
    """1930s Dutch Kamer en suite, re-cut in matte black steel and glass.

    Plan of the 600 mm partition (x across, y along):

      library | vitrine | pocket | vitrine | endurance
              | 200 mm  | 200 mm | 200 mm  |
                         ^      ^
                 skin A track   skin B track, 100 mm acoustic cavity

    Elevation along y: plaster pier | vitrine | 3.2 m opening (2 skins x 2
    pocket leaves) | vitrine | plaster pier, with a steel kalf at 2.75 m,
    double-glazed bovenlicht to 3.30 m and a plaster bulkhead above.
    """
    x0, x1 = X_ENSUITE - ES_HALF, X_ENSUITE + ES_HALF
    pocket = ES_SKIN_GAP + 0.10
    xp0, xp1 = X_ENSUITE - pocket / 2, X_ENSUITE + pocket / 2
    y0, y1 = YS1, YI1
    yc = (y0 + y1) / 2
    o0, o1 = yc - ES_OPENING / 2, yc + ES_OPENING / 2
    c0, c1 = o0 - ES_CABINET, o1 + ES_CABINET
    JAMB, KALF = 0.05, 0.07
    DH, TT = ES_DOOR_HEAD, ES_TRANSOM_TOP

    mb = MB()
    mb.box(x0, y0, 0, x1, c0, H, "plaster")              # piers
    mb.box(x0, c1, 0, x1, y1, H, "plaster")
    mb.box(x0, c0, TT, x1, c1, H, "plaster")             # bulkhead
    mb.box(x0, o0 - JAMB, 0, x1, o0, DH, "steel")        # steel portal jambs
    mb.box(x0, o1, 0, x1, o1 + JAMB, DH, "steel")
    mb.box(x0, c0, DH, x1, c1, DH + KALF, "steel")       # the kalf
    mb.box(x0, o0, 0, x1, o1, 0.004, "steel")            # threshold plate
    n_transom = max(1, round((c1 - c0) / 0.36))
    for px in (x0 + 0.03, x1 - 0.03):                    # double-glazed bovenlicht
        steel_grid(mb, "y", px, c0, c1, DH + KALF, TT, cols=n_transom, rows=1, frame=0.04, depth=0.04)

    for ya, yb in ((c0, o0 - JAMB), (o1 + JAMB, c1)):
        # (outer face, pocket face, glazing plane, shelf front, shelf back) per room
        for fo, fp, glaze, sf, sb in ((x0, xp0, x0 + 0.025, x0 + 0.05, xp0 - 0.018),
                                      (x1, xp1, x1 - 0.025, x1 - 0.05, xp1 + 0.018)):
            mb.box(fo, ya, 0, fp, yb, 0.85, "oak")                    # drawer base
            mb.box(sb, ya, 0.85, fp, yb, DH, "oak")                   # pocket wall
            mb.box(fo, ya, 0.85, fp, ya + 0.02, DH, "oak")            # cabinet ends
            mb.box(fo, yb - 0.02, 0.85, fp, yb, DH, "oak")
            for z in (1.35, 1.85, 2.3):
                mb.box(sf, ya + 0.02, z - 0.012, sb, yb - 0.02, z + 0.012, "oak")
            steel_grid(mb, "y", glaze, ya, yb, 0.85, DH, cols=2, rows=4, frame=0.04, depth=0.04)
    mb.build("EnSuite_Frame", col)

    # Controller: custom property "open" drives all four leaves
    ctrl = bpy.data.objects.new("EnSuite_CONTROL", None)
    ctrl.empty_display_type = "SINGLE_ARROW"
    ctrl.empty_display_size = 0.6
    ctrl.location = (X_ENSUITE, yc, H + 0.6)
    ctrl["open"] = float(ES_OPEN)
    try:
        ctrl.id_properties_ui("open").update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0,
                                             description="0 = sealed, 1 = leaves pocketed")
    except (AttributeError, TypeError):
        pass
    col.objects.link(ctrl)

    lap = 0.03
    lw = ES_OPENING / 2 + lap
    travel = ES_OPENING / 2
    lt = 0.04
    for skin, px in (("Library", X_ENSUITE - ES_SKIN_GAP / 2), ("Endurance", X_ENSUITE + ES_SKIN_GAP / 2)):
        for side, sign in (("S", -1), ("N", 1)):
            leaf = MB()
            ha = lw / 2 - 0.0015
            steel_grid(leaf, "y", 0.0, -ha, ha, 0.006, DH - 0.004, cols=ES_LEAF_GRID[0],
                       rows=ES_LEAF_GRID[1], frame=0.05, bar=0.022, depth=lt, glass_t=0.016)
            leaf.box(-lt / 2, -ha, 0.006, lt / 2, ha, 0.15, "steel")   # kick rail
            # flush pull on the meeting stile, both faces
            ey = -sign * (ha - 0.06)
            for s in (-1, 1):
                leaf.box(s * lt / 2, ey - 0.01, 0.9, s * (lt / 2 + 0.012), ey + 0.01, 1.4, "steel")
            cy = yc + sign * lw / 2      # closed: laps 30 mm into the jamb
            ob = leaf.build(f"EnSuite_Leaf_{skin}_{side}", col, location=(px, cy, 0.0))
            fc = ob.driver_add("location", 1)
            drv = fc.driver
            drv.type = "SCRIPTED"
            var = drv.variables.new()
            var.name = "k"
            var.type = "SINGLE_PROP"
            var.targets[0].id_type = "OBJECT"
            var.targets[0].id = ctrl
            var.targets[0].data_path = '["open"]'
            drv.expression = f"{cy:.4f} {'+' if sign > 0 else '-'} k*{travel:.4f}"


PANEL_T = 0.025


def panel_run(mb, axis, face, inward, A0, A1, height, wall_key, stiles=0.6, mid_rail=None):
    """Oak panelling with skirting, optional mid rail, cap rail and stiles,
    cut around the host wall's openings."""
    host = spans(WALLS[wall_key])
    p0, p1 = sorted((face, face + inward * PANEL_T))
    for a0, a1, z0, z1 in solid_pieces(A0, A1, height, host):
        abox(mb, axis, p0, p1, a0, a1, z0, z1, "oak")

    def rail(z0, z1, proud):
        r0, r1 = sorted((face, face + inward * (PANEL_T + proud)))
        cuts = [(a, b) for a, b, s, h in host if s < z1 and h > z0]
        for a, b in along_gaps(A0, A1, cuts):
            abox(mb, axis, r0, r1, a, b, z0, z1, "oak")

    rail(0.0, 0.18, 0.015)                        # skirting
    rail(height - 0.07, height, 0.035)            # cap rail
    if mid_rail:
        rail(mid_rail - 0.03, mid_rail + 0.03, 0.018)
    s0, s1 = sorted((face, face + inward * (PANEL_T + 0.012)))
    a = A0 + stiles
    while a < A1 - 0.1:
        if not any(o0 - 0.05 < a < o1 + 0.05 for o0, o1, s, h in host if s < height):
            abox(mb, axis, s0, s1, a - 0.035, a + 0.035, 0.18, height - 0.07, "oak")
        a += stiles


def build_joinery(col):
    lib = MB()
    xe = X_ENSUITE - ES_HALF
    panel_run(lib, "x", YI1, -1, XI0, xe, LIBRARY_PANEL_H, "N", mid_rail=0.95)
    panel_run(lib, "y", XI0, 1, YS1, YI1, LIBRARY_PANEL_H, "W", mid_rail=0.95)
    panel_run(lib, "x", YS1, 1, XI0, xe, LIBRARY_PANEL_H, "SPLIT", mid_rail=0.95)
    lib.build("Panelling_Library_Oak", col)

    lng = MB()
    lx0, lx1 = X_KITCHEN_LNG + HT, X_LNG_MUD - HT
    panel_run(lng, "x", YI0, 1, lx0, lx1, LOUNGE_DADO_H, "S", stiles=0.5)
    panel_run(lng, "x", YS0, -1, lx0, lx1, LOUNGE_DADO_H, "SPLIT", stiles=0.5)
    panel_run(lng, "y", lx0, 1, YI0, YS0, LOUNGE_DADO_H, "XKL", stiles=0.5)
    panel_run(lng, "y", lx1, -1, YI0, YS0, LOUNGE_DADO_H, "XLM", stiles=0.5)
    lng.build("Panelling_Lounge_Dado_Oak", col)


def build_props(col):
    rnd = random.Random(1930)

    # --- Culinary core: back kitchen, charcoal-grill hearth, communal table
    k = MB()
    k.box(XI0, 1.0, 0, XI0 + 0.65, 7.0, 0.88, "oak")
    k.box(XI0, 1.0, 0.88, XI0 + 0.68, 7.0, 0.92, "concrete")
    for z in (1.55, 2.0):
        k.box(XI0, 1.4, z, XI0 + 0.32, 6.6, z + 0.04, "oak")
    ix0, ix1, iy0, iy1 = 2.2, 3.4, 3.0, 6.6
    wx0, wx1, wy0, wy1 = 2.45, 3.15, 4.0, 5.6
    k.box(ix0, iy0, 0, ix1, iy1, 0.86, "terracotta")                     # masonry hearth
    k.box(ix0 - 0.05, iy0 - 0.05, 0.86, ix1 + 0.05, wy0, 0.92, "concrete")
    k.box(ix0 - 0.05, wy1, 0.86, ix1 + 0.05, iy1 + 0.05, 0.92, "concrete")
    k.box(ix0 - 0.05, wy0, 0.86, wx0, wy1, 0.92, "concrete")
    k.box(wx1, wy0, 0.86, ix1 + 0.05, wy1, 0.92, "concrete")
    k.box(wx0, wy0, 0.70, wx1, wy1, 0.86, "steel")                       # charcoal well
    k.box(wx0 + 0.03, wy0 + 0.03, 0.86, wx1 - 0.03, wy1 - 0.03, 0.875, "embers")
    for i in range(12):
        y = wy0 + 0.06 + i * (wy1 - wy0 - 0.12) / 11
        k.box(wx0, y - 0.006, 0.90, wx1, y + 0.006, 0.912, "steel")       # grate
    k.box(2.0, 3.7, 2.3, 3.6, 5.9, H, "plaster")                         # plastered hood
    k.box(1.98, 3.68, 2.3, 3.62, 5.92, 2.37, "steel")
    tx0, tx1, ty0, ty1 = 6.0, 7.2, 1.8, 7.2                              # 5.4 x 1.2 m
    k.box(tx0, ty0, 0.68, tx1, ty1, 0.78, "oak")                         # 100 mm slab top
    for y in (2.4, 4.5, 6.6):
        k.box(tx0 + 0.15, y - 0.06, 0, tx1 - 0.15, y + 0.06, 0.68, "oak")  # trestles
    k.box(tx0 + 0.15, ty0 + 0.5, 0.12, tx1 - 0.15, ty1 - 0.5, 0.18, "oak")  # stretcher
    k.box(5.35, 2.0, 0.42, 5.7, 7.0, 0.47, "oak")                        # benches
    k.box(7.5, 2.0, 0.42, 7.85, 7.0, 0.47, "oak")
    for bx in (5.4, 7.55):
        for y in (2.3, 4.5, 6.7):
            k.box(bx, y - 0.05, 0, bx + 0.25, y + 0.05, 0.42, "oak")
    k.build("Props_Culinary", col)

    # --- Lounge: hearth, mantel, chesterfields, rug
    lg = MB()
    fw, d = 0.9, 0.5
    lg.box(CHIMNEY_X - fw / 2, YS0 - 0.12, 0, CHIMNEY_X + fw / 2, YS0, 0.85, "firebox")
    lg.box(CHIMNEY_X - 1.1, YS0 - d - 0.45, 0, CHIMNEY_X + 1.1, YS0 - d, 0.03, "terracotta")
    lg.box(CHIMNEY_X - fw / 2, YS0 - d, 0, CHIMNEY_X + fw / 2, YS0 - 0.12, 0.03, "terracotta")
    lg.box(CHIMNEY_X - 1.1, YS0 - d - 0.1, 1.28, CHIMNEY_X + 1.1, YS0, 1.36, "oak")
    lg.box(CHIMNEY_X - 0.25, YS0 - 0.35, 0.03, CHIMNEY_X + 0.25, YS0 - 0.2, 0.12, "embers")
    lg.box(12.6, 4.2, 0, 16.6, 7.6, 0.008, "rug")
    for sx0, sx1, back in ((12.9, 13.8, "W"), (15.4, 16.3, "E")):
        lg.box(sx0, 4.7, 0, sx1, 7.1, 0.42, "leather")
        bx0, bx1 = (sx0, sx0 + 0.22) if back == "W" else (sx1 - 0.22, sx1)
        lg.box(bx0, 4.7, 0.42, bx1, 7.1, 0.78, "leather")
        lg.box(sx0, 4.7, 0.42, sx1, 4.92, 0.78, "leather")              # rolled arms
        lg.box(sx0, 6.88, 0.42, sx1, 7.1, 0.78, "leather")
    lg.box(14.05, 5.3, 0, 15.15, 6.5, 0.42, "oak")
    lg.build("Props_Lounge", col)

    # --- Mudroom: recessed coir mat, linear drain, boot bench, wetsuit rail
    md = MB()
    md.box(20.0, YI0, 0, 22.0, 1.55, 0.001, "coir")
    md.box(20.0, 1.6, 0, 22.0, 1.7, 0.002, "steel")
    md.box(XI1 - 0.5, 1.8, 0.40, XI1, 7.2, 0.46, "oak")
    for y in (2.0, 4.5, 7.0):
        md.box(XI1 - 0.45, y - 0.04, 0, XI1 - 0.05, y + 0.04, 0.40, "steel")
    md.box(20.8, YS0 - 0.1, 1.75, 22.5, YS0 - 0.07, 1.78, "steel")
    for x in (20.8, 22.47):
        md.box(x, YS0 - 0.1, 1.75, x + 0.03, YS0, 1.78, "steel")
    md.build("Props_Mudroom", col)

    # --- Library: full-wall bookcase, refectory cowork table, reading chairs
    lb = MB()
    bx0, bx1, by0, bd = 0.6, 9.6, YS1 + PANEL_T, 0.36
    lb.box(bx0, by0, 0, bx1, by0 + 0.02, LIBRARY_PANEL_H, "oak")
    lb.box(bx0, by0, 0, bx1, by0 + bd, 0.1, "oak")
    bays = int(round((bx1 - bx0) / 0.9))
    for i in range(bays + 1):
        x = bx0 + i * (bx1 - bx0) / bays
        lb.box(x - 0.012, by0, 0, x + 0.012, by0 + bd, LIBRARY_PANEL_H, "oak")
    shelves = [0.1 + j * 0.38 for j in range(7)]
    for z in shelves:
        lb.box(bx0, by0, z - 0.02, bx1, by0 + bd, z, "oak")
    for i in range(bays):
        xa = bx0 + i * (bx1 - bx0) / bays + 0.02
        for z in shelves[:-1]:
            fill = rnd.uniform(0.55, 0.86)
            lb.box(xa, by0 + 0.04, z, xa + fill, by0 + 0.30, z + rnd.uniform(0.22, 0.31), "books")
    lb.box(4.4, 11.7, 0.72, 9.2, 12.8, 0.78, "oak")
    for x in (4.9, 8.7):
        lb.box(x - 0.06, 11.85, 0, x + 0.06, 12.65, 0.72, "oak")
    for y in (10.2, 14.3):
        lb.box(10.4, y - 0.4, 0, 11.2, y + 0.4, 0.42, "leather")
        lb.box(10.4, y - 0.4, 0.42, 10.6, y + 0.4, 0.95, "leather")
    lb.build("Props_Library", col)

    # --- Endurance: four smart-trainer bays behind the glass, ~29 m2 BJJ mat
    en = MB()
    for y in (10.2, 11.5, 12.8, 14.1):
        en.box(13.1, y - 0.45, 0, 15.1, y + 0.45, 0.006, "rubber")
        en.box(13.35, y - 0.24, 0.006, 13.95, y + 0.24, 0.42, "trainer")   # direct-drive unit
        en.box(13.55, y - 0.03, 0.30, 14.85, y + 0.03, 0.36, "steel")      # frame (simplified)
        en.box(13.6, y - 0.03, 0.36, 13.66, y + 0.03, 0.95, "steel")
        en.box(13.5, y - 0.07, 0.95, 13.78, y + 0.07, 1.0, "rubber")
        en.box(14.75, y - 0.03, 0.36, 14.81, y + 0.03, 1.02, "steel")
        en.box(14.72, y - 0.22, 1.0, 14.84, y + 0.22, 1.04, "rubber")
        en.box(14.65, y - 0.12, 0.006, 14.95, y + 0.12, 0.10, "trainer")
    en.box(15.4, 9.65, 0, 20.8, 15.05, 0.04, "bjj")
    en.build("Props_Endurance", col)

    # --- Wet core: shower cubicle fins and a changing bench
    wc = MB()
    for y in (12.4, 13.5, 14.6):
        wc.box(XI1 - 1.05, y - 0.04, 0, XI1, y + 0.04, 1.85, "concrete")
    wc.box(X_END_WET + HT, 11.0, 0.40, X_END_WET + HT + 0.4, 15.2, 0.46, "oak")
    wc.build("Props_WetCore", col)


def build_labels(col, areas):
    for (key, label, _m, _f, net), (_l, area) in zip(ZONES, areas):
        cu = bpy.data.curves.new(f"Label_{key}", "FONT")
        cu.body = f"{label}\n{area:.1f} m2"
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        cu.size = 0.42
        ob = bpy.data.objects.new(f"Label_{key}", cu)
        ob.location = ((net[0] + net[2]) / 2, (net[1] + net[3]) / 2 - 1.2, 0.05)
        ob.hide_render = True
        col.objects.link(ob)


# =============================================================================
# 6. LIGHT, WORLD, CAMERAS, RENDER
# =============================================================================
def aim(ob, direction):
    ob.rotation_euler = Vector(direction).to_track_quat("-Z", "Y").to_euler()


def build_world():
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = _node(nt, "ShaderNodeOutputWorld", (400, 0))
    bg = _node(nt, "ShaderNodeBackground", (150, 0))
    _link(nt, bg.outputs["Background"], out.inputs["Surface"])
    if HDRI_PATH and os.path.exists(HDRI_PATH):
        tc = _node(nt, "ShaderNodeTexCoord", (-600, 0))
        mp = _mapping(nt, (-400, 0), tc.outputs["Generated"], rot=(0, 0, math.radians(HDRI_ROTATION_DEG)))
        env = _node(nt, "ShaderNodeTexEnvironment", (-150, 0))
        env.image = bpy.data.images.load(HDRI_PATH, check_existing=True)
        _link(nt, mp.outputs["Vector"], env.inputs["Vector"])
        _link(nt, env.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = HDRI_STRENGTH
        return "HDRI"
    try:
        sky = _node(nt, "ShaderNodeTexSky", (-150, 0))
        sky.sky_type = "NISHITA"
        sky.sun_disc = False             # the Sun lamp carries the direct light
        sky.sun_elevation = math.radians(SUN_ELEVATION_DEG)
        sky.sun_rotation = math.radians(SUN_AZIMUTH_DEG)
        sky.dust_density = 2.5           # salt haze off the water
        _link(nt, sky.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 0.25
        return "Nishita sky (procedural fallback)"
    except (TypeError, AttributeError):
        for n in list(nt.nodes):
            if n.bl_idname == "ShaderNodeTexSky":
                nt.nodes.remove(n)
        bg.inputs["Color"].default_value = (0.55, 0.65, 0.8, 1.0)
        bg.inputs["Strength"].default_value = 0.6
        return "flat sky colour (fallback)"


def build_lighting(col):
    az, el = math.radians(SUN_AZIMUTH_DEG), math.radians(SUN_ELEVATION_DEG)
    to_sun = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    sun_data = bpy.data.lights.new("Sun_Coastal", "SUN")
    sun_data.energy = SUN_STRENGTH
    sun_data.angle = math.radians(0.6)         # crisp but not CG-sharp
    sun_data.color = (1.0, 0.86, 0.72)         # late-afternoon warmth
    sun = bpy.data.objects.new("Sun_Coastal", sun_data)
    sun.location = Vector((PLATE_X / 2, PLATE_Y / 2, 0.0)) + to_sun * 30
    aim(sun, -to_sun)
    col.objects.link(sun)

    # Cycles light portals in every exterior glazed opening
    for key in ("S", "N", "W", "E"):
        w = WALLS[key]
        for i, o in enumerate(w["openings"]):
            if o["kind"] not in ("window", "glazed_door"):
                continue
            room = -w["outer"]
            across = inner_face(w) + room * 0.01
            zc = (o["sill"] + o["head"]) / 2
            loc = (o["at"], across, zc) if w["axis"] == "x" else (across, o["at"], zc)
            ld = bpy.data.lights.new(f"Portal_{key}{i}", "AREA")
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = o["w"], o["head"] - o["sill"]
            try:
                ld.cycles.is_portal = True
            except AttributeError:
                ld.energy = 0.0
            ob = bpy.data.objects.new(f"Portal_{key}{i}", ld)
            ob.location = loc
            aim(ob, (0, room, 0) if w["axis"] == "x" else (room, 0, 0))
            col.objects.link(ob)
    return sun


def build_practicals(col):
    warm, ember, cool = (1.0, 0.62, 0.34), (1.0, 0.42, 0.14), (1.0, 0.9, 0.8)

    def point(name, loc, watts, rgb, radius=0.04):
        ld = bpy.data.lights.new(name, "POINT")
        ld.energy, ld.color = watts, rgb
        ld.shadow_soft_size = radius
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        col.objects.link(ob)

    shades = MB()
    for i, y in enumerate((2.8, 4.5, 6.2)):                    # pendants over the table
        point(f"Pendant_Table_{i}", (6.6, y, 1.98), 45, warm)
        shades.box(6.42, y - 0.18, 2.03, 6.78, y + 0.18, 2.22, "steel")
        shades.box(6.59, y - 0.01, 2.22, 6.61, y + 0.01, H, "steel")
    shades.build("Pendant_Shades", col)
    point("Lamp_Library_A", (5.8, 12.25, 1.15), 12, warm)
    point("Lamp_Library_B", (7.8, 12.25, 1.15), 12, warm)
    point("Fire_Lounge", (CHIMNEY_X, YS0 - 0.25, 0.25), 60, ember, 0.15)
    point("Embers_Grill", (2.8, 4.8, 1.0), 30, ember, 0.2)
    for i, y in enumerate((11.0, 13.5)):                        # cooler, brighter gym
        ld = bpy.data.lights.new(f"Linear_Endurance_{i}", "AREA")
        ld.shape, ld.size, ld.size_y = "RECTANGLE", 6.0, 0.15
        ld.energy, ld.color = 180, cool
        ob = bpy.data.objects.new(f"Linear_Endurance_{i}", ld)
        ob.location = (17.0, y, H - 0.05)
        col.objects.link(ob)


CAMERAS = [
    # name, location, target, lens
    ("CAM_01_Library_EnSuite", (0.9, 12.25, 1.40), (20.0, 12.25, 1.40), 24),
    ("CAM_02_Mudroom_Threshold", (23.6, 3.2, 1.50), (12.0, 5.2, 1.40), 21),
    ("CAM_03_Culinary_Hearth", (8.9, 0.9, 1.65), (2.8, 5.2, 1.10), 24),
    ("CAM_04_Endurance_to_Library", (20.5, 12.25, 1.45), (2.0, 12.25, 1.30), 24),
]


def build_cameras(col):
    first = None
    for name, loc, target, lens in CAMERAS:
        cam = bpy.data.cameras.new(name)
        cam.lens, cam.sensor_width, cam.clip_end = lens, 36, 200
        ob = bpy.data.objects.new(name, cam)
        ob.location = loc
        aim(ob, Vector(target) - Vector(loc))   # level target = two-point perspective
        col.objects.link(ob)
        first = first or ob
    plan = bpy.data.cameras.new("CAM_00_Plan_Ortho")
    plan.type, plan.ortho_scale, plan.clip_end = "ORTHO", 27.0, 200
    ob = bpy.data.objects.new("CAM_00_Plan_Ortho", plan)
    ob.location = (PLATE_X / 2, PLATE_Y / 2, 30.0)
    col.objects.link(ob)
    bpy.context.scene.camera = first


def setup_render():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = 512
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.01
    cy.use_denoising = True
    cy.max_bounces = 16
    cy.diffuse_bounces = 6          # dark oak rooms live on bounce light
    cy.glossy_bounces = 4
    cy.transmission_bounces = 12    # several stacked glass skins in the en suite
    cy.transparent_max_bounces = 16
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    cy.sample_clamp_indirect = 10.0
    sc.render.resolution_x, sc.render.resolution_y = 3000, 2000
    sc.render.resolution_percentage = 50
    vs = sc.view_settings
    for vt in ("AgX", "Filmic"):
        try:
            vs.view_transform = vt
            break
        except TypeError:
            continue
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            vs.look = look
            break
        except TypeError:
            continue
    vs.exposure = EXPOSURE


# =============================================================================
# 7. SCENE MANAGEMENT AND MAIN
# =============================================================================
DATA_TYPES = ((bpy.types.Mesh, "meshes"), (bpy.types.Camera, "cameras"),
              (bpy.types.Light, "lights"), (bpy.types.Curve, "curves"))


def remove_object(ob):
    data = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if data is not None and data.users == 0:
        for t, attr in DATA_TYPES:
            if isinstance(data, t):
                getattr(bpy.data, attr).remove(data)
                break


def wipe_collection(col):
    for child in list(col.children):
        wipe_collection(child)
        bpy.data.collections.remove(child)
    for ob in list(col.objects):
        remove_object(ob)


def main():
    scene = bpy.context.scene
    if REMOVE_DEFAULT_OBJECTS:
        for name in ("Cube", "Light", "Camera"):
            ob = bpy.data.objects.get(name)
            if ob is not None:
                remove_object(ob)
    root_col = bpy.data.collections.get("VERDIO")
    if root_col is None:
        root_col = bpy.data.collections.new("VERDIO")
        scene.collection.children.link(root_col)
    else:
        wipe_collection(root_col)

    def sub(name):
        c = bpy.data.collections.new(name)
        root_col.children.link(c)
        return c

    cols = {k: sub(f"VRD_{k}") for k in (
        "01_Structure", "02_Floors", "03_EnSuite", "04_Openings", "05_Joinery",
        "06_Props", "07_Lighting", "08_Cameras", "09_Labels")}

    build_materials()
    build_structure(cols["01_Structure"])
    areas = build_floors(cols["02_Floors"])
    build_ensuite(cols["03_EnSuite"])
    build_openings(cols["04_Openings"])
    build_joinery(cols["05_Joinery"])
    if BUILD_PROPS:
        build_props(cols["06_Props"])
    sky = build_world()
    sun = build_lighting(cols["07_Lighting"])
    if BUILD_PRACTICALS:
        build_practicals(cols["07_Lighting"])
    build_cameras(cols["08_Cameras"])
    build_labels(cols["09_Labels"], areas)
    setup_render()

    # Parent the building (not the sun) to one root so SITE_ROTATION_DEG
    # turns the plan against the sky.
    root = bpy.data.objects.new("VERDIO_ROOT", None)
    root.empty_display_type = "PLAIN_AXES"
    root_col.objects.link(root)
    for ob in root_col.all_objects:
        if ob not in (root, sun) and ob.parent is None:
            ob.parent = root
    root.rotation_euler[2] = math.radians(SITE_ROTATION_DEG)

    ceiling = bpy.data.objects.get("Ceiling_Slab")
    if ceiling is not None:
        try:
            ceiling.hide_set(True)      # viewport only; it still renders
        except RuntimeError:
            pass

    total = sum(a for _, a in areas)
    print("\nVERDIO ground floor - net areas")
    for label, a in areas:
        print(f"  {label:<22} {a:6.1f} m2")
    print(f"  {'net total':<22} {total:6.1f} m2   (gross plate {PLATE_X * PLATE_Y:.0f} m2)")
    print(f"  world: {sky}\n")


if __name__ == "__main__":
    main()
