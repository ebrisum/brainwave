"""
VERDIO - Ground Floor - parametric conceptual massing
=====================================================
Boutique high-performance coastal poshtel.  Blender 4.2 LTS or newer.

Run it:  Scripting workspace -> Open this file -> Run Script
         or headless:  blender -b -P verdio_ground_floor.py
Re-running rebuilds the "VERDIO" collection in place.  Materials are rebuilt
under the same names, so nothing piles up as .001 copies.

Direction: a dune house, not a modern box.  A Dutch coastal farmhouse
(brick, pantiles, an oak beam ceiling) crossed with an English country
house (panelling, hearths, window seats), set into the dunes, with a deep
veranda where most of daily life happens half outdoors.  No polished
concrete, no flat white ceilings, no LED strips, no powder-coated steel.

Plan convention: +X = east, +Y = north, Z up, 1 unit = 1 m.
The coast / sea is SOUTH (-Y).  Plate 25.0 x 16.0 m = 400 m2 gross.

                    TRAINING YARD (sand, pull-up rig)
                          ^ doors ^
    N  y=16.00
    +-------------------------------------------------+
    |  LIBRARY / COWORK      #  ENDURANCE      | WET  |
    |  dark oak, panelled    #  KICKR + BJJ    | CORE |
    |  80.6 m2               #  58.5 m2        |20.7  |
    +------------------+-----#-----------+-----+------+  y=8.75
    |  CULINARY CORE   |  LOUNGE         | MUDROOM    |
    |  grill + table   |  dark oak       | terracotta |
    |  75.1 m2         |  73.0 m2        | 50.2 m2    |
    +==||====||========+==||===||===||===+===||=======+  y=0   || = French doors
    :  VERANDA 3.6 m: terracotta runs straight through     :
    :  oven, long table  |  daybeds          |  porch, shower:  y=-3.6
    :  vine pergola      |  pantile lean-to roof             :
    x=0               9.5   12.5        18.5  21.5   25
                                            | boardwalk
                  ~~~~~~  foredune, beach, sea  ~~~~~~
    #  = Kamer en suite partition (x = 12.5)

Indoor/outdoor moves:
  * The culinary terracotta runs out onto the veranda at the same level.
  * The ceiling joists and the veranda rafters share one 0.75 m grid, so
    the ceiling appears to carry on outside.
  * The French doors on the coast side and the endurance room's yard doors
    fold fully open; the window shutters fold back against the brick.
  * Every room looks onto dune, grass or sea; the library has low sills and
    window seats.
  * Nature comes indoors: potted olive and fig trees, natural materials.

Garden (a temperate take on a hillside resort like Shanti, north Bali):
  the house terrace sits 4.6 m above the sea.  In front of the veranda a
  natural swimming pond overflows to the view; below it, terraces step down
  (wildflower meadow, then tulip strips like the bulb fields behind the
  Dutch dunes) to a boardwalk and the beach.  Four reed-thatched garden
  pavilions sit in dense planting on the dunes either side, each with an
  open-air living veranda, and boardwalks link them to the house.

Realism: with api.polyhaven.com and dl.polyhaven.org reachable, CC0 scanned
textures, plants and an HDRI sky replace the procedural stand-ins (cached
under PH_CACHE).  QUALITY = "final" renders at full resolution and samples.

Two custom-property controllers:
  EnSuite_CONTROL["open"]  0-1 slides the four en suite leaves into their pockets.
  FACADE_CONTROL["open"]   0-1 swings every French door and shutter.
"""

import math
import os
import random

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils import noise as mnoise

# =============================================================================
# 1. PARAMETERS.  Change these and re-run; the model rebuilds from them.
# =============================================================================
PLATE_X, PLATE_Y = 25.0, 16.0   # 400 m2 gross
EXT_T = 0.35                    # exterior wall: solid masonry, Rotband inside
INT_T = 0.20                    # internal masonry partitions
H = 3.60                        # floor to ceiling
SLAB_T = 0.25
FINISH_T = 0.03                 # floor finish build-up
SKIN_T = 0.03                   # brick slip on the exterior faces

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
ES_DOOR_HEAD = 2.75     # underside of the "kalf" (transom rail)
ES_TRANSOM_TOP = 3.30   # top of the "bovenlicht" glazing; plaster bulkhead above
ES_SKIN_GAP = 0.10      # acoustic cavity between the two glass skins
ES_OPEN = 0.0           # 0 = closed (acoustic and climate seal), 1 = pocketed
ES_LEAF_GRID = (2, 5)   # divided lights per leaf (cols, rows)
ENSUITE_FRAME = "iron"  # "iron" = hand-forged blackened iron, "oak" = dark oak

LIBRARY_PANEL_H = 2.40  # full-height oak panelling, to picture-rail height
LOUNGE_DADO_H = 1.10    # country-house dado panelling

# Timber ceiling, carried outside as the veranda rafters
JOIST_PITCH = 0.75
GIRDER_Y = 4.0          # main oak girder across the coast band

# Veranda (outside the 400 m2 plate)
VERANDA_DEPTH = 3.6
VERANDA_EAVE = 2.85     # underside of the oak plate beam on the posts
VERANDA_SEAT = 4.10     # where the rafters bear on the facade
VERANDA_POSTS = (0.2, 5.0, 9.5, 12.75, 15.25, 18.5, 22.4, 24.8)  # on the facade piers
PERGOLA_TO_X = 9.5      # open vine pergola over the outdoor kitchen up to here, tiles beyond
FACADE_OPEN = 1.0       # 0 = French doors and shutters shut, 1 = folded open

# Upper floors (placeholder massing for the exterior silhouette)
BUILD_UPPER = True
UPPER_FLOORS = 1
UPPER_H = 3.0
ROOF_PITCH_DEG = 45.0   # steep Dutch pantile roof

# Landscape
BUILD_LANDSCAPE = True
LANDSCAPE_SEED = 7
GRASS_COUNT = 9000      # marram tussocks (x 30 blades each at render time)
SEA_LEVEL = -4.6        # the house terrace sits 4.6 m above the sea: a panorama
BOARDWALK_X = 21.0      # the path from the mudroom porch down to the beach

# Garden, laid out like a hillside resort on a temperate coast
TERRACE_X = (-8.0, 33.0)                          # formal terraces between these x
TERRACE_STEPS = ((-10.0, -1.2), (-16.0, -2.35))   # (retaining wall y, level south of it)
TERRACE_END = -22.0                               # last wall; dune slope to the beach below
TERRACE_FOOT = -3.5                               # ground at the foot of the last wall
POND = (2.0, -10.0, 16.0, -6.2)                   # natural swimming pond, overflowing to the view
REED_BED = (16.0, -10.0, 20.0, -6.2)              # planted regeneration zone that cleans it
PAVILIONS = ((-13.0, 2.5, 0.0), (-14.5, 15.0, 10.0), (38.5, 2.0, 0.0), (40.0, 14.5, -10.0))  # (x, y, rot)
BULB_COLOURS = ("#B5172B", "#F0B83C", "#EDE6D8", "#7E3A86")  # tulip strips on the lowest terrace

# Site and light
SITE_ROTATION_DEG = 0.0     # rotate the building against the sun (-90: coast faces west)
SUN_AZIMUTH_DEG = 235.0     # compass bearing of the sun: 0 N, 90 E, 180 S (coast), 270 W
SUN_ELEVATION_DEG = 16.0    # low, late-afternoon raking light
SUN_STRENGTH = 4.5
EXPOSURE = 1.5              # interiors sit about +1.5 EV over the exterior
HDRI_PATH = ""              # absolute path to an .exr/.hdr; empty = procedural sky
HDRI_STRENGTH = 1.0
HDRI_ROTATION_DEG = 0.0

BUILD_PROPS = True
BUILD_CEILING = True
BUILD_PRACTICALS = True
QUALITY = "preview"         # "preview" (128 spp, half res) or "final" (1024 spp, full res, remeshed plaster)
HERO_PLASTER = QUALITY == "final"   # voxel-remesh the walls + true displacement (Cycles; heavy)
HERO_VOXEL = 0.04
REMOVE_DEFAULT_OBJECTS = True   # delete the startup Cube / Light / Camera

# Poly Haven (CC0 scanned assets).  Needs api.polyhaven.com and dl.polyhaven.org
# reachable; without them everything falls back to the procedural stand-ins.
USE_POLYHAVEN = True
PH_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "verdio_polyhaven")
PH_TEX_RES, PH_MODEL_RES, PH_HDRI_RES = "2k", "1k", "4k"

SPACE_BLUE = "#1D2951"

# Derived interior faces
XI0, XI1 = EXT_T, PLATE_X - EXT_T
YI0, YI1 = EXT_T, PLATE_Y - EXT_T
HT = INT_T / 2
YS0, YS1 = Y_SPLIT - HT, Y_SPLIT + HT
ES_HALF = ES_DEPTH / 2
ES_MAT = "iron" if ENSUITE_FRAME == "iron" else "oak"
# The flat pad (building, veranda, yard); dunes rise beyond it
PAD = (-2.0, -VERANDA_DEPTH - 1.5, PLATE_X + 2.0, PLATE_Y + 6.5)


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


def smooth(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


class MB:
    """Accumulates boxes, beams and blobs into one bmesh, one material slot per key."""

    def __init__(self):
        self.bm = bmesh.new()
        self.mats = []

    def _idx(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def _hex(self, pts, mat):
        idx = self._idx(mat)
        v = [self.bm.verts.new(p) for p in pts]
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                  (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.bm.faces.new([v[i] for i in f]).material_index = idx

    def box(self, x0, y0, z0, x1, y1, z1, mat):
        xa, xb = sorted((x0, x1))
        ya, yb = sorted((y0, y1))
        za, zb = sorted((z0, z1))
        if xb - xa < 1e-5 or yb - ya < 1e-5 or zb - za < 1e-5:
            return
        self._hex(((xa, ya, za), (xb, ya, za), (xb, yb, za), (xa, yb, za),
                   (xa, ya, zb), (xb, ya, zb), (xb, yb, zb), (xa, yb, zb)), mat)

    def beam(self, a, b, width, depth, mat):
        """Box of `width` x `depth` along the segment a-b (rafters, roofs, bent trunks)."""
        a, b = Vector(a), Vector(b)
        d = (b - a).normalized()
        side = d.cross(Vector((0, 0, 1)))
        side = side.normalized() if side.length > 1e-6 else Vector((1, 0, 0))
        up = side.cross(d).normalized()
        s, u = side * (width / 2), up * (depth / 2)
        self._hex([a - s - u, a + s - u, a + s + u, a - s + u,
                   b - s - u, b + s - u, b + s + u, b - s + u], mat)

    def prism(self, base, offset, mat):
        """Extrude a convex polygon by `offset` (gables)."""
        idx = self._idx(mat)
        off = Vector(offset)
        v0 = [self.bm.verts.new(Vector(p)) for p in base]
        v1 = [self.bm.verts.new(Vector(p) + off) for p in base]
        n = len(base)
        self.bm.faces.new(v0).material_index = idx
        self.bm.faces.new(list(reversed(v1))).material_index = idx
        for i in range(n):
            j = (i + 1) % n
            self.bm.faces.new((v0[i], v0[j], v1[j], v1[i])).material_index = idx

    def hull(self, verts, faces, mats):
        """Arbitrary closed solid: `faces` index into `verts`, one material key per face."""
        v = [self.bm.verts.new(Vector(p)) for p in verts]
        for f, m in zip(faces, mats):
            self.bm.faces.new([v[i] for i in f]).material_index = self._idx(m)

    def blob(self, center, radius, mat, scale=(1, 1, 1), rough=0.22, rng=None, subdiv=2):
        """Jittered icosphere: canopies, shrubs, oven domes."""
        rng = rng or random
        idx = self._idx(mat)
        c = Vector(center)
        verts = bmesh.ops.create_icosphere(self.bm, subdivisions=subdiv, radius=radius,
                                           matrix=Matrix.Identity(4))["verts"]
        for v in verts:
            o = Vector(v.co)
            k = 1.0 + rng.uniform(-rough, rough)
            v.co = c + Vector((o.x * scale[0], o.y * scale[1], o.z * scale[2])) * k
        for f in {f for v in verts for f in v.link_faces}:
            f.material_index = idx
            f.smooth = True

    def build(self, name, col, location=(0.0, 0.0, 0.0)):
        if not self.bm.verts:
            self.bm.free()
            return None
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
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


def glazed_grid(mb, axis, p, a0, a1, z0, z1, cols=1, rows=1, frame=0.045,
                bar=0.022, depth=0.05, glass=True, glass_t=0.010, mat="iron"):
    """Frame with divided-light glazing bars and a glass pane (oak or iron)."""
    d = depth / 2
    abox(mb, axis, p - d, p + d, a0, a0 + frame, z0, z1, mat)
    abox(mb, axis, p - d, p + d, a1 - frame, a1, z0, z1, mat)
    abox(mb, axis, p - d, p + d, a0 + frame, a1 - frame, z1 - frame, z1, mat)
    abox(mb, axis, p - d, p + d, a0 + frame, a1 - frame, z0, z0 + frame, mat)
    ia0, ia1, iz0, iz1 = a0 + frame, a1 - frame, z0 + frame, z1 - frame
    bd = d * 0.7
    for i in range(1, cols):
        a = ia0 + (ia1 - ia0) * i / cols
        abox(mb, axis, p - bd, p + bd, a - bar / 2, a + bar / 2, iz0, iz1, mat)
    for j in range(1, rows):
        z = iz0 + (iz1 - iz0) * j / rows
        abox(mb, axis, p - bd, p + bd, ia0, ia1, z - bar / 2, z + bar / 2, mat)
    if glass:
        abox(mb, axis, p - glass_t / 2, p + glass_t / 2, ia0, ia1, iz0, iz1, "glass")


def drive(ob, path, index, ctrl, expr):
    """Scripted driver reading ctrl["open"] as `k` (simple expression, no auto-run needed)."""
    fc = ob.driver_add(path, index)
    drv = fc.driver
    drv.type = "SCRIPTED"
    var = drv.variables.new()
    var.name = "k"
    var.type = "SINGLE_PROP"
    var.targets[0].id_type = "OBJECT"
    var.targets[0].id = ctrl
    var.targets[0].data_path = '["open"]'
    drv.expression = expr


def controller(name, location, value, col, tip):
    ctrl = bpy.data.objects.new(name, None)
    ctrl.empty_display_type = "SINGLE_ARROW"
    ctrl.empty_display_size = 0.6
    ctrl.location = location
    ctrl["open"] = float(value)
    try:
        ctrl.id_properties_ui("open").update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, description=tip)
    except (AttributeError, TypeError):
        pass
    col.objects.link(ctrl)
    return ctrl


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


def _multiply_color(nt, loc, a, b):
    m = _node(nt, "ShaderNodeVectorMath", loc, operation="MULTIPLY")
    _link(nt, a, m.inputs[0])
    _link(nt, b, m.inputs[1])
    return m.outputs["Vector"]


def _wall_plane_uv(nt, loc):
    """(along-wall, z) coordinates for vertical faces of either orientation,
    so a 2D Brick texture reads correctly on every facade."""
    tc = _node(nt, "ShaderNodeTexCoord", (loc[0] - 600, loc[1]))
    pos = _node(nt, "ShaderNodeSeparateXYZ", (loc[0] - 400, loc[1] + 100))
    nrm = _node(nt, "ShaderNodeSeparateXYZ", (loc[0] - 400, loc[1] - 150))
    _link(nt, tc.outputs["Object"], pos.inputs[0])
    _link(nt, tc.outputs["Normal"], nrm.inputs[0])
    faces_y = _math(nt, (loc[0] - 250, loc[1] - 150), "GREATER_THAN",
                    _math(nt, (loc[0] - 300, loc[1] - 250), "ABSOLUTE", nrm.outputs["Y"]).outputs[0], 0.5)
    inv = _math(nt, (loc[0] - 100, loc[1] - 250), "SUBTRACT", 1.0, faces_y.outputs[0])
    y_part = _math(nt, (loc[0] - 100, loc[1] - 50), "MULTIPLY", pos.outputs["Y"], inv.outputs[0])
    u = _math(nt, (loc[0] + 50, loc[1]), "MULTIPLY_ADD", pos.outputs["X"], faces_y.outputs[0], y_part.outputs[0])
    comb = _node(nt, "ShaderNodeCombineXYZ", (loc[0] + 200, loc[1]))
    _link(nt, u.outputs[0], comb.inputs["X"])
    _link(nt, pos.outputs["Z"], comb.inputs["Y"])
    return comb.outputs["Vector"], tc


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


def _planked(key, name, viewport, c1, c2, gap, plank_l, plank_w, grain_scale, shade_stops,
             rough=(0.36, 0.5)):
    """Boards in the XY plane: floors, ceilings, decks."""
    mat, nt, bsdf, out = new_material(key, name, viewport, rough[0])
    tc = _node(nt, "ShaderNodeTexCoord", (-1300, 0))
    planks = _brick(nt, (-900, 250), tc.outputs["Object"], c1, c2, gap, plank_l, plank_w, 0.0015)
    space = _mapping(nt, (-1000, -150), tc.outputs["Object"], scale=grain_scale)
    grain = _noise(nt, (-800, -150), space.outputs["Vector"], 1.0, detail=6.0, rough=0.6, distortion=0.8)
    shade = _ramp(nt, (-550, -150), grain.outputs["Fac"], shade_stops)
    _link(nt, _multiply_color(nt, (-250, 150), planks.outputs["Color"], shade.outputs["Color"]),
          bsdf.inputs["Base Color"])
    r = _maprange(nt, (-250, -150), grain.outputs["Fac"], 0.3, 0.7, rough[0], rough[1])
    _link(nt, r.outputs[0], bsdf.inputs["Roughness"])
    seam = _bump(nt, (100, -300), 0.4, 0.002, planks.outputs["Fac"], invert=True)
    b2 = _bump(nt, (300, -300), 0.05, 0.0005, grain.outputs["Fac"], normal=seam.outputs["Normal"])
    _link(nt, b2.outputs["Normal"], bsdf.inputs["Normal"])


def _grained(key, name, viewport, stops, rough=(0.38, 0.52), scale=(45.0, 45.0, 1.5)):
    """Solid timber with vertical grain: joinery, beams, posts."""
    mat, nt, bsdf, out = new_material(key, name, viewport, rough[0])
    tc = _node(nt, "ShaderNodeTexCoord", (-1100, 0))
    space = _mapping(nt, (-900, 0), tc.outputs["Object"], scale=scale)
    grain = _noise(nt, (-700, 0), space.outputs["Vector"], 1.0, detail=6.0, rough=0.6, distortion=0.9)
    col = _ramp(nt, (-450, 150), grain.outputs["Fac"], stops)
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])
    r = _maprange(nt, (-450, -100), grain.outputs["Fac"], 0.3, 0.7, rough[0], rough[1])
    _link(nt, r.outputs[0], bsdf.inputs["Roughness"])
    b = _bump(nt, (0, -300), 0.08, 0.0006, grain.outputs["Fac"])
    _link(nt, b.outputs["Normal"], bsdf.inputs["Normal"])


def mat_tiles(key, name, viewport, c1, c2, mortar, w, h, mortar_size, offset, rough=(0.72, 0.92)):
    """Square-jointed floor tiles or stone flags in the XY plane."""
    mat, nt, bsdf, out = new_material(key, name, viewport, rough[0])
    tc = _node(nt, "ShaderNodeTexCoord", (-1200, 0))
    tiles = _brick(nt, (-850, 250), tc.outputs["Object"], c1, c2, mortar, w, h, mortar_size, offset=offset)
    mottle = _noise(nt, (-850, -150), tc.outputs["Object"], 6.0, detail=4.0, rough=0.6)
    shade = _ramp(nt, (-600, -150), mottle.outputs["Fac"], [(0.35, "#B8B8B8"), (0.65, "#FFFFFF")])
    _link(nt, _multiply_color(nt, (-300, 150), tiles.outputs["Color"], shade.outputs["Color"]),
          bsdf.inputs["Base Color"])
    r = _maprange(nt, (-300, -100), tiles.outputs["Fac"], 0.0, 1.0, rough[0], rough[1])
    _link(nt, r.outputs[0], bsdf.inputs["Roughness"])
    joint = _bump(nt, (100, -300), 0.5, 0.003, tiles.outputs["Fac"], invert=True)
    b2 = _bump(nt, (300, -300), 0.1, 0.0006, mottle.outputs["Fac"], normal=joint.outputs["Normal"])
    _link(nt, b2.outputs["Normal"], bsdf.inputs["Normal"])


def mat_brick():
    """Hand-moulded Waal-format brick (210 x 50 mm, 10 mm lime joints), weathered red-brown."""
    mat, nt, bsdf, out = new_material("brick", "VRD_Brick_Handvorm", "#7E4330", 0.85)
    uv, tc = _wall_plane_uv(nt, (-900, 0))
    bricks = _brick(nt, (-450, 250), uv, "#74382A", "#94523A", "#BDB3A3", 0.22, 0.062, 0.009)
    weather = _noise(nt, (-450, -150), tc.outputs["Object"], 1.8, detail=5.0, rough=0.6)
    shade = _ramp(nt, (-250, -150), weather.outputs["Fac"], [(0.3, "#9A9A9A"), (0.7, "#FFFFFF")])
    _link(nt, _multiply_color(nt, (-50, 150), bricks.outputs["Color"], shade.outputs["Color"]),
          bsdf.inputs["Base Color"])
    joint = _bump(nt, (200, -300), 0.6, 0.004, bricks.outputs["Fac"], invert=True)
    _link(nt, joint.outputs["Normal"], bsdf.inputs["Normal"])


def mat_pantile():
    """Aged red Dutch pantiles: courses in plan, S-wave profile as bump."""
    mat, nt, bsdf, out = new_material("pantile", "VRD_Pantile_OudRood", "#8F3E25", 0.75)
    tc = _node(nt, "ShaderNodeTexCoord", (-1100, 0))
    tiles = _brick(nt, (-750, 250), tc.outputs["Object"], "#8A3B24", "#A65233", "#3E2016",
                   0.24, 0.29, 0.012, offset=0.0)
    wave = _node(nt, "ShaderNodeTexWave", (-750, -150), wave_type="BANDS", bands_direction="X")
    _inp(wave, "Scale", 1.0 / 0.24 / 1.0)
    _link(nt, tc.outputs["Object"], wave.inputs["Vector"])
    lichen = _noise(nt, (-750, -400), tc.outputs["Object"], 2.5, detail=5.0, rough=0.65)
    shade = _ramp(nt, (-450, -400), lichen.outputs["Fac"], [(0.45, "#FFFFFF"), (0.62, "#8C8A70")])
    _link(nt, _multiply_color(nt, (-200, 150), tiles.outputs["Color"], shade.outputs["Color"]),
          bsdf.inputs["Base Color"])
    b1 = _bump(nt, (100, -200), 0.6, 0.02, wave.outputs["Fac"])
    b2 = _bump(nt, (300, -200), 0.5, 0.01, tiles.outputs["Fac"], normal=b1.outputs["Normal"], invert=True)
    _link(nt, b2.outputs["Normal"], bsdf.inputs["Normal"])


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


def mat_iron():
    """Hand-forged, blackened iron: dark, satin, faint hammer marks.  Reads as
    a traditional smith's finish, not as powder coat."""
    mat, nt, bsdf, out = new_material("iron", "VRD_Iron_Forged", "#1B1A19", 0.55)
    _inp(bsdf, "Metallic", 0.7)
    tc = _node(nt, "ShaderNodeTexCoord", (-900, 0))
    var = _noise(nt, (-650, 100), tc.outputs["Object"], 8.0, detail=4.0, rough=0.6)
    col = _ramp(nt, (-400, 200), var.outputs["Fac"], [(0.35, "#141312"), (0.7, "#2A2622")])
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])
    r = _maprange(nt, (-400, -50), var.outputs["Fac"], 0.3, 0.7, 0.45, 0.72)
    _link(nt, r.outputs[0], bsdf.inputs["Roughness"])
    hammer = _node(nt, "ShaderNodeTexVoronoi", (-650, -250), feature="SMOOTH_F1")
    _inp(hammer, "Scale", 60.0)
    _link(nt, tc.outputs["Object"], hammer.inputs["Vector"])
    b = _bump(nt, (0, -300), 0.12, 0.0005, hammer.outputs["Distance"])
    _link(nt, b.outputs["Normal"], bsdf.inputs["Normal"])


def mat_books():
    """Book spines on vertical faces facing +/-Y: Brick texture in the XZ plane."""
    mat, nt, bsdf, out = new_material("books", "VRD_Books", "#3A2A22", 0.6)
    tc = _node(nt, "ShaderNodeTexCoord", (-900, 0))
    xz = _mapping(nt, (-700, 0), tc.outputs["Object"], rot=(math.pi / 2, 0, 0))
    spines = _brick(nt, (-450, 0), xz.outputs["Vector"], "#5A2620", "#22362E", "#0B0806",
                    0.035, 0.31, 0.004, offset=0.37, bias=0.0)
    _link(nt, spines.outputs["Color"], bsdf.inputs["Base Color"])


def mat_foliage(key, name, c_dark, c_light, translucency=0.3):
    """Leaf mass for blob proxies: colour noise, leaf-scale bump, light through leaves."""
    mat, nt, bsdf, out = new_material(key, name, c_dark, 0.6)
    tc = _node(nt, "ShaderNodeTexCoord", (-1000, 0))
    n = _noise(nt, (-750, 150), tc.outputs["Object"], 3.0, detail=4.0, rough=0.6)
    col = _ramp(nt, (-500, 200), n.outputs["Fac"], [(0.35, c_dark), (0.7, c_light)])
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])
    leaves = _node(nt, "ShaderNodeTexVoronoi", (-750, -200), feature="F1")
    _inp(leaves, "Scale", 28.0)
    _link(nt, tc.outputs["Object"], leaves.inputs["Vector"])
    b = _bump(nt, (-250, -250), 0.7, 0.03, leaves.outputs["Distance"])
    _link(nt, b.outputs["Normal"], bsdf.inputs["Normal"])
    trans = _node(nt, "ShaderNodeBsdfTranslucent", (300, -250))
    _link(nt, col.outputs["Color"], trans.inputs["Color"])
    _link(nt, b.outputs["Normal"], trans.inputs["Normal"])
    mix = _node(nt, "ShaderNodeMixShader", (700, 0))
    mix.inputs[0].default_value = translucency
    _link(nt, bsdf.outputs["BSDF"], mix.inputs[1])
    _link(nt, trans.outputs["BSDF"], mix.inputs[2])
    _link(nt, mix.outputs["Shader"], out.inputs["Surface"])


def mat_vine():
    """Climbing vine over the pergola: one thin plane whose shader cuts out
    leaf clusters, which casts dappled light on the outdoor table."""
    mat, nt, bsdf, out = new_material("vine", "VRD_Vine_Canopy", "#4A6330", 0.55)
    tc = _node(nt, "ShaderNodeTexCoord", (-1300, 0))
    cluster = _noise(nt, (-1000, 250), tc.outputs["Object"], 1.6, detail=3.0, rough=0.55)
    dense = _maprange(nt, (-750, 300), cluster.outputs["Fac"], 0.48, 0.58, 0.0, 1.0)
    leaves = _node(nt, "ShaderNodeTexVoronoi", (-1000, -100), feature="F1")
    _inp(leaves, "Scale", 22.0)
    _link(nt, tc.outputs["Object"], leaves.inputs["Vector"])
    disc = _maprange(nt, (-750, -100), leaves.outputs["Distance"], 0.28, 0.4, 1.0, 0.0)
    edge = _maprange(nt, (-750, 100), cluster.outputs["Fac"], 0.38, 0.5, 0.0, 1.0)
    mask = _math(nt, (-500, 100), "MAXIMUM", dense.outputs[0],
                 _math(nt, (-600, -50), "MULTIPLY", disc.outputs[0], edge.outputs[0]).outputs[0])
    col = _ramp(nt, (-500, 400), cluster.outputs["Fac"], [(0.4, "#34492A"), (0.7, "#6C7F3A")])
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])
    trans = _node(nt, "ShaderNodeBsdfTranslucent", (300, -250))
    _link(nt, col.outputs["Color"], trans.inputs["Color"])
    leaf = _node(nt, "ShaderNodeMixShader", (600, -100))
    leaf.inputs[0].default_value = 0.35
    _link(nt, bsdf.outputs["BSDF"], leaf.inputs[1])
    _link(nt, trans.outputs["BSDF"], leaf.inputs[2])
    hole = _node(nt, "ShaderNodeBsdfTransparent", (600, 150))
    cut = _node(nt, "ShaderNodeMixShader", (800, 0))
    _link(nt, mask.outputs[0], cut.inputs[0])
    _link(nt, hole.outputs["BSDF"], cut.inputs[1])
    _link(nt, leaf.outputs["Shader"], cut.inputs[2])
    _link(nt, cut.outputs["Shader"], out.inputs["Surface"])


def mat_sand():
    """Beach to dune: wet sand at the waterline, dry sand, grey-green dune crust inland."""
    mat, nt, bsdf, out = new_material("sand", "VRD_Sand_Dune", "#D2C09A", 0.9)
    tc = _node(nt, "ShaderNodeTexCoord", (-1200, 0))
    sep = _node(nt, "ShaderNodeSeparateXYZ", (-950, 200))
    _link(nt, tc.outputs["Object"], sep.inputs[0])
    patch = _noise(nt, (-950, -100), tc.outputs["Object"], 0.15, detail=4.0, rough=0.6)
    height = _math(nt, (-700, 200), "MULTIPLY_ADD", patch.outputs["Fac"], 1.2, sep.outputs["Z"])
    fac = _maprange(nt, (-500, 200), height.outputs[0], SEA_LEVEL - 0.1, 3.0, 0.0, 1.0)
    col = _ramp(nt, (-250, 250), fac.outputs[0],
                [(0.0, "#7B6A52"), (0.12, "#CDB891"), (0.4, "#D9C8A3"), (0.75, "#A9A07C"), (1.0, "#8F8B68")])
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])
    wet = _maprange(nt, (-250, 0), fac.outputs[0], 0.0, 0.12, 0.25, 0.92)
    _link(nt, wet.outputs[0], bsdf.inputs["Roughness"])
    ripple_space = _mapping(nt, (-700, -300), tc.outputs["Object"], scale=(1.0, 6.0, 1.0),
                            rot=(0, 0, math.radians(20)))
    ripple = _noise(nt, (-500, -300), ripple_space.outputs["Vector"], 3.0, detail=3.0, rough=0.5)
    b = _bump(nt, (0, -300), 0.3, 0.01, ripple.outputs["Fac"])
    _link(nt, b.outputs["Normal"], bsdf.inputs["Normal"])


def mat_sea():
    mat, nt, bsdf, out = new_material("sea", "VRD_North_Sea", "#1A3A3E", 0.06)
    _inp(bsdf, "Base Color", lin("#16353A"))
    _inp(bsdf, "IOR", 1.33)
    tc = _node(nt, "ShaderNodeTexCoord", (-900, 0))
    swell_space = _mapping(nt, (-700, 0), tc.outputs["Object"], scale=(0.35, 1.0, 1.0))
    swell = _noise(nt, (-500, 0), swell_space.outputs["Vector"], 0.4, detail=8.0, rough=0.62)
    b = _bump(nt, (0, -200), 0.35, 0.15, swell.outputs["Fac"])
    _link(nt, b.outputs["Normal"], bsdf.inputs["Normal"])


def mat_grass():
    """Marram grass on hair strands: grey-green to bleached straw per strand."""
    mat, nt, bsdf, out = new_material("grass", "VRD_Marram_Grass", "#8E8B5E", 0.55)
    info = _node(nt, "ShaderNodeHairInfo", (-700, 0))
    mix = _math(nt, (-500, 0), "MULTIPLY_ADD", info.outputs["Intercept"], 0.35, info.outputs["Random"])
    col = _ramp(nt, (-250, 100), mix.outputs[0],
                [(0.0, "#6F7650"), (0.45, "#9A9566"), (0.75, "#C4B585"), (1.0, "#D8CBA0")])
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])


def mat_embers():
    mat, nt, bsdf, out = principled("embers", "VRD_Charcoal_Embers", "#1A0A05", 0.9)
    _inp(bsdf, ["Emission Color", "Emission"], lin("#FF4A12"))
    _inp(bsdf, "Emission Strength", 8.0)


def mat_thatch():
    """Aged Dutch reed thatch: streaks run down the slope on every roof face
    (they follow Z in object space), with moss in patches."""
    mat, nt, bsdf, out = new_material("thatch", "VRD_Reed_Thatch", "#6F604A", 0.95)
    tc = _node(nt, "ShaderNodeTexCoord", (-1100, 0))
    space = _mapping(nt, (-900, 100), tc.outputs["Object"], scale=(55.0, 55.0, 2.5))
    reed = _noise(nt, (-700, 100), space.outputs["Vector"], 1.0, detail=8.0, rough=0.7, distortion=0.4)
    moss = _noise(nt, (-700, -200), tc.outputs["Object"], 0.6, detail=4.0, rough=0.6)
    tone = _math(nt, (-450, 100), "MULTIPLY_ADD", moss.outputs["Fac"], 0.35,
                 _math(nt, (-550, 250), "MULTIPLY", reed.outputs["Fac"], 0.65).outputs[0])
    col = _ramp(nt, (-250, 150), tone.outputs[0],
                [(0.3, "#4A4232"), (0.5, "#7A6A4E"), (0.62, "#9A8762"), (0.75, "#666B45")])
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])
    b = _bump(nt, (0, -250), 0.9, 0.03, reed.outputs["Fac"])
    _link(nt, b.outputs["Normal"], bsdf.inputs["Normal"])


def mat_pool_water():
    """Natural swimming pond: clear on top, green-teal with depth (volume
    absorption), soft ripples, and sun reaching the floor (shadow-ray trick)."""
    mat, nt, bsdf, out = new_material("pool_water", "VRD_Pond_Water", "#4F7A70", 0.02)
    _inp(bsdf, "Base Color", lin("#E6F0EC"))
    _inp(bsdf, ["Transmission Weight", "Transmission"], 1.0)
    _inp(bsdf, "IOR", 1.333)
    tc = _node(nt, "ShaderNodeTexCoord", (-700, -200))
    ripple = _noise(nt, (-500, -200), tc.outputs["Object"], 2.5, detail=4.0, rough=0.5)
    b = _bump(nt, (-250, -200), 0.12, 0.02, ripple.outputs["Fac"])
    _link(nt, b.outputs["Normal"], bsdf.inputs["Normal"])
    lp = _node(nt, "ShaderNodeLightPath", (100, 300))
    clear = _node(nt, "ShaderNodeBsdfTransparent", (300, -200))
    mix = _node(nt, "ShaderNodeMixShader", (700, 0))
    _link(nt, lp.outputs["Is Shadow Ray"], mix.inputs[0])
    _link(nt, bsdf.outputs["BSDF"], mix.inputs[1])
    _link(nt, clear.outputs["BSDF"], mix.inputs[2])
    _link(nt, mix.outputs["Shader"], out.inputs["Surface"])
    vol = _node(nt, "ShaderNodeVolumeAbsorption", (500, -350))
    vol.inputs["Color"].default_value = lin("#3E7A68")
    vol.inputs["Density"].default_value = 0.9
    _link(nt, vol.outputs["Volume"], out.inputs["Volume"])


def mat_hair(key, name, stops, by="Random"):
    """Grass, reeds: colour per strand (Random) or root to tip (Intercept)."""
    mat, nt, bsdf, out = new_material(key, name, stops[len(stops) // 2][1], 0.55)
    info = _node(nt, "ShaderNodeHairInfo", (-700, 0))
    col = _ramp(nt, (-300, 100), info.outputs[by], stops)
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])


def mat_wildflowers():
    """One material for every flower head: each instance picks a meadow colour."""
    mat, nt, bsdf, out = new_material("wildflower", "VRD_Wildflower_Heads", "#C9302C", 0.5)
    info = _node(nt, "ShaderNodeObjectInfo", (-700, 0))
    col = _ramp(nt, (-350, 100), info.outputs["Random"],
                [(0.0, "#C3292A"), (0.3, "#3A5BA9"), (0.5, "#F1EDE0"), (0.75, "#E9C23A"), (0.9, "#7D4E9E")])
    col.color_ramp.interpolation = "CONSTANT"
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])
    _inp(bsdf, ["Sheen Weight", "Sheen"], 0.4)


def mat_shell():
    """Crushed-shell path, the Dutch coastal path surface."""
    mat, nt, bsdf, out = new_material("shell", "VRD_Shell_Path", "#D9D3C6", 0.85)
    tc = _node(nt, "ShaderNodeTexCoord", (-900, 0))
    bits = _node(nt, "ShaderNodeTexVoronoi", (-650, 0), feature="F1")
    _inp(bits, "Scale", 60.0)
    _link(nt, tc.outputs["Object"], bits.inputs["Vector"])
    col = _ramp(nt, (-350, 150), bits.outputs["Distance"], [(0.05, "#9C968A"), (0.35, "#E2DCCF"), (0.7, "#F0ECE2")])
    _link(nt, col.outputs["Color"], bsdf.inputs["Base Color"])
    b = _bump(nt, (-50, -250), 0.6, 0.006, bits.outputs["Distance"])
    _link(nt, b.outputs["Normal"], bsdf.inputs["Normal"])


def build_garden_materials():
    mat_thatch()
    mat_pool_water()
    mat_wildflowers()
    mat_shell()
    mat_hair("lawn", "VRD_Lawn_Grass", [(0.0, "#3B5524"), (0.5, "#56722F"), (1.0, "#7A8A44")])
    mat_hair("meadow", "VRD_Meadow_Grass", [(0.0, "#5A6B35"), (0.6, "#8C9052"), (1.0, "#B9AE76")])
    mat_hair("reed", "VRD_Reed_Common", [(0.0, "#4F6232"), (0.7, "#7E8550"), (1.0, "#B7A574")], by="Intercept")
    _grained("soil", "VRD_Garden_Soil", "#3E3226", [(0.3, "#2E251C"), (0.7, "#4A3D2F")],
             rough=(0.9, 1.0), scale=(4.0, 4.0, 4.0))
    principled("stem", "VRD_Plant_Stem", "#4C6B2F", 0.6)
    for i, c in enumerate(BULB_COLOURS):
        principled(f"tulip{i}", f"VRD_Tulip_{i}", c, 0.45, sheen=0.3)


def build_materials():
    mat_plaster()
    _planked("oak_floor", "VRD_Oak_Floor_DarkStained", "#2A1A10", "#2C1B11", "#3D2717", "#0C0805",
             1.6, 0.19, (1.5, 70.0, 70.0), [(0.3, "#8A8A8A"), (0.7, "#FFFFFF")], rough=(0.36, 0.5))
    _planked("boards", "VRD_Ceiling_Boards_Limewashed", "#CFC6B5", "#C9BFAE", "#D8CFBF", "#8F877A",
             3.0, 0.16, (1.5, 70.0, 70.0), [(0.3, "#D0D0D0"), (0.7, "#FFFFFF")], rough=(0.75, 0.9))
    _planked("deck", "VRD_Oak_Deck_Weathered", "#8C867C", "#7E786E", "#9A948A", "#3A3630",
             1.4, 0.145, (70.0, 1.5, 70.0), [(0.3, "#9C9C9C"), (0.7, "#FFFFFF")], rough=(0.7, 0.9))
    _grained("oak", "VRD_Oak_Joinery_DarkStained", "#2B1B11", [(0.3, "#1A100A"), (0.7, "#3B2618")])
    _grained("oak_weathered", "VRD_Oak_Weathered_Silver", "#8A8379",
             [(0.3, "#6A645C"), (0.7, "#A19B90")], rough=(0.7, 0.9))
    _grained("bark", "VRD_Bark", "#3A2E26", [(0.3, "#2A211B"), (0.7, "#55473B")],
             rough=(0.85, 0.95), scale=(30.0, 30.0, 3.0))
    mat_tiles("terracotta", "VRD_Terracotta_Frisian", "#9A4B2D", "#A2532F", "#874026", "#76695E",
              0.25, 0.25, 0.006, 0.0)
    mat_tiles("stone", "VRD_Bluestone_Flags", "#575B5C", "#4E5254", "#62676A", "#8A857C",
              0.6, 0.4, 0.004, 0.5, rough=(0.5, 0.8))
    mat_brick()
    mat_pantile()
    mat_glass()
    mat_iron()
    mat_books()
    mat_foliage("foliage", "VRD_Foliage", "#2E3F26", "#58693A")
    mat_foliage("buckthorn", "VRD_Foliage_SeaBuckthorn", "#5E6449", "#8C8D6C", translucency=0.2)
    mat_vine()
    mat_sand()
    mat_sea()
    mat_grass()
    mat_embers()
    principled("slab", "VRD_Lime_Mortar_Slab", "#8C857A", 0.9)
    principled("blue", "VRD_SpaceBlue_Paint", SPACE_BLUE, 0.4, coat=0.15)
    principled("brass", "VRD_Brass_Aged", "#A88653", 0.38, metallic=1.0)
    principled("bjj", "VRD_Tatami_Natural", "#A39A74", 0.7)
    principled("rubber", "VRD_Rubber_Black", "#151515", 0.85)
    principled("trainer", "VRD_Trainer_Plastic", "#2C2C2C", 0.35)
    principled("coir", "VRD_Coir_Mat", "#6E5236", 0.95)
    principled("firebox", "VRD_Firebox_Soot", "#070605", 0.95)
    principled("leather", "VRD_Leather_Oxblood", "#3A1D12", 0.45, coat=0.1)
    principled("rug", "VRD_Wool_Rug", "#4B1F1C", 1.0, sheen=0.5)
    principled("linen", "VRD_Linen_Natural", "#D6CDBC", 0.9, sheen=0.6)
    principled("pot", "VRD_Terracotta_Pot", "#9C5434", 0.85)
    build_garden_materials()


# =============================================================================
# 3b. POLY HAVEN: CC0 scanned textures, plants and sky
#     Everything here is optional; offline, the procedural setup stays.
# =============================================================================
PH_API = "https://api.polyhaven.com"
PH_MODELS = {}                      # role -> list of Collections of scanned assets
PH_STATUS = {"online": False, "used": []}

# material key: (preferred asset ids, fallback keywords, real-world tile size in m, stain hex or None)
PH_TEXTURES = {
    "oak_floor": (("wood_floor_worn", "dark_wooden_planks", "wood_floor"), ("wood", "floor", "planks"), 2.0, "#5A3E2B"),
    "terracotta": (("terracotta_tiles", "floor_tiles_06"), ("terracotta", "tiles"), 1.0, None),
    "brick": (("red_brick", "red_brick_03", "brick_wall_001"), ("brick", "red"), 2.0, None),
    "pantile": (("roof_tiles", "clay_roof_tiles", "roof_tiles_14"), ("roof", "tiles"), 2.0, None),
    "stone": (("stone_tiles", "slate_floor"), ("stone", "tiles", "slate"), 2.0, None),
    "thatch": (("thatch_roof", "thatch"), ("thatch", "straw"), 2.0, None),
    "deck": (("old_planks_02", "weathered_planks", "old_wood_floor"), ("planks", "weathered", "old"), 2.0, None),
    "soil": (("brown_mud", "forest_ground_01", "aerial_mud_1"), ("soil", "mud", "ground"), 3.0, None),
    "shell": (("gravel_floor", "gravel_floor_02"), ("gravel",), 2.0, None),
    "sand": (("coast_sand_01", "sand_01", "aerial_beach_01"), ("sand", "beach"), 4.0, None),
}
# role: (preferred asset ids, fallback keywords)
PH_MODEL_ROLES = {
    "potted": (("potted_plant_01", "potted_plant_02", "potted_plant_04"), ("potted", "plant")),
    "shrub": (("shrub_01", "shrub_02", "shrub_03", "shrub_04"), ("shrub", "bush")),
    "tree": (("island_tree_01", "island_tree_02", "island_tree_03"), ("tree",)),
    "pine": (("pine_tree_01", "fir_tree_01", "fir_sapling"), ("pine", "fir", "conifer")),
    "grass": (("grass_medium_01", "grass_medium_02"), ("grass",)),
    "fern": (("fern_02", "fern_01"), ("fern",)),
}
PH_HDRI = (("kloofendal_48d_partly_cloudy_puresky", "kloofendal_43d_clear_puresky"), ("puresky", "partly", "cloudy"))


def _ph_request(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Verdio-Blender-Blocking/1.0"})
    return urllib.request.urlopen(req, timeout=60)


def _ph_json(path):
    import json
    os.makedirs(PH_CACHE, exist_ok=True)
    cache = os.path.join(PH_CACHE, "api_" + "".join(c if c.isalnum() else "_" for c in path) + ".json")
    if os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)
    with _ph_request(PH_API + path) as r:
        data = json.loads(r.read().decode())
    with open(cache, "w") as f:
        json.dump(data, f)
    return data


def _ph_download(url, dest):
    import shutil
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with _ph_request(url) as r, open(dest + ".part", "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(dest + ".part", dest)
    return dest


def ph_pick(kind, prefer, keywords, n=1):
    """Asset ids: preferred ids that exist first, then the best keyword matches."""
    assets = _ph_json(f"/assets?t={kind}")
    picked = [p for p in prefer if p in assets][:n]
    if len(picked) < n:
        scored = []
        for aid, info in assets.items():
            if aid in picked:
                continue
            hay = " ".join([aid, info.get("name", "")] + list(info.get("tags", [])) +
                           list(info.get("categories", []))).lower()
            score = sum(1 for k in keywords if k in hay)
            if score:
                scored.append((-score, -info.get("download_count", 0), aid))
        picked += [aid for _s, _d, aid in sorted(scored)[: n - len(picked)]]
    return picked


def _pick_file(entry, formats):
    for fmt in formats:
        if fmt in entry:
            return entry[fmt]["url"]
    return next(iter(entry.values()))["url"]


def ph_texture_maps(aid, res=None):
    files = _ph_json(f"/files/{aid}")
    res = res or PH_TEX_RES
    maps = {}
    for key, names in (("diff", ("Diffuse", "diffuse")), ("rough", ("Rough", "rough")),
                       ("nor", ("nor_gl", "Normal")), ("disp", ("Displacement", "disp"))):
        for nm in names:
            if nm in files:
                entry = files[nm].get(res) or next(iter(files[nm].values()))
                url = _pick_file(entry, ("jpg", "png", "exr"))
                maps[key] = _ph_download(url, os.path.join(PH_CACHE, "textures", aid, os.path.basename(url)))
                break
    return maps


def ph_material(key, aid, maps, size, stain):
    """Rebuild MAT[key] in place (same name, so slots stay) from scanned maps,
    box-projected on Object coordinates at real-world scale."""
    old = MAT[key]
    viewport = old.diffuse_color[:]
    mat, nt, bsdf, out = new_material(key, old.name, "#808080", 0.6)
    mat.diffuse_color = viewport
    tc = _node(nt, "ShaderNodeTexCoord", (-1200, 0))
    mp = _mapping(nt, (-1000, 0), tc.outputs["Object"], scale=(1.0 / size,) * 3)

    def img(path, loc, non_color):
        n = _node(nt, "ShaderNodeTexImage", loc)
        n.image = bpy.data.images.load(path, check_existing=True)
        n.projection = "BOX"
        n.projection_blend = 0.25
        if non_color:
            n.image.colorspace_settings.name = "Non-Color"
        _link(nt, mp.outputs["Vector"], n.inputs["Vector"])
        return n

    if "diff" in maps:
        d = img(maps["diff"], (-700, 300), False)
        colour = d.outputs["Color"]
        if stain:
            st = _node(nt, "ShaderNodeVectorMath", (-350, 300), operation="MULTIPLY")
            _link(nt, colour, st.inputs[0])
            st.inputs[1].default_value = lin(stain)[:3]
            colour = st.outputs["Vector"]
        _link(nt, colour, bsdf.inputs["Base Color"])
    if "rough" in maps:
        _link(nt, img(maps["rough"], (-700, 0), True).outputs["Color"], bsdf.inputs["Roughness"])
    if "nor" in maps:
        nm = _node(nt, "ShaderNodeNormalMap", (-300, -250))
        _link(nt, img(maps["nor"], (-700, -300), True).outputs["Color"], nm.inputs["Color"])
        _link(nt, nm.outputs["Normal"], bsdf.inputs["Normal"])
    if "disp" in maps:
        dn = _node(nt, "ShaderNodeDisplacement", (500, -400))
        _link(nt, img(maps["disp"], (-700, -600), True).outputs["Color"], dn.inputs["Height"])
        _inp(dn, "Scale", 0.01 * size)
        _link(nt, dn.outputs["Displacement"], out.inputs["Displacement"])
        set_displacement_method(mat, "BUMP")


def ph_model_collection(aid):
    """Append a scanned model's objects into a Collection that is not linked to
    the scene: it renders only through the instances that point at it."""
    name = f"PH_{aid}"
    existing = bpy.data.collections.get(name)
    if existing is not None and existing.objects:
        return existing
    files = _ph_json(f"/files/{aid}")
    blend = files["blend"]
    entry = (blend.get(PH_MODEL_RES) or next(iter(blend.values())))["blend"]
    folder = os.path.join(PH_CACHE, "models", aid)
    path = _ph_download(entry["url"], os.path.join(folder, os.path.basename(entry["url"])))
    for rel, inc in entry.get("include", {}).items():
        _ph_download(inc["url"], os.path.join(folder, rel))
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = list(src.objects)
    coll = existing or bpy.data.collections.new(name)
    for ob in dst.objects:
        if ob is not None:
            coll.objects.link(ob)
    for im in bpy.data.images:                # appended texture paths are relative to the source file
        if im.filepath.startswith("//") and not os.path.exists(bpy.path.abspath(im.filepath)):
            cand = os.path.join(folder, im.filepath[2:])
            if os.path.exists(cand):
                im.filepath = cand
    return coll


def ph_hdri_path(aid):
    files = _ph_json(f"/files/{aid}")
    hdri = files["hdri"]
    entry = hdri.get(PH_HDRI_RES) or next(iter(hdri.values()))
    url = _pick_file(entry, ("exr", "hdr"))
    return _ph_download(url, os.path.join(PH_CACHE, "hdris", os.path.basename(url)))


def load_polyhaven():
    global HDRI_PATH
    if not USE_POLYHAVEN:
        return
    try:
        _ph_json("/types")
    except Exception as e:                  # offline or blocked: keep the procedural scene
        print(f"  Poly Haven unreachable ({type(e).__name__}); using procedural materials and proxies")
        return
    PH_STATUS["online"] = True
    for key, (prefer, words, size, stain) in PH_TEXTURES.items():
        try:
            aid = ph_pick("textures", prefer, words)[0]
            ph_material(key, aid, ph_texture_maps(aid), size, stain)
            PH_STATUS["used"].append(f"texture {key:<11} <- {aid}")
        except Exception as e:
            print(f"  Poly Haven texture for {key} skipped: {e}")
    for role, (prefer, words) in PH_MODEL_ROLES.items():
        cols = []
        for aid in ph_pick("models", prefer, words, n=3):
            try:
                cols.append(ph_model_collection(aid))
                PH_STATUS["used"].append(f"model   {role:<11} <- {aid}")
            except Exception as e:
                print(f"  Poly Haven model {aid} skipped: {e}")
        if cols:
            PH_MODELS[role] = cols
    if not HDRI_PATH:
        try:
            aid = ph_pick("hdris", *PH_HDRI)[0]
            HDRI_PATH = ph_hdri_path(aid)
            PH_STATUS["used"].append(f"hdri    sky         <- {aid}")
        except Exception as e:
            print(f"  Poly Haven HDRI skipped: {e}")


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
    ("Endurance", "ENDURANCE ROOM", "oak_floor",
     (X_ENSUITE, Y_SPLIT, X_END_WET, PLATE_Y), (X_ENSUITE + ES_HALF, YS1, X_END_WET - HT, YI1)),
    ("WetCore", "WET CORE", "stone",
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
        O(3.0, 2.4, 0.0, 3.0, "french_door"),           # culinary -> outdoor kitchen
        O(7.0, 2.4, 0.0, 3.0, "french_door"),
        O(11.5, 1.8, 0.0, 3.0, "french_door"),          # lounge -> veranda daybeds
        O(14.0, 1.8, 0.0, 3.0, "french_door"),
        O(16.5, 1.8, 0.0, 3.0, "french_door"),
        O(21.0, 1.8, 0.0, 2.7, "blue_door"),            # beach entrance under the porch
        O(23.4, 1.0, 0.9, 2.7, "window"),
    ]),
    "N": dict(axis="x", c=PLATE_Y - EXT_T / 2, t=EXT_T, a0=0.0, a1=PLATE_X, outer=1, openings=[
        O(2.4, 1.6, 0.5, 2.9, "window"),                # library: low sills, window seats onto the dune
        O(6.2, 1.6, 0.5, 2.9, "window"),
        O(10.0, 1.6, 0.5, 2.9, "window"),
        O(15.2, 2.4, 0.0, 3.0, "french_door"),          # endurance -> training yard
        O(19.2, 2.4, 0.0, 3.0, "french_door"),
        O(23.1, 1.2, 1.9, 2.7, "window"),               # wet core clerestory
    ]),
    "W": dict(axis="y", c=EXT_T / 2, t=EXT_T, a0=YI0, a1=YI1, outer=-1, openings=[
        O(7.75, 1.0, 0.0, 2.4, "oak_door"),             # kitchen garden door
        O(12.25, 1.6, 0.5, 2.9, "window"),              # library
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
        # the wet-to-dry threshold: oak-cased opening with a flush brass floor strip
        O(4.6, 2.6, 0.0, 2.75, "void", lining="oak", threshold=True),
    ]),
    "XEW": dict(axis="y", c=X_END_WET, t=INT_T, a0=YS1, a1=YI1, outer=0, openings=[
        O(10.0, 0.9, 0.0, 2.2, "oak_door"),             # wet core -> endurance
    ]),
}


def spans(wall):
    return [(o["at"] - o["w"] / 2, o["at"] + o["w"] / 2, o["sill"], o["head"])
            for o in wall["openings"]]


def frame_plane(wall):
    """Exterior joinery sits 100 mm in from the outer face, leaving a deep inner reveal."""
    if wall["outer"]:
        return wall["c"] + wall["outer"] * (wall["t"] / 2 - 0.10)
    return wall["c"]


def inner_face(wall):
    return wall["c"] - wall["outer"] * wall["t"] / 2


def outer_face(wall):
    return wall["c"] + wall["outer"] * wall["t"] / 2


def swing_sign(wall, leaf_dir):
    """Sign of the Z rotation that swings a leaf (extending +a when leaf_dir
    is +1, -a when -1) outward through the wall's outer side."""
    axis_sign = 1 if wall["axis"] == "x" else -1
    return axis_sign * wall["outer"] * leaf_dir


# =============================================================================
# 5. LANDSCAPE HEIGHT FIELD (also used to seat paths, pavilions and cameras)
# =============================================================================
def terrace_level(y):
    """Formal terrace level at y: the house terrace, then one step per wall."""
    lv = -0.05
    for edge, below in TERRACE_STEPS:
        if y < edge:
            lv = below
    return lv


def south_base(y):
    """The general fall of the site from the house terrace to the sea."""
    if y >= PAD[1]:
        return -0.05
    if y >= TERRACE_END:
        last = TERRACE_STEPS[-1][1]
        return -0.05 + (last + 0.05) * smooth(PAD[1], TERRACE_END, y)
    return max(TERRACE_FOOT - (TERRACE_END - y) * 0.08, SEA_LEVEL - 3.0)


def pad_distance(x, y):
    dx = max(PAD[0] - x, 0.0, x - PAD[2])
    dy = max(PAD[1] - y, 0.0, y - PAD[3])
    return math.hypot(dx, dy)


def terrace_weight(x, y):
    """1 inside the formal terrace band, fading to 0 into the dunes either side."""
    if not (TERRACE_END - 1.0 <= y < -VERANDA_DEPTH - 0.2):
        return 0.0
    tx0, tx1 = TERRACE_X
    return smooth(tx0 - 5.0, tx0, x) * (1.0 - smooth(tx1, tx1 + 5.0, x))


def raw_terrain(x, y):
    t = smooth(0.0, 14.0, pad_distance(x, y))
    n = mnoise.fractal(Vector((x * 0.035 + 31.7, y * 0.035 + 11.3, 0.0)), 1.0, 2.0, 4)
    dune = 1.0 + 3.0 * (0.5 + 0.5 * n) + 2.0 * max(0.0, n)
    base = south_base(y)
    wt = terrace_weight(x, y)
    if wt > 0.0:
        # under the terrace ground boxes: always below the lower neighbouring level
        stepped = min(terrace_level(y + 1.2), terrace_level(y), terrace_level(y - 1.2)) - 0.3
        base += (stepped - base) * wt
    if y < PAD[1]:
        dune *= 0.45 * (1.0 - wt)       # low foredune either side: keeps the panorama open
    return base + t * dune


_PAV_Z = {}


def pavilion_z(i):
    if i not in _PAV_Z:
        cx, cy = pavilion_point(PAVILIONS[i], 0.0, 1.0)
        _PAV_Z[i] = max(raw_terrain(cx, cy), 0.4)
    return _PAV_Z[i]


def pavilion_point(site, lx, ly):
    x, y, r = site
    a = math.radians(r)
    return (x + lx * math.cos(a) - ly * math.sin(a), y + lx * math.sin(a) + ly * math.cos(a))


def in_pond(x, y, margin=0.0):
    return (POND[0] - margin <= x <= REED_BED[2] + margin) and (POND[1] - margin <= y <= POND[3] + margin)


def terrain_z(x, y):
    """Flat house pad; terraces stepping down to the sea in front of it; dunes
    either side and behind; flat pads for the garden pavilions."""
    z = raw_terrain(x, y)
    for i, site in enumerate(PAVILIONS):
        cx, cy = pavilion_point(site, 0.0, 1.0)
        w = 1.0 - smooth(7.5, 13.0, math.hypot(x - cx, y - cy))
        if w > 0.0:
            z += (pavilion_z(i) - 0.05 - z) * w
    if in_pond(x, y, 0.6):
        z = min(z, -1.9)
    return z


def path_segments():
    """Boardwalk routes: house <-> pavilions, and the terraces' foot <-> beach."""
    segs = []
    starts = ((-0.45, -2.0), (-0.45, 7.75), (PLATE_X + 0.45, -2.0), (PLATE_X + 0.45, -0.8))
    for i, site in enumerate(PAVILIONS):
        segs.append((starts[i % len(starts)], pavilion_point(site, 0.0, -4.3), i))
    foot = TERRACE_END - 0.32 * max(2, round((TERRACE_STEPS[-1][1] - TERRACE_FOOT) / 0.18))
    segs.append(((BOARDWALK_X, foot), (BOARDWALK_X, -37.0), None))
    return segs


def near_path(x, y, r=1.6):
    p = Vector((x, y))
    for a, b, _i in path_segments():
        a, b = Vector(a), Vector(b)
        d = b - a
        t = max(0.0, min(1.0, (p - a).dot(d) / d.length_squared))
        if (a + d * t - p).length < r:
            return True
    return abs(x - BOARDWALK_X) < r and TERRACE_END - 1 <= y < PAD[1]


# =============================================================================
# 6. BUILDERS
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

    # Brick outside: a slip skin cut around the same openings, up to the upper floor
    skin = MB()
    top = H + SLAB_T
    for key in ("S", "N", "W", "E"):
        w = WALLS[key]
        f0, f1 = sorted((outer_face(w), outer_face(w) + w["outer"] * SKIN_T))
        a0, a1 = (-SKIN_T, PLATE_X + SKIN_T) if w["axis"] == "x" else (0.0, PLATE_Y)
        for p0, p1, z0, z1 in solid_pieces(a0, a1, top, spans(w)):
            abox(skin, w["axis"], f0, f1, p0, p1, z0, z1, "brick")
    skin.build("Facade_Brick", col)

    if BUILD_CEILING:
        c = MB()
        c.box(0, 0, H, PLATE_X, PLATE_Y, H + SLAB_T, "boards")
        c.build("Ceiling_Boards", col)


CHIMNEY_X = 14.6


def build_chimney(walls):
    """English country-house chimney breast on the lounge's north wall."""
    w, d, fw, fh = 2.0, 0.5, 0.9, 0.85
    y1, y0 = YS0, YS0 - d
    walls.box(CHIMNEY_X - w / 2, y0, 0, CHIMNEY_X - fw / 2, y1, H, "plaster")
    walls.box(CHIMNEY_X + fw / 2, y0, 0, CHIMNEY_X + w / 2, y1, H, "plaster")
    walls.box(CHIMNEY_X - fw / 2, y0, fh, CHIMNEY_X + fw / 2, y1, H, "plaster")


def joist_xs(x0, x1, margin=0.2):
    """X positions on the shared joist/rafter grid inside [x0, x1]."""
    k = math.ceil((x0 + margin) / JOIST_PITCH - 0.5)
    out = []
    while (k + 0.5) * JOIST_PITCH <= x1 - margin:
        out.append((k + 0.5) * JOIST_PITCH)
        k += 1
    return out


def build_ceiling_timber(col):
    """Exposed dark oak joists under limewashed boards; an oak girder across
    the 8.3 m coast band.  The joist grid continues outside as rafters."""
    mb = MB()
    for _key, _label, _mat, _frect, (x0, y0, x1, y1) in ZONES:
        for x in joist_xs(x0, x1):
            mb.box(x - 0.07, y0, H - 0.24, x + 0.07, y1, H, "oak")
    mb.box(XI0, GIRDER_Y - 0.15, H - 0.56, XI1, GIRDER_Y + 0.15, H - 0.24, "oak")
    mb.build("Ceiling_Oak_Joists", col)


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
    cols = max(1, round(o["w"] / 0.5))
    rows = max(1, round((o["head"] - o["sill"]) / 0.5))
    glazed_grid(mb, ax, p, a0, a1, o["sill"], o["head"], cols, rows,
                frame=0.07, bar=0.03, depth=0.07, mat="oak")
    if o["sill"] > 0 and w["outer"]:
        room = -w["outer"]
        nose = 0.06 if o["sill"] < 0.6 else 0.03    # low sills become window seats
        q0, q1 = sorted((p + room * 0.035, inner_face(w) + room * nose))
        abox(mb, ax, q0, q1, a0 - 0.03, a1 + 0.03, o["sill"] - 0.045, o["sill"], "oak")
        # brick-on-edge outer sill
        e0, e1 = sorted((p - room * 0.035, outer_face(w) - room * (SKIN_T + 0.05)))
        abox(mb, ax, e0, e1, a0 - 0.05, a1 + 0.05, o["sill"] - 0.11, o["sill"] - 0.02, "brick")


def fill_door(mb, w, o, leaf_mat, lining_mat):
    ax, t, c, p = w["axis"], w["t"], w["c"], frame_plane(w)
    a0, a1, head = o["at"] - o["w"] / 2, o["at"] + o["w"] / 2, o["head"]
    L, gap, lt = 0.03, 0.004, 0.055
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
            b0, b1 = sorted((p + s * (lt / 2 + 0.01), p + s * (lt / 2 + 0.05)))
            abox(mb, ax, b0, b1, edge - 0.02, edge + 0.02, 1.0, 1.06, "brass")   # knob


def fill_french_door(mb, w, o, col, ctrl):
    """Pair of oak French doors with a fixed fanlight, swinging outward.
    The fixed frame goes into `mb`; each leaf is its own object, pivoting on
    its hinge, driven by FACADE_CONTROL["open"]."""
    ax, p = w["axis"], frame_plane(w)
    a0, a1, head = o["at"] - o["w"] / 2, o["at"] + o["w"] / 2, o["head"]
    F, d = 0.07, 0.045
    tz = min(2.45, head - 0.35)
    abox(mb, ax, p - d, p + d, a0, a0 + F, 0, head, "oak")
    abox(mb, ax, p - d, p + d, a1 - F, a1, 0, head, "oak")
    abox(mb, ax, p - d, p + d, a0 + F, a1 - F, head - F, head, "oak")
    abox(mb, ax, p - d, p + d, a0 + F, a1 - F, tz, tz + 0.07, "oak")       # transom
    glazed_grid(mb, ax, p, a0 + F, a1 - F, tz + 0.07, head - F,
                cols=max(2, round((a1 - a0) / 0.45)), rows=1, frame=0.015, bar=0.03, depth=0.05, mat="oak")
    abox(mb, ax, p - d, p + d, a0, a1, 0.0, 0.003, "brass")               # level threshold
    lw = (a1 - a0 - 2 * F) / 2 - 0.003
    top = tz - 0.004
    theta = math.radians(100.0)
    for side, hinge, leaf_dir in (("L", a0 + F, 1), ("R", a1 - F, -1)):
        leaf = MB()
        lo, hi = sorted((0.0, leaf_dir * lw))
        glazed_grid(leaf, ax, 0.0, lo, hi, 0.008, top, cols=2, rows=4,
                    frame=0.08, bar=0.028, depth=0.05, mat="oak")
        abox(leaf, ax, -0.02, 0.02, lo + 0.08, hi - 0.08, 0.008, 0.45, "oak")  # kick panel
        knob = leaf_dir * (lw - 0.07)
        for s in (-1, 1):
            k0, k1 = sorted((s * 0.025, s * 0.06))
            abox(leaf, ax, k0, k1, knob - 0.015, knob + 0.015, 1.0, 1.05, "brass")
        loc = (hinge, p, 0.0) if ax == "x" else (p, hinge, 0.0)
        ob = leaf.build(f"FrenchDoor_{o['at']:.2f}_{side}", col, location=loc)
        sign = swing_sign(w, leaf_dir)
        drive(ob, "rotation_euler", 2, ctrl, f"{'-' if sign < 0 else ''}k*{theta:.4f}")


def add_shutters(w, o, col, ctrl):
    """Dutch luiken: boarded Space Blue shutters that fold flat against the
    brick when open."""
    ax = w["axis"]
    a0, a1 = o["at"] - o["w"] / 2, o["at"] + o["w"] / 2
    plane = outer_face(w) + w["outer"] * (SKIN_T + 0.025)
    lw = (a1 - a0) / 2 - 0.004
    z0, z1 = o["sill"] + 0.01, o["head"] - 0.01
    for side, hinge, leaf_dir in (("L", a0, 1), ("R", a1, -1)):
        leaf = MB()
        lo, hi = sorted((0.0, leaf_dir * lw))
        abox(leaf, ax, -0.0175, 0.0175, lo, hi, z0, z1, "blue")
        # ledges on the inner face: hidden when shut, showing when folded back
        l0, l1 = sorted((-w["outer"] * 0.0175, -w["outer"] * 0.04))
        for z in (z0 + 0.2, z1 - 0.2):
            abox(leaf, ax, l0, l1, lo + 0.03, hi - 0.03, z - 0.05, z + 0.05, "blue")
        s0, s1 = sorted((w["outer"] * 0.0175, w["outer"] * 0.024))
        h0, h1 = sorted((0.0, leaf_dir * 0.6 * lw))
        for z in (z0 + 0.2, z1 - 0.2):                                      # strap hinges
            abox(leaf, ax, s0, s1, h0, h1, z - 0.02, z + 0.02, "iron")
        loc = (hinge, plane, 0.0) if ax == "x" else (plane, hinge, 0.0)
        ob = leaf.build(f"Shutter_{o['at']:.2f}_{side}", col, location=loc)
        sign = swing_sign(w, leaf_dir)
        drive(ob, "rotation_euler", 2, ctrl, f"{'-' if sign < 0 else ''}k*{math.pi:.4f}")


def fill_void(mb, w, o):
    ax, t, c = w["axis"], w["t"], w["c"]
    a0, a1, head = o["at"] - o["w"] / 2, o["at"] + o["w"] / 2, o["head"]
    lining = o.get("lining")
    if lining:
        L = 0.03
        abox(mb, ax, c - t / 2 - 0.005, c + t / 2 + 0.005, a0, a0 + L, 0, head, lining)
        abox(mb, ax, c - t / 2 - 0.005, c + t / 2 + 0.005, a1 - L, a1, 0, head, lining)
        abox(mb, ax, c - t / 2 - 0.005, c + t / 2 + 0.005, a0, a1, head - L, head, lining)
    if o.get("threshold"):
        # flush 25 mm brass strip on the terracotta/oak seam
        abox(mb, ax, c - 0.0125, c + 0.0125, a0, a1, 0.0, 0.002, "brass")


def build_openings(col, facade_ctrl):
    mb = MB()
    for w in WALLS.values():
        for o in w["openings"]:
            k = o["kind"]
            if k == "window":
                fill_window(mb, w, o)
                if w["outer"] and 0 < o["sill"] < 1.5 and o["w"] <= 1.8:
                    add_shutters(w, o, col, facade_ctrl)
            elif k == "french_door":
                fill_french_door(mb, w, o, col, facade_ctrl)
            elif k == "blue_door":
                fill_door(mb, w, o, "blue", "oak")
            elif k == "oak_door":
                fill_door(mb, w, o, "oak", "oak")
            elif k == "void":
                fill_void(mb, w, o)
    mb.build("Openings_Oak_Glass_Doors", col)


def build_ensuite(col):
    """1930s Dutch Kamer en suite.  Frame in hand-forged iron (or oak, see
    ENSUITE_FRAME).

    Plan of the 600 mm partition (x across, y along):

      library | vitrine | pocket | vitrine | endurance
              | 200 mm  | 200 mm | 200 mm  |
                         ^      ^
                 skin A track   skin B track, 100 mm acoustic cavity

    Elevation along y: plaster pier | vitrine | 3.2 m opening (2 skins x 2
    pocket leaves) | vitrine | plaster pier, with the kalf at 2.75 m,
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
    mb.box(x0, o0 - JAMB, 0, x1, o0, DH, ES_MAT)         # portal jambs
    mb.box(x0, o1, 0, x1, o1 + JAMB, DH, ES_MAT)
    mb.box(x0, c0, DH, x1, c1, DH + KALF, ES_MAT)        # the kalf
    mb.box(x0, o0, 0, x1, o1, 0.004, "brass")            # threshold plate
    n_transom = max(1, round((c1 - c0) / 0.36))
    for px in (x0 + 0.03, x1 - 0.03):                    # double-glazed bovenlicht
        glazed_grid(mb, "y", px, c0, c1, DH + KALF, TT, cols=n_transom, rows=1,
                    frame=0.04, depth=0.04, mat=ES_MAT)

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
            glazed_grid(mb, "y", glaze, ya, yb, 0.85, DH, cols=2, rows=4, frame=0.04, depth=0.04, mat=ES_MAT)
    mb.build("EnSuite_Frame", col)

    ctrl = controller("EnSuite_CONTROL", (X_ENSUITE, yc, H + 0.6), ES_OPEN, col,
                      "0 = sealed, 1 = leaves pocketed")
    lap = 0.03
    lw = ES_OPENING / 2 + lap
    travel = ES_OPENING / 2
    lt = 0.04
    for skin, px in (("Library", X_ENSUITE - ES_SKIN_GAP / 2), ("Endurance", X_ENSUITE + ES_SKIN_GAP / 2)):
        for side, sign in (("S", -1), ("N", 1)):
            leaf = MB()
            ha = lw / 2 - 0.0015
            glazed_grid(leaf, "y", 0.0, -ha, ha, 0.006, DH - 0.004, cols=ES_LEAF_GRID[0],
                        rows=ES_LEAF_GRID[1], frame=0.05, bar=0.022, depth=lt, glass_t=0.016, mat=ES_MAT)
            leaf.box(-lt / 2, -ha, 0.006, lt / 2, ha, 0.15, ES_MAT)        # kick rail
            ey = -sign * (ha - 0.06)                                       # pull on the meeting stile
            for s in (-1, 1):
                leaf.box(s * lt / 2, ey - 0.01, 0.9, s * (lt / 2 + 0.012), ey + 0.01, 1.4, "brass")
            cy = yc + sign * lw / 2      # closed: laps 30 mm into the jamb
            ob = leaf.build(f"EnSuite_Leaf_{skin}_{side}", col, location=(px, cy, 0.0))
            drive(ob, "location", 1, ctrl, f"{cy:.4f} {'+' if sign > 0 else '-'} k*{travel:.4f}")


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


PLANT_SPOTS = []    # potted-plant positions filled by scanned assets after the build


def potted_tree(mb, x, y, h, rng, canopy="foliage", pot_r=0.32, z0=0.0):
    """Olive or fig in a terracotta pot: the dune garden brought indoors.
    With Poly Haven online the spot gets a scanned potted plant instead."""
    if PH_MODELS.get("potted"):
        PLANT_SPOTS.append((x, y, z0))
        return
    mb.box(x - pot_r, y - pot_r, z0, x + pot_r, y + pot_r, z0 + 0.55, "pot")
    lean = Vector((rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), 0))
    mid = Vector((x, y, z0 + h * 0.55)) + lean
    mb.beam((x, y, z0 + 0.5), mid, 0.07, 0.07, "bark")
    mb.beam(mid, mid + Vector((0.2, -0.1, h * 0.25)), 0.05, 0.05, "bark")
    for _ in range(4):
        c = mid + Vector((rng.uniform(-0.35, 0.35), rng.uniform(-0.35, 0.35), h * rng.uniform(0.25, 0.45)))
        mb.blob(c, rng.uniform(0.3, 0.45), canopy, scale=(1.0, 1.0, 0.75), rng=rng, subdiv=3)


def build_props(col):
    rnd = random.Random(1930)

    # --- Culinary core: back kitchen, charcoal-grill hearth, communal table
    k = MB()
    k.box(XI0, 1.0, 0, XI0 + 0.65, 7.0, 0.88, "oak")
    k.box(XI0, 1.0, 0.88, XI0 + 0.68, 7.0, 0.92, "stone")
    for z in (1.55, 2.0):
        k.box(XI0, 1.4, z, XI0 + 0.32, 6.6, z + 0.04, "oak")
    ix0, ix1, iy0, iy1 = 2.2, 3.4, 3.0, 6.6
    wx0, wx1, wy0, wy1 = 2.45, 3.15, 4.0, 5.6
    k.box(ix0, iy0, 0, ix1, iy1, 0.86, "brick")                          # masonry hearth
    k.box(ix0 - 0.05, iy0 - 0.05, 0.86, ix1 + 0.05, wy0, 0.92, "stone")
    k.box(ix0 - 0.05, wy1, 0.86, ix1 + 0.05, iy1 + 0.05, 0.92, "stone")
    k.box(ix0 - 0.05, wy0, 0.86, wx0, wy1, 0.92, "stone")
    k.box(wx1, wy0, 0.86, ix1 + 0.05, wy1, 0.92, "stone")
    k.box(wx0, wy0, 0.70, wx1, wy1, 0.86, "iron")                        # charcoal well
    k.box(wx0 + 0.03, wy0 + 0.03, 0.86, wx1 - 0.03, wy1 - 0.03, 0.875, "embers")
    for i in range(12):
        y = wy0 + 0.06 + i * (wy1 - wy0 - 0.12) / 11
        k.box(wx0, y - 0.006, 0.90, wx1, y + 0.006, 0.912, "iron")        # grate
    k.box(2.0, 3.7, 2.3, 3.6, 5.9, H, "plaster")                         # plastered hood
    k.box(1.98, 3.68, 2.3, 3.62, 5.92, 2.37, "oak")                      # oak mantel rail
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
    potted_tree(k, 8.9, 7.9, 2.2, rnd)
    k.build("Props_Culinary", col)

    # --- Lounge: hearth, mantel, chesterfields, rug, olive tree
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
    potted_tree(lg, 17.7, 1.1, 2.4, rnd)
    potted_tree(lg, 9.98, 0.8, 1.9, rnd, pot_r=0.3)
    lg.build("Props_Lounge", col)

    # --- Mudroom: recessed coir mat, linear drain, boot bench, wetsuit rail
    md = MB()
    md.box(20.0, YI0, 0, 22.0, 1.55, 0.001, "coir")
    md.box(20.0, 1.6, 0, 22.0, 1.7, 0.002, "brass")
    md.box(XI1 - 0.5, 1.8, 0.40, XI1, 7.2, 0.46, "oak")
    for y in (2.0, 4.5, 7.0):
        md.box(XI1 - 0.45, y - 0.04, 0, XI1 - 0.05, y + 0.04, 0.40, "oak")
    md.box(20.8, YS0 - 0.1, 1.75, 22.5, YS0 - 0.07, 1.78, "iron")
    for x in (20.8, 22.47):
        md.box(x, YS0 - 0.1, 1.75, x + 0.03, YS0, 1.78, "iron")
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
    for x in (2.4, 6.2, 10.0):                                       # window-seat cushions
        lb.box(x - 0.75, YI1 - 0.06 - 0.04, 0.5, x + 0.75, YI1 + 0.18, 0.58, "linen")
    potted_tree(lb, 1.0, 15.0, 2.0, rnd)
    lb.build("Props_Library", col)

    # --- Endurance: four smart-trainer bays behind the glass, ~29 m2 tatami
    en = MB()
    for y in (10.2, 11.5, 12.8, 14.1):
        en.box(13.1, y - 0.45, 0, 15.1, y + 0.45, 0.006, "rubber")
        en.box(13.35, y - 0.24, 0.006, 13.95, y + 0.24, 0.42, "trainer")   # direct-drive unit
        en.box(13.55, y - 0.03, 0.30, 14.85, y + 0.03, 0.36, "iron")       # frame (simplified)
        en.box(13.6, y - 0.03, 0.36, 13.66, y + 0.03, 0.95, "iron")
        en.box(13.5, y - 0.07, 0.95, 13.78, y + 0.07, 1.0, "rubber")
        en.box(14.75, y - 0.03, 0.36, 14.81, y + 0.03, 1.02, "iron")
        en.box(14.72, y - 0.22, 1.0, 14.84, y + 0.22, 1.04, "rubber")
        en.box(14.65, y - 0.12, 0.006, 14.95, y + 0.12, 0.10, "trainer")
    en.box(15.4, 9.65, 0, 20.8, 15.05, 0.04, "bjj")
    potted_tree(en, 13.4, 9.3, 2.0, rnd)
    en.build("Props_Endurance", col)

    # --- Wet core: bluestone shower fins and a changing bench
    wc = MB()
    for y in (12.4, 13.5, 14.6):
        wc.box(XI1 - 1.05, y - 0.04, 0, XI1, y + 0.04, 1.85, "stone")
    wc.box(X_END_WET + HT, 11.0, 0.40, X_END_WET + HT + 0.4, 15.2, 0.46, "oak")
    wc.build("Props_WetCore", col)


def build_veranda(col):
    """The coast-side room without walls: oak posts on the facade piers, a
    lean-to pantile roof on rafters that continue the indoor joist grid, an
    open vine pergola over the outdoor kitchen, and terracotta running
    straight through from the culinary core."""
    VD = VERANDA_DEPTH
    rng = random.Random(55)
    mb = MB()
    mb.box(-0.3, -VD, -FINISH_T, PLATE_X + 0.3, 0.0, 0.0, "terracotta")
    mb.box(-0.4, -VD - 0.25, -0.35, PLATE_X + 0.4, -VD, 0.0, "brick")      # brick kerb
    mb.box(-0.4, -VD - 0.08, -0.35, PLATE_X + 0.4, -0.0, -FINISH_T, "brick")
    py = -VD + 0.2
    for x in VERANDA_POSTS:
        mb.box(x - 0.16, py - 0.16, 0, x + 0.16, py + 0.16, 0.06, "stone")   # stone post pads
        mb.box(x - 0.11, py - 0.11, 0.06, x + 0.11, py + 0.11, VERANDA_EAVE, "oak_weathered")
        mb.beam((x, py, VERANDA_EAVE - 0.6), (x, py + 0.45, VERANDA_EAVE), 0.08, 0.08, "oak_weathered")
    plate_top = VERANDA_EAVE + 0.22
    mb.box(-0.3, py - 0.12, VERANDA_EAVE, PLATE_X + 0.3, py + 0.12, plate_top, "oak_weathered")
    mb.box(-0.3, -SKIN_T - 0.12, VERANDA_SEAT - 0.25, PLATE_X + 0.3, -SKIN_T, VERANDA_SEAT, "oak_weathered")

    slope = (VERANDA_SEAT - plate_top) / (VD - 0.2)
    y_end = -VD - 0.45
    z_end = VERANDA_SEAT - slope * (VD + 0.45)
    for x in joist_xs(-0.3, PLATE_X + 0.3, margin=0.05):
        mb.beam((x, -SKIN_T, VERANDA_SEAT - 0.09), (x, y_end, z_end - 0.09), 0.1, 0.18, "oak_weathered")
    roof_x0 = PERGOLA_TO_X
    xm, wx = (roof_x0 + PLATE_X + 0.3) / 2, PLATE_X + 0.3 - roof_x0
    mb.beam((xm, -SKIN_T, VERANDA_SEAT + 0.012), (xm, y_end, z_end + 0.012), wx, 0.025, "boards")
    mb.beam((xm, -SKIN_T, VERANDA_SEAT + 0.07), (xm, y_end - 0.05, z_end + 0.06), wx, 0.07, "pantile")
    mb.build("Veranda_Structure", col)

    vine = MB()
    px_m, pw = (-0.3 + PERGOLA_TO_X) / 2, PERGOLA_TO_X + 0.3
    vine.beam((px_m, -SKIN_T, VERANDA_SEAT + 0.03), (px_m, y_end, z_end + 0.03), pw, 0.006, "vine")
    for _ in range(14):                                  # trailing tendrils over the front plate
        x = rng.uniform(0.0, PERGOLA_TO_X)
        vine.blob((x, py + rng.uniform(-0.2, 0.2), VERANDA_EAVE + 0.1), rng.uniform(0.25, 0.45),
                  "foliage", scale=(1.3, 0.8, 1.2), rng=rng)
    for x in (0.2, 5.0):                                 # vine trunks climbing two posts
        vine.beam((x + 0.14, py, 0.06), (x + 0.1, py + 0.05, VERANDA_EAVE + 0.1), 0.05, 0.05, "bark")
    vine.build("Veranda_Vine_Pergola", col)

    # Outdoor kitchen and living under the veranda
    out = MB()
    out.box(0.35, -3.25, 0, 1.65, -1.95, 0.9, "brick")                    # wood-fired oven base
    out.blob((1.0, -2.6, 1.0), 0.62, "plaster", scale=(1.0, 1.0, 0.65), rough=0.03)
    out.box(0.75, -3.0, 1.2, 1.25, -2.85, 1.35, "firebox")
    out.box(0.9, -2.75, 1.3, 1.1, -2.55, 2.4, "iron")                      # flue
    out.box(2.6, -2.35, 0.7, 7.8, -1.35, 0.78, "oak_weathered")            # long outdoor table
    for x in (3.0, 5.2, 7.4):
        out.box(x - 0.06, -2.25, 0, x + 0.06, -1.45, 0.7, "oak_weathered")
    out.box(2.8, -2.95, 0.42, 7.6, -2.65, 0.46, "oak_weathered")           # benches
    out.box(2.8, -1.05, 0.42, 7.6, -0.75, 0.46, "oak_weathered")
    for bx in (10.7, 15.4):                                                # daybeds facing the sea
        out.box(bx, -2.9, 0, bx + 2.0, -1.95, 0.38, "oak_weathered")
        out.box(bx + 0.05, -2.85, 0.38, bx + 1.95, -2.0, 0.5, "linen")
        out.box(bx + 0.05, -2.05, 0.38, bx + 1.95, -1.9, 0.85, "linen")
    out.box(19.0, -1.2, 0.42, 20.2, -0.75, 0.46, "oak_weathered")          # porch bench
    out.box(24.0, -3.3, 0, 24.9, -2.4, 0.04, "deck")                       # outdoor shower
    out.box(24.82, -3.3, 0, 24.92, -3.2, 2.3, "oak_weathered")
    out.box(24.4, -3.3, 2.2, 24.85, -3.24, 2.24, "brass")
    out.box(24.33, -3.36, 2.12, 24.47, -3.18, 2.2, "brass")
    for i in range(3):                                                     # board rack
        x = 23.2 + i * 0.25
        out.blob((x, -0.25, 1.15), 1.0, "linen", scale=(0.05, 0.26, 1.0), rough=0.0, subdiv=2)
    potted_tree(out, 9.0, -2.9, 1.8, rng)
    out.build("Veranda_Living", col)


def build_upper(col):
    """Placeholder massing so the exterior reads as a brick dune house under
    a steep pantile roof, not as a flat-roofed box.  Not designed."""
    z0 = H + SLAB_T
    z1 = z0 + UPPER_FLOORS * UPPER_H
    win = {"S": (3.0, 7.0, 11.5, 14.0, 16.5, 21.0, 23.4), "N": (2.4, 6.2, 10.0, 15.2, 19.2, 23.1),
           "W": (4.4, 12.0), "E": (4.4, 12.0)}
    mb = MB()
    for key, xs in win.items():
        w = WALLS[key]
        f0, f1 = sorted((outer_face(w) + w["outer"] * SKIN_T, inner_face(w)))
        a0, a1 = (-SKIN_T, PLATE_X + SKIN_T) if w["axis"] == "x" else (0.0, PLATE_Y)
        for fl in range(UPPER_FLOORS):
            zb = z0 + fl * UPPER_H
            ops = [(x - 0.65, x + 0.65, 0.85, 2.45) for x in xs]
            for p0, p1, za, zc in solid_pieces(a0, a1, UPPER_H, ops):
                abox(mb, w["axis"], f0, f1, p0, p1, zb + za, zb + zc, "brick")
            p = frame_plane(w)
            for x in xs:
                glazed_grid(mb, w["axis"], p, x - 0.65, x + 0.65, zb + 0.85, zb + 2.45,
                            cols=2, rows=3, frame=0.07, bar=0.03, depth=0.07, mat="oak")
                q0, q1 = sorted((p - w["outer"] * 0.05, inner_face(w)))
                abox(mb, w["axis"], q0, q1, x - 0.65, x + 0.65, zb + 0.85, zb + 2.45, "firebox")
    mb.box(0, 0, z1, PLATE_X, PLATE_Y, z1 + 0.25, "slab")

    eave = z1 + 0.25
    rise = (PLATE_Y / 2 + 0.45) * math.tan(math.radians(ROOF_PITCH_DEG))
    ridge = eave + rise
    yr = PLATE_Y / 2
    for ys in (-0.45 - SKIN_T, PLATE_Y + 0.45 + SKIN_T):
        mb.beam((PLATE_X / 2, ys, eave), (PLATE_X / 2, yr, ridge), PLATE_X + 0.6, 0.12, "pantile")
    for gx, off in ((-SKIN_T, EXT_T + SKIN_T), (PLATE_X + SKIN_T, -(EXT_T + SKIN_T))):
        mb.prism([(gx, -SKIN_T, z1), (gx, PLATE_Y + SKIN_T, z1), (gx, yr, ridge - 0.1)], (off, 0, 0), "brick")
    mb.box(CHIMNEY_X - 0.7, YS0 - 0.6, z1, CHIMNEY_X + 0.7, YS0 + 0.3, ridge + 1.0, "brick")
    mb.box(CHIMNEY_X - 0.8, YS0 - 0.7, ridge + 1.0, CHIMNEY_X + 0.8, YS0 + 0.4, ridge + 1.12, "brick")
    mb.build("Upper_Massing_Placeholder", col)


# -----------------------------------------------------------------------------
# Scatter helpers
# -----------------------------------------------------------------------------
def rect_minus(rect, holes):
    """Axis-aligned rectangles covering `rect` minus the `holes`."""
    x0, y0, x1, y1 = rect
    xs = sorted({x0, x1} | {h[0] for h in holes if x0 < h[0] < x1} | {h[2] for h in holes if x0 < h[2] < x1})
    out = []
    for a, b in zip(xs, xs[1:]):
        cuts = sorted((max(y0, h[1]), min(y1, h[3])) for h in holes
                      if h[0] < b and h[2] > a and h[1] < y1 and h[3] > y0)
        cur = y0
        for c0, c1 in cuts:
            if c0 > cur:
                out.append((a, cur, b, c0))
            cur = max(cur, c1)
        if cur < y1:
            out.append((a, cur, b, y1))
    return [r for r in out if r[2] - r[0] > 0.05 and r[3] - r[1] > 0.05]


def plane_object(name, rects, z, col):
    """Flat emitter made of quads (for hair and scatter; not rendered itself)."""
    bm = bmesh.new()
    for x0, y0, x1, y1 in rects:
        bm.faces.new([bm.verts.new(p) for p in ((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z))])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    return ob


def add_hair(ob, name, mat_key, count, length, children=20, child_radius=0.05, radius=0.004,
             tip=0.05, lean=0.12, seed=1, vgroup=None, show_emitter=False, rough_end=0.1):
    """Hair-particle grass/reeds: `count` guides, each a tuft of `children` blades."""
    if MAT[mat_key].name not in [m.name for m in ob.data.materials if m]:
        ob.data.materials.append(MAT[mat_key])
    slot = [m.name for m in ob.data.materials].index(MAT[mat_key].name) + 1
    mod = ob.modifiers.new(name, "PARTICLE_SYSTEM")
    ps = mod.particle_system
    ps.seed = seed
    if vgroup:
        ps.vertex_group_density = vgroup
    st = ps.settings
    st.name = name
    st.type = "HAIR"
    st.count = count
    st.hair_length = length
    st.emit_from = "FACE"
    st.use_emit_random = True
    st.factor_random = lean
    ob.show_instancer_for_render = show_emitter      # hide the emitter plane, keep the hair
    st.child_type = "SIMPLE" if children else "NONE"
    for attr, val in (("child_percent", max(1, children // 5)), ("rendered_child_count", children),
                      ("child_radius", child_radius), ("child_length", 1.0), ("child_length_threshold", 0.35),
                      ("display_percentage", 15), ("clump_factor", -0.5), ("clump_shape", 0.4),
                      ("roughness_1", 0.04), ("roughness_endpoint", rough_end), ("roughness_end_shape", 1.5),
                      ("radius_scale", radius), ("root_radius", 1.0), ("tip_radius", tip)):
        if hasattr(st, attr):
            setattr(st, attr, val)
    try:
        st.material_slot = MAT[mat_key].name
    except TypeError:
        st.material = slot          # the enum fills only after a depsgraph update
    return st


def gn_scatter(ob, name, instance, density, scale=(0.8, 1.2), seed=0, tilt=0.08):
    """Geometry Nodes scatter of an object or a collection (pick per point)
    over `ob`'s faces.  The emitter itself is not kept."""
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n, link = ng.nodes, ng.links.new
    gi, go = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    dist = n.new("GeometryNodeDistributePointsOnFaces")
    dist.inputs["Density"].default_value = density
    dist.inputs["Seed"].default_value = seed
    link(gi.outputs[0], dist.inputs["Mesh"])
    iop = n.new("GeometryNodeInstanceOnPoints")
    link(dist.outputs["Points"], iop.inputs["Points"])
    if isinstance(instance, bpy.types.Collection):
        info = n.new("GeometryNodeCollectionInfo")
        info.inputs["Collection"].default_value = instance
        info.inputs["Separate Children"].default_value = True
        info.inputs["Reset Children"].default_value = True
        link(info.outputs[0], iop.inputs["Instance"])
        iop.inputs["Pick Instance"].default_value = True
        pick = n.new("FunctionNodeRandomValue")
        pick.data_type = "INT"
        pick.inputs[4].default_value, pick.inputs[5].default_value = 0, 99
        pick.inputs[8].default_value = seed + 7
        link(pick.outputs[2], iop.inputs["Instance Index"])
    else:
        info = n.new("GeometryNodeObjectInfo")
        info.inputs["Object"].default_value = instance
        info.inputs["As Instance"].default_value = True
        link(info.outputs["Geometry"], iop.inputs["Instance"])
    rot = n.new("FunctionNodeRandomValue")
    rot.data_type = "FLOAT_VECTOR"
    rot.inputs[0].default_value = (-tilt, -tilt, 0.0)
    rot.inputs[1].default_value = (tilt, tilt, 2 * math.pi)
    rot.inputs[8].default_value = seed + 1
    link(rot.outputs[0], iop.inputs["Rotation"])
    sc = n.new("FunctionNodeRandomValue")
    sc.data_type = "FLOAT"
    sc.inputs[2].default_value, sc.inputs[3].default_value = scale
    sc.inputs[8].default_value = seed + 2
    link(sc.outputs[1], iop.inputs["Scale"])
    link(iop.outputs[0], go.inputs[0])
    mod = ob.modifiers.new(name, "NODES")
    mod.node_group = ng
    return mod


def place_instance(src, loc, rot_z, scale, col, name):
    """Instance a proxy object (linked duplicate) or a scanned-asset Collection."""
    if isinstance(src, bpy.types.Collection):
        ob = bpy.data.objects.new(name, None)
        ob.instance_type = "COLLECTION"
        ob.instance_collection = src
    else:
        ob = bpy.data.objects.new(name, src.data)
    ob.location = loc
    ob.rotation_euler[2] = rot_z
    ob.scale = (scale, scale, scale)
    col.objects.link(ob)
    return ob


def source_object(name, mb, col):
    """Build a hidden instance source, parked out of shot."""
    ob = mb.build(name, col)
    ob.location = (0.0, 0.0, -200.0)
    ob.hide_render = True
    try:
        ob.hide_set(True)
    except RuntimeError:
        pass
    return ob


def boardwalk(mb, a, b, z_start=None, z_end=None, width=1.4):
    """Silvered oak planks across a straight route, riding 0.25 m over the
    ground on posts and easing to the given levels at either end."""
    a, b = Vector((a[0], a[1], 0.0)), Vector((b[0], b[1], 0.0))
    d = b - a
    length = d.length
    u = d / length
    side = Vector((-u.y, u.x, 0.0)) * (width / 2)
    n = max(1, int(length / 0.152))

    def deck_z(s):
        p = a + u * s
        z = max(terrain_z(p.x, p.y), SEA_LEVEL + 0.2) + 0.25
        if z_start is not None:
            w = 1.0 - smooth(0.0, 3.0, s)
            z += (z_start - z) * w
        if z_end is not None:
            w = 1.0 - smooth(0.0, 3.0, length - s)
            z += (z_end - z) * w
        return z

    for i in range(n):
        s = (i + 0.5) * length / n
        p = a + u * s
        z = deck_z(s)
        mb.beam(p - side + Vector((0, 0, z - 0.02)), p + side + Vector((0, 0, z - 0.02)), 0.14, 0.04, "deck")
    s = 1.2
    while s < length - 1.0:
        p = a + u * s
        z = deck_z(s) - 0.04
        g = terrain_z(p.x, p.y) - 0.4
        for sgn in (-1, 1):
            q = p + side * sgn * 0.93
            mb.box(q.x - 0.05, q.y - 0.05, g, q.x + 0.05, q.y + 0.05, z, "oak_weathered")
        s += 2.4


# -----------------------------------------------------------------------------
# Garden: terraces, pond, meadow, bulbs
# -----------------------------------------------------------------------------
def terrace_bands():
    """(north y, south y, level) for each formal terrace, house terrace first."""
    edges = [-VERANDA_DEPTH - 0.25] + [e for e, _ in TERRACE_STEPS] + [TERRACE_END]
    levels = [-0.05] + [lv for _, lv in TERRACE_STEPS]
    return [(edges[i], edges[i + 1], levels[i]) for i in range(len(levels))]


def build_garden(col):
    tx0, tx1 = TERRACE_X
    path = (BOARDWALK_X - 0.8, BOARDWALK_X + 0.8)
    bands = terrace_bands()
    mb = MB()
    for yn, ys, lv in bands:
        mb.box(tx0, ys, lv - 0.6, tx1, yn, lv - 0.02, "soil")
        mb.box(path[0], ys, lv - 0.02, path[1], yn, lv + 0.01, "shell")       # shell path to the beach
    walls = [(bands[i][1], bands[i][2], bands[i + 1][2]) for i in range(len(bands) - 1)]
    walls.append((TERRACE_END, bands[-1][2], TERRACE_FOOT))
    for e, up, lo in walls:
        for a, b in along_gaps(tx0, tx1, [path]):
            mb.box(a, e - 0.45, lo - 0.6, b, e, up + 0.1, "brick")              # retaining wall
            mb.box(a, e - 0.5, up + 0.1, b, e + 0.05, up + 0.16, "stone")       # bluestone coping
        n = max(2, round((up - lo) / 0.18))
        rise = (up - lo) / n
        for k in range(n):                                                     # steps down to the next level
            mb.box(path[0], e - (k + 1) * 0.32, lo - 0.3, path[1], e - k * 0.32, up - (k + 1) * rise + 0.02, "stone")
        for x in (path[0] - 0.3, path[1]):                                      # stair cheeks
            mb.box(x, e - n * 0.32, lo - 0.3, x + 0.3, e, up + 0.1, "brick")
    mb.build("Garden_Terraces", col)

    build_pond(col)

    # House terrace lawn around the pond; wildflower meadow; tulip strips at the bottom
    pond_hole = (POND[0] - 0.5, POND[1] - 0.3, REED_BED[2] + 0.5, POND[3] + 2.1)
    path_hole = (path[0], -100.0, path[1], 100.0)
    yn, ys, lv = bands[0]
    lawn = plane_object("Lawn_HouseTerrace", rect_minus((tx0, ys, tx1, yn), [pond_hole, path_hole]), lv - 0.02, col)
    if PH_MODELS.get("grass"):
        gn_scatter(lawn, "Lawn_Scanned_Grass", PH_MODELS["grass"][0], 8.0, scale=(0.5, 0.8), seed=3)
    else:
        add_hair(lawn, "Lawn_Hair", "lawn", 30000, 0.09, children=16, child_radius=0.03, radius=0.0015, seed=3)

    if len(bands) > 1:
        yn, ys, lv = bands[1]
        meadow = plane_object("Meadow_Terrace", rect_minus((tx0, ys + 0.1, tx1, yn - 0.5), [path_hole]), lv - 0.02, col)
        add_hair(meadow, "Meadow_Hair", "meadow", 9000, 0.38, children=18, child_radius=0.06, radius=0.002, seed=4)
        flower = MB()
        flower.beam((0, 0, 0), (0.01, 0.0, 0.42), 0.004, 0.004, "stem")
        flower.blob((0.01, 0.0, 0.44), 0.025, "wildflower", scale=(1.0, 1.0, 0.45), rough=0.0, subdiv=1)
        src = source_object("Proxy_Wildflower", flower, col)
        gn_scatter(meadow, "Meadow_Flowers", src, 5.0, scale=(0.7, 1.25), seed=5, tilt=0.15)

    yn, ys, lv = bands[-1]
    tulips = []
    for i, _c in enumerate(BULB_COLOURS):
        t = MB()
        t.beam((0, 0, 0), (0, 0, 0.36), 0.006, 0.006, "stem")
        t.beam((0, 0, 0.02), (0.06, 0.02, 0.2), 0.035, 0.003, "stem")
        t.beam((0, 0, 0.02), (-0.05, -0.03, 0.18), 0.035, 0.003, "stem")
        t.blob((0, 0, 0.4), 0.03, f"tulip{i}", scale=(1.0, 1.0, 1.45), rough=0.05, subdiv=2)
        tulips.append(source_object(f"Proxy_Tulip_{i}", t, col))
    y = yn - 0.6
    k = 0
    while y - 0.8 > ys + 0.3:
        strip = plane_object(f"Bulb_Strip_{k}", rect_minus((tx0 + 0.5, y - 0.8, tx1 - 0.5, y), [path_hole]), lv - 0.02, col)
        gn_scatter(strip, f"Bulb_Strip_{k}_Tulips", tulips[k % len(tulips)], 55.0, scale=(0.85, 1.15), seed=10 + k)
        y -= 1.2
        k += 1


def build_pond(col):
    """Natural swimming pond on the house terrace.  Its south edge is an
    overflow lip on the retaining wall, so from the veranda the water runs
    straight into the meadow, the dunes and the sea."""
    x0, y0, x1, y1 = POND
    rx = REED_BED[2]
    top, wl, C = -0.05, -0.17, 0.45
    mb = MB()
    mb.box(x0 - C, y1, top - 0.2, rx + C, y1 + C, top + 0.04, "stone")            # bluestone coping
    mb.box(x0 - C, y0, top - 0.2, x0, y1, top + 0.04, "stone")
    mb.box(rx, y0, top - 0.2, rx + C, y1, top + 0.04, "stone")
    mb.box(x0 - C, y0 - 0.25, -1.7, rx + C, y0, wl - 0.012, "stone")              # overflow lip
    mb.box(x0 - C, y0 - 0.25, -1.75, rx + C, y1 + C, -1.6, "stone")               # basin floor
    for bx0, bx1 in ((x0 - 0.15, x0), (rx, rx + 0.15)):
        mb.box(bx0, y0, -1.6, bx1, y1, top - 0.2, "stone")
    mb.box(x0, y1, -1.6, rx, y1 + 0.15, top - 0.2, "stone")
    mb.box(x1 - 0.1, y0, -1.6, x1 + 0.1, y1, wl - 0.15, "stone")                  # submerged divider
    mb.box(x1 + 0.1, y0, -1.6, rx, y1, -0.6, "shell")                             # gravel of the reed bed
    for i in range(4):                                                            # steps down into the swim zone
        mb.box(x0 + 0.2, y1 - 0.35 * (i + 1), -1.6, x0 + 1.6, y1 - 0.35 * i, top - 0.3 - 0.3 * i, "stone")
    mb.box(x0 - C, y1 + C, top - 0.06, rx + C, y1 + C + 1.6, top + 0.02, "deck")  # sun deck
    for x in (5.0, 7.2, 11.6, 13.8):                                              # loungers
        mb.box(x, y1 + C + 0.25, top + 0.02, x + 0.7, y1 + C + 1.35, top + 0.32, "oak_weathered")
        mb.box(x + 0.03, y1 + C + 0.28, top + 0.32, x + 0.67, y1 + C + 1.32, top + 0.4, "linen")
    mb.build("Pond_Basin", col)
    water = MB()
    water.box(x0, y0 - 0.25, -1.6, rx, y1, wl, "pool_water")
    water.build("Pond_Water", col)
    reeds = plane_object("Reed_Bed", [(x1 + 0.15, y0 + 0.1, rx - 0.1, y1 - 0.1)], -0.6, col)
    add_hair(reeds, "Reeds", "reed", 900, 1.7, children=14, child_radius=0.1, radius=0.005, tip=0.2,
             lean=0.05, seed=8, rough_end=0.05)


# -----------------------------------------------------------------------------
# Garden pavilions: brick room, open-air living veranda, reed-thatched roof
# -----------------------------------------------------------------------------
def build_pavilion_parts(col):
    """One pavilion in local space (front faces -Y).  Returns its objects."""
    fl = 0.3                  # floor on a brick plinth
    eave = fl + 2.5
    s = MB()
    s.box(-4.4, -3.4, -0.5, 4.4, 5.4, fl - 0.03, "brick")
    s.box(-3.5, 0.0, fl - 0.03, 3.5, 5.0, fl, "oak_floor")
    s.box(-4.4, -3.4, fl - 0.03, 4.4, 0.0, fl, "terracotta")
    s.box(-1.2, -3.72, -0.5, 1.2, -3.4, 0.15, "stone")                            # step
    for p0, p1, z0, z1 in solid_pieces(-3.5, 3.5, 2.5, [(-1.6, 1.6, 0.0, 2.25)]):
        s.box(p0, 0.0, fl + z0, p1, 0.3, fl + z1, "brick")                        # front, wide opening
    s.box(-3.5, 4.7, fl, 3.5, 5.0, eave, "brick")                                 # back
    for x0, x1 in ((-3.5, -3.2), (3.2, 3.5)):
        for p0, p1, z0, z1 in solid_pieces(0.3, 4.7, 2.5, [(1.8, 3.0, 0.9, 2.2)]):
            s.box(x0, p0, fl + z0, x1, p1, fl + z1, "brick")
        glazed_grid(s, "y", (x0 + x1) / 2, 1.8, 3.0, fl + 0.9, fl + 2.2, cols=2, rows=3,
                    frame=0.06, bar=0.028, depth=0.06, mat="oak")
    s.box(-3.2, 4.68, fl, 3.2, 4.7, eave, "plaster")
    s.box(-1.6, 0.0, fl + 2.2, 1.6, 0.3, fl + 2.25, "oak")                        # oak lintel
    for side in (-1, 1):                                                           # glazed doors folded back
        a0, a1 = sorted((side * 1.6, side * 3.13))
        glazed_grid(s, "x", -0.045, a0, a1, fl + 0.01, fl + 2.18, cols=2, rows=4,
                    frame=0.08, bar=0.028, depth=0.05, mat="oak")
    for x in (-4.1, 4.1):
        s.box(x - 0.1, -3.2, fl, x + 0.1, -3.0, eave, "oak_weathered")            # veranda posts
    s.box(-4.3, -3.22, eave - 0.2, 4.3, -2.98, eave, "oak_weathered")             # plate
    for x in (-4.1, 4.1):
        s.box(x - 0.08, -3.0, eave - 0.18, x + 0.08, 0.0, eave, "oak_weathered")  # tie beams
    struct = s.build("Pavilion_Structure", col)

    r = MB()
    ex0, ex1, ey0, ey1 = -4.9, 4.9, -3.95, 5.95
    rise = (ex1 - ex0) / 2 * math.tan(math.radians(52.0))
    yc = (ey0 + ey1) / 2
    half_ridge = max(0.05, ((ey1 - ey0) - (ex1 - ex0)) / 2)
    verts = [(ex0, ey0, eave), (ex1, ey0, eave), (ex1, ey1, eave), (ex0, ey1, eave),
             (0.0, yc - half_ridge, eave + rise), (0.0, yc + half_ridge, eave + rise)]
    faces = [(0, 3, 2, 1), (0, 1, 4), (1, 2, 5, 4), (2, 3, 5), (3, 0, 4, 5)]
    r.hull(verts, faces, ["boards", "thatch", "thatch", "thatch", "thatch"])
    for b in ((ex0 - 0.15, ey0 - 0.2, ex1 + 0.15, ey0 + 0.15),                    # chunky thatch eave roll
              (ex0 - 0.15, ey1 - 0.15, ex1 + 0.15, ey1 + 0.2),
              (ex0 - 0.2, ey0 - 0.2, ex0 + 0.15, ey1 + 0.2),
              (ex1 - 0.15, ey0 - 0.2, ex1 + 0.2, ey1 + 0.2)):
        r.box(b[0], b[1], eave - 0.28, b[2], b[3], eave + 0.12, "thatch")
    r.box(-0.25, yc - half_ridge - 0.3, eave + rise - 0.35, 0.25, yc + half_ridge + 0.3, eave + rise + 0.12, "thatch")
    roof = r.build("Pavilion_Roof_Thatch", col)

    f = MB()
    f.box(-1.0, 2.8, fl, 1.0, 4.65, fl + 0.45, "oak")                              # bed
    f.box(-0.97, 2.83, fl + 0.45, 0.97, 4.62, fl + 0.62, "linen")
    f.box(-1.1, 4.6, fl, 1.1, 4.68, fl + 1.3, "oak")
    f.box(-3.9, -2.9, fl, -1.8, -1.95, fl + 0.36, "oak_weathered")                # veranda daybed
    f.box(-3.85, -2.85, fl + 0.36, -1.85, -2.0, fl + 0.5, "linen")
    f.box(-3.85, -2.05, fl + 0.36, -1.85, -1.9, fl + 0.85, "linen")
    for x in (0.2, 1.2):                                                           # chairs + table
        f.box(x - 0.35, -2.4, fl, x + 0.35, -1.7, fl + 0.42, "leather")
        f.box(x - 0.35, -1.85, fl + 0.42, x + 0.35, -1.7, fl + 0.85, "leather")
    f.box(0.25, -3.1, fl, 1.15, -2.6, fl + 0.45, "oak")
    f.box(2.0, -3.1, fl, 3.9, -1.95, fl + 0.6, "stone")                           # outdoor soaking tub
    f.box(2.1, -3.0, fl + 0.3, 3.8, -2.05, fl + 0.56, "pool_water")
    f.box(-0.15, -1.75, eave - 0.75, 0.15, -1.45, eave - 0.45, "iron")            # lantern
    f.box(-0.01, -1.61, eave - 0.45, 0.01, -1.59, eave, "iron")
    furn = f.build("Pavilion_Furnishing", col)
    return [struct, roof, furn]


def build_pavilions(col, light_col):
    parts = build_pavilion_parts(col)
    rng = random.Random(77)
    for i, site in enumerate(PAVILIONS):
        x, y, rot = site
        holder = bpy.data.objects.new(f"Pavilion_{i}", None)
        holder.location = (x, y, pavilion_z(i))
        holder.rotation_euler[2] = math.radians(rot)
        col.objects.link(holder)
        for p in parts:
            ob = p if i == 0 else bpy.data.objects.new(f"{p.name}_{i}", p.data)
            if i:
                col.objects.link(ob)
            ob.parent = holder
        ld = bpy.data.lights.new(f"Lantern_Pavilion_{i}", "POINT")
        ld.energy, ld.color, ld.shadow_soft_size = 25, (1.0, 0.62, 0.34), 0.08
        lamp = bpy.data.objects.new(f"Lantern_Pavilion_{i}", ld)
        lamp.location = (0.0, -1.6, 2.2)
        lamp.parent = holder
        light_col.objects.link(lamp)
        px, py = pavilion_point(site, 3.9, -3.0)
        pot = MB()
        potted_tree(pot, px, py, 1.8, rng, z0=pavilion_z(i) + 0.3)
        pot.build(f"Potted_Pavilion_{i}", col)


def build_paths(col):
    bw = MB()
    for a, b, i in path_segments():
        if i is None:
            boardwalk(bw, a, b, z_start=TERRACE_FOOT + 0.03)
        else:
            boardwalk(bw, a, b, z_start=0.0, z_end=pavilion_z(i) + 0.03)
    bw.build("Boardwalks", col)


def build_landscape(col):
    """Dunes either side and behind, terraces and a foredune in front, the sea
    below; marram grass on the dunes; buckthorn, black pines and oaks planted
    densely around the pavilions; a sand training yard behind the gym."""
    rng = random.Random(LANDSCAPE_SEED)
    X0, X1, Y0, Y1 = -60.0, 85.0, -70.0, 75.0
    NX, NY = int(X1 - X0), int(Y1 - Y0)          # 1 m grid: terrace walls land on grid lines
    bm = bmesh.new()
    verts, weights = [], []
    patch_off = Vector((5.3, 9.1, 0.0))
    pav_centres = [pavilion_point(s, 0.0, 1.0) for s in PAVILIONS]
    for j in range(NY + 1):
        y = Y0 + (Y1 - Y0) * j / NY
        for i in range(NX + 1):
            x = X0 + (X1 - X0) * i / NX
            z = terrain_z(x, y)
            verts.append(bm.verts.new((x, y, z)))
            patch = 0.5 + 0.5 * mnoise.noise(Vector((x * 0.12, y * 0.12, 0.0)) + patch_off)
            w = smooth(SEA_LEVEL + 0.4, SEA_LEVEL + 1.2, z) * smooth(1.5, 5.0, pad_distance(x, y))
            w *= (0.35 + 0.65 * patch) * (1.0 - terrace_weight(x, y))
            for cx, cy in pav_centres:
                w *= smooth(7.0, 9.0, math.hypot(x - cx, y - cy))
            if w > 0.01 and near_path(x, y, 1.2):
                w = 0.0
            weights.append(w)
    for j in range(NY):
        for i in range(NX):
            a = j * (NX + 1) + i
            bm.faces.new((verts[a], verts[a + 1], verts[a + NX + 2], verts[a + NX + 1])).smooth = True
    me = bpy.data.meshes.new("Terrain_Dunes")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MAT["sand"])
    terr = bpy.data.objects.new("Terrain_Dunes", me)
    col.objects.link(terr)
    vg = terr.vertex_groups.new(name="marram")
    for idx, w in enumerate(weights):
        if w > 0.01:
            vg.add([idx], w, "REPLACE")
    add_hair(terr, "Marram_Grass", "grass", GRASS_COUNT, 0.6, children=30, child_radius=0.09, radius=0.004,
             seed=LANDSCAPE_SEED, vgroup="marram", show_emitter=True)

    sea = MB()
    sea.box(-2000, -2000, SEA_LEVEL - 0.5, 2000, 2000, SEA_LEVEL, "sea")
    sea.build("Sea_North", col)

    # Training yard behind the endurance room: sand, oak pull-up rig, logs
    yd = MB()
    yd.box(12.9, PLATE_Y + SKIN_T, -0.05, 21.3, PLATE_Y + 6.0, -0.02, "sand")
    for x in (15.0, 17.6):
        yd.box(x - 0.08, 19.4, -0.05, x + 0.08, 19.56, 2.45, "oak_weathered")
    yd.box(15.0, 19.46, 2.3, 17.6, 19.5, 2.34, "iron")
    for i in range(3):
        yd.beam((18.6, 17.5 + i * 0.45, 0.12), (20.6, 17.6 + i * 0.45, 0.12), 0.24, 0.24, "bark")
    yd.build("Training_Yard", col)

    # Vegetation sources: scanned Poly Haven assets when available, proxies otherwise
    def proxy_shrub():
        mb = MB()
        for _ in range(7):
            mb.blob((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), rng.uniform(0.35, 0.8)),
                    rng.uniform(0.35, 0.6), "buckthorn", scale=(1.2, 1.0, 0.8), rough=0.3, rng=rng, subdiv=3)
        return source_object("Proxy_SeaBuckthorn", mb, col)

    def proxy_pine():
        mb = MB()
        lean = Vector((0.9, 0.6, 0))          # bent away from the south-west wind
        pts = [lean * (t * t) + Vector((0, 0, 6.5 * t)) for t in (0.0, 0.35, 0.65, 1.0)]
        for a, b in zip(pts, pts[1:]):
            mb.beam(a, b, 0.28, 0.28, "bark")
        for _ in range(9):
            t = rng.uniform(0.62, 1.0)
            c = lean * (t * t) * 1.3 + Vector((rng.uniform(-1.4, 1.6), rng.uniform(-1.2, 1.3), 6.5 * t))
            mb.blob(c, rng.uniform(0.7, 1.2), "foliage", scale=(1.4, 1.2, 0.7), rough=0.3, rng=rng, subdiv=3)
        return source_object("Proxy_BlackPine", mb, col)

    def proxy_oak():
        mb = MB()
        mb.beam((0, 0, 0), (0.3, 0.1, 3.2), 0.4, 0.4, "bark")
        for d in ((1.6, 0.5, 5.0), (-1.2, 0.8, 4.8), (0.4, -1.3, 5.2)):
            mb.beam((0.3, 0.1, 3.0), d, 0.2, 0.2, "bark")
        for _ in range(14):
            mb.blob((rng.uniform(-2.6, 2.8), rng.uniform(-2.4, 2.6), rng.uniform(4.2, 7.0)),
                    rng.uniform(1.0, 1.6), "foliage", scale=(1.2, 1.2, 0.9), rough=0.3, rng=rng, subdiv=3)
        return source_object("Proxy_Oak", mb, col)

    shrubs = PH_MODELS.get("shrub") or [proxy_shrub()]
    pines = PH_MODELS.get("pine") or [proxy_pine()]
    trees = PH_MODELS.get("tree") or [proxy_oak()]
    ferns = PH_MODELS.get("fern") or shrubs

    def clear(x, y):
        if near_path(x, y, 2.0) or pad_distance(x, y) < 3.0 or terrace_weight(x, y) > 0.2 or in_pond(x, y, 2.0):
            return False
        return all(math.hypot(x - cx, y - cy) > 7.0 for cx, cy in pav_centres)

    def plant(srcs, x, y, s_range, tag, k):
        z = terrain_z(x, y)
        if z < SEA_LEVEL + 0.8:
            return
        place_instance(rng.choice(srcs), (x, y, z - 0.08), rng.uniform(0, 2 * math.pi),
                       rng.uniform(*s_range), col, f"{tag}_{k:03d}")

    k = 0
    for _ in range(4000):                                   # dune planting across the site
        if k >= 90:
            break
        x, y = rng.uniform(X0 + 10, X1 - 10), rng.uniform(Y0 + 30, Y1 - 10)
        if clear(x, y) and terrain_z(x, y) > SEA_LEVEL + 1.5:
            plant(shrubs, x, y, (0.7, 1.6), "Shrub", k)
            k += 1
    for site_i, (cx, cy) in enumerate(pav_centres):          # embed each pavilion in planting
        rot = math.radians(PAVILIONS[site_i][2])
        for j in range(26):
            ang = rng.uniform(0, 2 * math.pi)
            local = ang - rot
            if math.sin(local) < -0.55:                       # keep the sea-facing front open
                continue
            r = rng.uniform(7.2, 11.5)
            x, y = cx + r * math.cos(ang), cy + r * math.sin(ang)
            if not near_path(x, y, 1.6):
                plant(ferns if j % 3 == 0 else shrubs, x, y, (0.8, 1.5), f"Garden{site_i}", j)
        for j in range(4):
            ang = rot + math.pi / 2 + rng.uniform(-1.1, 1.1)  # trees behind (north of) each pavilion
            r = rng.uniform(9.0, 14.0)
            x, y = cx + r * math.cos(ang), cy + r * math.sin(ang)
            if not near_path(x, y, 2.5):
                plant(trees if j % 2 else pines, x, y, (0.8, 1.2), f"Tree{site_i}", j)
    k = 0
    for _ in range(3000):                                   # pines on the back and side dunes
        if k >= 22:
            break
        x, y = rng.uniform(X0 + 10, X1 - 10), rng.uniform(PAD[1], Y1 - 10)
        if clear(x, y) and terrain_z(x, y) > 1.5 and pad_distance(x, y) > 9.0:
            plant(pines if k % 3 else trees, x, y, (0.8, 1.3), "Pine", k)
            k += 1


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
# 7. LIGHT, WORLD, CAMERAS, RENDER
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
            if o["kind"] not in ("window", "french_door"):
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
    warm, ember = (1.0, 0.62, 0.34), (1.0, 0.42, 0.14)

    def point(name, loc, watts, rgb, radius=0.04):
        ld = bpy.data.lights.new(name, "POINT")
        ld.energy, ld.color = watts, rgb
        ld.shadow_soft_size = radius
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        col.objects.link(ob)

    shades = MB()
    for i, y in enumerate((2.8, 4.5, 6.2)):                    # forged-iron pendants over the table
        point(f"Pendant_Table_{i}", (6.6, y, 1.98), 45, warm)
        shades.box(6.42, y - 0.18, 2.03, 6.78, y + 0.18, 2.22, "iron")
        shades.box(6.59, y - 0.01, 2.22, 6.61, y + 0.01, H - 0.24, "iron")
    for i, y in enumerate((11.0, 13.5)):                       # iron lanterns in the gym
        point(f"Lantern_Endurance_{i}", (17.5, y, 2.55), 60, warm, 0.08)
        shades.box(17.35, y - 0.15, 2.6, 17.65, y + 0.15, 2.85, "iron")
        shades.box(17.49, y - 0.01, 2.85, 17.51, y + 0.01, H - 0.24, "iron")
    shades.build("Pendant_Shades", col)
    point("Lamp_Library_A", (5.8, 12.25, 1.15), 12, warm)
    point("Lamp_Library_B", (7.8, 12.25, 1.15), 12, warm)
    point("Fire_Lounge", (CHIMNEY_X, YS0 - 0.25, 0.25), 60, ember, 0.15)
    point("Embers_Grill", (2.8, 4.8, 1.0), 30, ember, 0.2)
    point("Oven_Glow", (1.0, -3.1, 1.25), 25, ember, 0.15)


CAMERAS = [
    # name, location, target, lens, shift_y, exposure EV; z = None seats the camera 1.7 m above the sand
    ("CAM_01_Library_EnSuite", (0.9, 12.25, 1.40), (20.0, 12.25, 1.40), 24, 0.0, EXPOSURE),
    ("CAM_02_Mudroom_Threshold", (23.6, 3.2, 1.50), (12.0, 5.2, 1.40), 21, 0.0, EXPOSURE),
    ("CAM_03_Culinary_Hearth", (8.9, 0.9, 1.65), (2.8, 5.2, 1.10), 24, 0.0, EXPOSURE),
    ("CAM_04_Endurance_to_Library", (20.5, 12.25, 1.45), (2.0, 12.25, 1.30), 24, 0.0, EXPOSURE),
    ("CAM_05_Beach_to_House", (8.0, -34.0, None), (11.5, 0.0, None), 28, 0.25, 0.0),
    ("CAM_06_Culinary_Out_To_Sea", (7.0, 8.2, 1.55), (7.0, -20.0, 1.55), 21, 0.0, EXPOSURE - 0.5),
    ("CAM_07_Veranda_Pond_Panorama", (14.0, -2.6, 1.45), (12.0, -60.0, 1.45), 21, 0.0, 0.3),
    ("CAM_08_Garden_Pavilion", (-5.5, -7.5, None), (-13.0, 1.0, None), 28, 0.08, 0.3),
]


@bpy.app.handlers.persistent
def verdio_camera_exposure(scene, *_args):
    """Interiors need about +1.5 EV, the beach shot none: apply the active
    camera's ["exposure_ev"] whenever the camera changes or a render starts."""
    cam = scene.camera
    if cam is not None and "exposure_ev" in cam and scene.view_settings.exposure != cam["exposure_ev"]:
        scene.view_settings.exposure = cam["exposure_ev"]


def install_exposure_handler():
    for hs in (bpy.app.handlers.render_pre, bpy.app.handlers.depsgraph_update_post):
        for h in [h for h in hs if getattr(h, "__name__", "") == "verdio_camera_exposure"]:
            hs.remove(h)
        hs.append(verdio_camera_exposure)


def build_cameras(col):
    first = None
    for name, loc, target, lens, shift, ev in CAMERAS:
        loc, target = list(loc), list(target)
        ev = 0.0 if name == "CAM_00_Plan_Ortho" else ev
        if loc[2] is None:
            loc[2] = max(terrain_z(loc[0], loc[1]), SEA_LEVEL) + 1.7
            target[2] = loc[2]          # level: two-point perspective, reframe with shift
        cam = bpy.data.cameras.new(name)
        cam.lens, cam.sensor_width, cam.clip_end = lens, 36, 3000
        cam.shift_y = shift
        ob = bpy.data.objects.new(name, cam)
        ob.location = loc
        ob["exposure_ev"] = float(ev)
        aim(ob, Vector(target) - Vector(loc))
        col.objects.link(ob)
        first = first or ob
    plan = bpy.data.cameras.new("CAM_00_Plan_Ortho")
    plan.type, plan.ortho_scale, plan.clip_end = "ORTHO", 66.0, 200
    ob = bpy.data.objects.new("CAM_00_Plan_Ortho", plan)
    ob.location = (13.0, 3.0, 40.0)
    ob["exposure_ev"] = 0.0
    col.objects.link(ob)
    bpy.context.scene.camera = first


def setup_render():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    final = QUALITY == "final"
    cy.samples = 1024 if final else 128
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.005 if final else 0.02
    cy.use_denoising = True
    cy.max_bounces = 16
    cy.diffuse_bounces = 6          # dark oak rooms live on bounce light
    cy.glossy_bounces = 4
    cy.transmission_bounces = 12    # several stacked glass skins in the en suite
    cy.transparent_max_bounces = 24  # vine cut-outs and glass
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    cy.sample_clamp_indirect = 10.0
    sc.render.resolution_x, sc.render.resolution_y = 3000, 2000
    sc.render.resolution_percentage = 100 if final else 50
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
# 8. SCENE MANAGEMENT AND MAIN
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
    for ps in list(bpy.data.particles):
        if ps.users == 0:
            bpy.data.particles.remove(ps)
    for ng in list(bpy.data.node_groups):
        if ng.users == 0 and ng.bl_idname == "GeometryNodeTree":
            bpy.data.node_groups.remove(ng)


BEVEL_SKIP = ("Walls_", "Facade_", "Floor_", "Ground_", "Ceiling_Boards", "Terrain", "Sea_", "Upper_",
              "Lawn_", "Meadow_", "Bulb_", "Reed_", "Pond_Water", "Proxy_")
BEVEL_SOFT = {"Props_Lounge": (0.025, 3), "Props_Library": (0.01, 2), "Pavilion_Furnishing": (0.02, 3),
              "Veranda_Living": (0.012, 2), "Pond_Basin": (0.01, 2)}


def soften_edges(objects):
    """No real edge is perfectly sharp: a small bevel catches a highlight on
    every timber, stone and brick edge; soft furnishings get rounder."""
    for ob in objects:
        if ob.type != "MESH" or ob.name.startswith(BEVEL_SKIP) or ob.data.name.startswith("Proxy_"):
            continue
        if any(m.type in ("PARTICLE_SYSTEM", "NODES", "BEVEL") for m in ob.modifiers):
            continue
        head, _, tail = ob.name.rpartition("_")
        base = head if tail.isdigit() else ob.name
        width, segs = BEVEL_SOFT.get(base, (0.005, 2))
        m = ob.modifiers.new("Soft_Edges", "BEVEL")
        m.width, m.segments, m.limit_method, m.use_clamp_overlap = width, segs, "ANGLE", True


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
        "06_Props", "07_Veranda", "08_Garden", "09_Landscape", "10_UpperMassing",
        "11_Lighting", "12_Cameras", "13_Labels")}

    PLANT_SPOTS.clear()
    build_materials()
    load_polyhaven()
    build_structure(cols["01_Structure"])
    if BUILD_CEILING:
        build_ceiling_timber(cols["01_Structure"])
    areas = build_floors(cols["02_Floors"])
    build_ensuite(cols["03_EnSuite"])
    facade_ctrl = controller("FACADE_CONTROL", (PLATE_X / 2, -VERANDA_DEPTH - 1.0, 3.0), FACADE_OPEN,
                             cols["04_Openings"], "0 = French doors and shutters shut, 1 = open")
    build_openings(cols["04_Openings"], facade_ctrl)
    build_joinery(cols["05_Joinery"])
    if BUILD_PROPS:
        build_props(cols["06_Props"])
    build_veranda(cols["07_Veranda"])
    build_garden(cols["08_Garden"])
    build_pavilions(cols["08_Garden"], cols["11_Lighting"])
    build_paths(cols["08_Garden"])
    if BUILD_LANDSCAPE:
        build_landscape(cols["09_Landscape"])
    if BUILD_UPPER:
        build_upper(cols["10_UpperMassing"])
    if PH_MODELS.get("potted"):
        prng = random.Random(3)
        for k, (x, y, z) in enumerate(PLANT_SPOTS):
            place_instance(prng.choice(PH_MODELS["potted"]), (x, y, z), prng.uniform(0, 2 * math.pi),
                           1.0, cols["06_Props"], f"Potted_Plant_{k:02d}")
    sky = build_world()
    sun = build_lighting(cols["11_Lighting"])
    if BUILD_PRACTICALS:
        build_practicals(cols["11_Lighting"])
    build_cameras(cols["12_Cameras"])
    build_labels(cols["13_Labels"], areas)
    soften_edges(root_col.all_objects)
    setup_render()
    install_exposure_handler()

    # Parent the building (not the sun) to one root so SITE_ROTATION_DEG
    # turns the plan against the sky.
    root = bpy.data.objects.new("VERDIO_ROOT", None)
    root.empty_display_type = "PLAIN_AXES"
    root_col.objects.link(root)
    for ob in root_col.all_objects:
        if ob not in (root, sun) and ob.parent is None:
            ob.parent = root
    root.rotation_euler[2] = math.radians(SITE_ROTATION_DEG)

    for name in ("Ceiling_Boards", "Ceiling_Oak_Joists"):
        ob = bpy.data.objects.get(name)
        if ob is not None:
            try:
                ob.hide_set(True)      # viewport only; they still render
            except RuntimeError:
                pass

    total = sum(a for _, a in areas)
    print("\nVERDIO ground floor - net areas")
    for label, a in areas:
        print(f"  {label:<22} {a:6.1f} m2")
    print(f"  {'net total':<22} {total:6.1f} m2   (gross plate {PLATE_X * PLATE_Y:.0f} m2)")
    print(f"  veranda (covered, outdoor) {PLATE_X * VERANDA_DEPTH:6.1f} m2")
    print(f"  world: {sky}")
    if PH_STATUS["online"]:
        print("  Poly Haven assets:")
        for line in PH_STATUS["used"]:
            print(f"    {line}")
    else:
        print("  Poly Haven: offline, procedural stand-ins in use")
    print()


if __name__ == "__main__":
    main()
