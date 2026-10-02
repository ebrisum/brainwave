"""Road-surface defects as geometry, shared by the chunk bake (thin decals for streaming clients) and the hero road bake
(displaced, Nanite-dense surface for Unreal). Pure Python — no bpy — so it is unit-tested outside Blender.

Defects come from gpx2course/gamekit/roadside.py in road-local coordinates: s (m along the route), off (m, + = right of
the centreline). `Centreline` maps those onto the chunk's crowned/banked road surface (same cross-slope as the bake).
Shapes are seeded per defect, so every bake of a course shows the same pothole in the same place.
"""
import bisect
import math
import random


def cs(off, bank_deg, crown=0.02):
    """Cross-slope height at a lateral offset (+ right): crown blended into superelevation (gpx2course/roadgeom.py)."""
    t = math.tan(math.radians(bank_deg))
    w = min(1.0, abs(t) / 0.025)
    return (1 - w) * (-crown * abs(off)) + w * (-t * off)


class Centreline:
    """The chunk's course road (spec["road"]): road-local (s, off) → chunk-local (x, y, z) on the road surface."""

    LIFT = 0.04  # the chunk road sits 4 cm above the route centreline height

    def __init__(self, road):
        self.s, self.x, self.y, self.z = road["s"], road["x"], road["y"], road["z"]
        self.hs = [math.sin(h) for h in road["heading"]]
        self.hc = [math.cos(h) for h in road["heading"]]
        self.bank = road.get("bankDeg") or [0.0] * len(self.s)
        self.w = road["width"]

    def frame(self, s):
        """(x, y, z, ux, uy, nx, ny, bankDeg, halfWidth) at s: position, unit direction and right normal."""
        S = self.s
        i = min(max(bisect.bisect_right(S, s) - 1, 0), len(S) - 2)
        t = (s - S[i]) / ((S[i + 1] - S[i]) or 1.0)
        t = min(max(t, -0.5), 1.5)  # a little extrapolation at the chunk ends
        lerp = lambda a: a[i] + (a[i + 1] - a[i]) * t  # noqa: E731
        hx, hy = lerp(self.hs), lerp(self.hc)
        L = math.hypot(hx, hy) or 1.0
        ux, uy = hx / L, hy / L
        return lerp(self.x), lerp(self.y), lerp(self.z), ux, uy, uy, -ux, lerp(self.bank), lerp(self.w) / 2

    def point(self, s, off, lift=0.0):
        x, y, z, _, _, nx, ny, bank, _ = self.frame(s)
        return (x + nx * off, y + ny * off, z + self.LIFT + cs(off, bank) + lift)

    def covers(self, s):
        return self.s[0] - 1.0 <= s <= self.s[-1] + 1.0


# ---- shapes (road-local) ------------------------------------------------------------------------------------------------


def _local(d, u, v):
    """Defect-local (u along, v across, metres from its centre) → road-local (s, off), rotated by d["rot"]."""
    c, s_ = math.cos(d["rot"]), math.sin(d["rot"])
    return d["s"] + u * c - v * s_, d["off"] + u * s_ + v * c


def pothole_outline(d, n=18):
    """Ragged closed outline (road-local points) of a pothole: an ellipse with seeded radial jitter."""
    rnd = random.Random(d["seed"])
    a, b = d["len"] / 2, d["wid"] / 2
    ph = [rnd.random() * math.tau for _ in range(3)]
    out = []
    for k in range(n):
        t = k / n * math.tau
        j = 1.0 + 0.13 * math.sin(2 * t + ph[0]) + 0.08 * math.sin(3 * t + ph[1]) + 0.06 * math.sin(5 * t + ph[2]) + rnd.uniform(-0.05, 0.05)
        out.append(_local(d, a * j * math.cos(t), b * j * math.sin(t)))
    return out


def patch_outline(d):
    """Repair patch: a slightly irregular rectangle (cut edges are straight, corners not quite square)."""
    rnd = random.Random(d["seed"])
    a, b = d["len"] / 2, d["wid"] / 2
    q = [(-a, -b), (a, -b), (a, b), (-a, b)]
    return [_local(d, u + rnd.uniform(-0.03, 0.03), v + rnd.uniform(-0.03, 0.03)) for u, v in q]


def crack_path(d, step=0.25):
    """Meandering crack centre line (road-local points). Longitudinal cracks run along s, transverse ones across."""
    rnd = random.Random(d["seed"])
    if d["kind"] == "transverse":
        L, along = d["wid"], False
    else:
        L, along = d["len"], True
    n = max(2, int(L / step) + 1)
    pts, w = [], 0.0
    for k in range(n):
        t = -L / 2 + L * k / (n - 1)
        w += rnd.gauss(0, 0.012)
        w *= 0.92
        pts.append(_local(d, t, w) if along else _local(d, w, t))
    return pts


def edge_break_profile(d, step=0.2):
    """Crumbling edge: [(s, depth_in)] — how far (m) the broken edge reaches in from the road edge along the stretch."""
    rnd = random.Random(d["seed"])
    n = max(2, int(d["len"] / step) + 1)
    out = []
    for k in range(n):
        t = k / (n - 1)
        env = math.sin(math.pi * t) ** 0.6  # tapers in and out
        out.append((d["s"] + d["len"] * t, d["wid"] * env * (0.45 + 0.55 * rnd.random())))
    return out


# ---- height field for the hero road -----------------------------------------------------------------------------------


def _inside(poly, s, o):
    c = False
    n = len(poly)
    for k in range(n):
        (s1, o1), (s2, o2) = poly[k], poly[(k + 1) % n]
        if (o1 > o) != (o2 > o) and s < (s2 - s1) * (o - o1) / (o2 - o1) + s1:
            c = not c
    return c


def _dist_poly_edges(poly, s, o, closed=True):
    best = 1e9
    n = len(poly)
    for k in range(n if closed else n - 1):
        (s1, o1), (s2, o2) = poly[k], poly[(k + 1) % n]
        ds, do = s2 - s1, o2 - o1
        L2 = ds * ds + do * do or 1e-12
        t = max(0.0, min(1.0, ((s - s1) * ds + (o - o1) * do) / L2))
        best = min(best, math.hypot(s - (s1 + t * ds), o - (o1 + t * do)))
    return best


class Surface:
    """Height offset (m) of the defected road surface at road-local (s, off), relative to the clean crowned surface.

    potholes   bowls with steep walls (depth from roadside.py), a 3 mm crushed rim, a rough bottom
    patches    +3–4 mm plateaus with a 2 cm bevel
    cracks     sealed: +1.5 mm bitumen band; open: a V-groove (depth from roadside.py)
    edge break the road edge drops 4 cm to the base course where it has crumbled
    `fine(s, off)` says whether a point needs a dense mesh (≤ 4 cm) to show the detail.
    """

    def __init__(self, defects, half_width_at):
        self.items = []
        self.hw = half_width_at
        for d in defects:
            k = d["kind"]
            if k == "pothole":
                poly = pothole_outline(d)
                self.items.append(("pothole", d, poly, _bbox(poly, 0.06)))
            elif k == "patch":
                poly = patch_outline(d)
                self.items.append(("patch", d, poly, _bbox(poly, 0.03)))
            elif k in ("crackSealed", "crackOpen", "transverse"):
                path = crack_path(d)
                self.items.append(("crack", d, path, _bbox(path, abs(d["wid"] if k != "transverse" else d["len"]) + 0.02)))
            elif k == "edgeBreak":
                prof = edge_break_profile(d)
                side = 1 if d["off"] > 0 else -1
                inner = abs(d["off"]) - d["wid"] - 0.15
                lat = (inner, 1e9) if side > 0 else (-1e9, -inner)
                self.items.append(("edge", d, (prof, [p[0] for p in prof], side), (d["s"] - 0.2, d["s"] + d["len"] + 0.2) + lat))
        self.items.sort(key=lambda it: it[3][0])
        self.starts = [it[3][0] for it in self.items]
        self.max_len = max([it[3][1] - it[3][0] for it in self.items], default=0.0)

    def _near(self, s, o):
        k = bisect.bisect_right(self.starts, s)
        j = bisect.bisect_left(self.starts, s - self.max_len - 1e-6)
        for it in self.items[j:k]:
            s0, s1, o0, o1 = it[3]
            if s0 <= s <= s1 and o0 <= o <= o1:
                yield it

    def fine(self, s, o):
        return any(True for _ in self._near(s, o))

    def overlaps(self, s0, s1, o0, o1):
        """Does any defect's footprint touch the road-local box [s0, s1] × [o0, o1]? (mesh refinement)"""
        k = bisect.bisect_right(self.starts, s1)
        j = bisect.bisect_left(self.starts, s0 - self.max_len - 1e-6)
        for it in self.items[j:k]:
            a0, a1, b0, b1 = it[3]
            if a1 >= s0 and a0 <= s1 and b1 >= o0 and b0 <= o1:
                return True
        return False

    def material(self, s, o):
        """Kit material id the surface shows at (s, off), or None for the base asphalt."""
        out = None
        for kind, d, geo, _ in self._near(s, o):
            if kind == "pothole" and _inside(geo, s, o):
                return "pothole"
            if kind == "edge" and self.height(s, o) <= d["depth"] + 1e-9:
                return "gravel"  # the base course shows where the edge has crumbled
            if kind == "patch" and _inside(geo, s, o):
                out = "asphalt_patch"
            if kind == "crack" and d["depth"] > 0:
                w = abs(d["wid"] if d["kind"] != "transverse" else d["len"]) / 2
                if _dist_poly_edges(geo, s, o, closed=False) < w:
                    out = "tar_seal"
        return out

    def height(self, s, o):
        dz = 0.0
        for kind, d, geo, _ in self._near(s, o):
            if kind == "pothole":
                e = _dist_poly_edges(geo, s, o)
                if _inside(geo, s, o):
                    r = min(1.0, e / max(0.04, min(d["len"], d["wid"]) * 0.25))  # 0 at the wall → 1 a quarter in
                    rough = 0.15 * math.sin(s * 91.0 + o * 37.0) * math.sin(s * 53.0 - o * 71.0)
                    dz = min(dz, d["depth"] * (r ** 0.35) * (1.0 + rough))
                elif e < 0.05:
                    dz = max(dz, 0.003 * (1 - e / 0.05))
            elif kind == "patch":
                if _inside(geo, s, o):
                    e = _dist_poly_edges(geo, s, o)
                    dz = max(dz, d["depth"] * min(1.0, e / 0.02))
            elif kind == "crack":
                w = abs(d["wid"] if d["kind"] != "transverse" else d["len"]) / 2
                dist = _dist_poly_edges(geo, s, o, closed=False)
                if dist < w:
                    if d["depth"] > 0:
                        dz = max(dz, d["depth"])
                    else:
                        dz = min(dz, d["depth"] * (1 - dist / w))
            elif kind == "edge":
                prof, ps, side = geo
                if side * o > 0:
                    k = min(max(bisect.bisect_left(ps, s), 0), len(ps) - 1)
                    if self.hw(s) - abs(o) < prof[k][1]:
                        dz = min(dz, d["depth"])
        return dz


def _bbox(pts, pad):
    ss = [p[0] for p in pts]
    oo = [p[1] for p in pts]
    return (min(ss) - pad, max(ss) + pad, min(oo) - pad, max(oo) + pad)


# ---- gravel shoulder stones -------------------------------------------------------------------------------------------


def stone_height(s, o, seed=0, cell=0.045, height=0.016):
    """Loose gravel as a height field: Worley-style rounded stones on a jittered grid (one stone per cell)."""
    i0, j0 = math.floor(s / cell), math.floor(o / cell)
    best = 0.0
    for i in (i0 - 1, i0, i0 + 1):
        for j in (j0 - 1, j0, j0 + 1):
            rnd = random.Random((i * 73856093) ^ (j * 19349663) ^ seed)
            cx, cy = (i + rnd.random()) * cell, (j + rnd.random()) * cell
            r = cell * (0.35 + 0.35 * rnd.random())
            dd = math.hypot(s - cx, o - cy)
            if dd < r:
                best = max(best, height * (0.5 + 0.5 * rnd.random()) * math.sqrt(1 - (dd / r) ** 2))
    return best
