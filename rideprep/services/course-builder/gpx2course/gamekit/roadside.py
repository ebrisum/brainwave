"""Roadside rules and road-surface defects for the game-art layer.

These are the procedural ("PCG") rules an engine would otherwise run at load time, evaluated once in the pipeline so
every client — web chunks, the Unreal hero road — gets the same world, and so they can be tested here:

  setback    trees and tree rows stay `treeSetbackM` (5 m) clear of the course road edge; hedges `hedgeSetbackM`.
  shoulder   rural roads without kerbs get a gravel shoulder, wider on bigger roads; none on bridges or in towns.
  guardrail  W-beam runs where the ground drops ≥ `embankmentM` within 4 m of the edge, on bridges, and where water
             lies within `waterM` of the edge (Romagna roads run along canals). Runs are evaluated on the whole route
             (chunk boundaries never split them), gaps shorter than `gapM` are closed, runs shorter than `minRunM` dropped.
  defects    potholes, patches (incl. trench repairs), sealed and open cracks, crumbling edges — deterministic per
             route sample (hash-seeded), with densities per surface material; none on porphyry setts in towns.

Defects are road-local: `s` (m along the route), `off` (m, + = right of the centreline), `len` along, `wid` across,
`rot` (rad, relative to the road direction), `depth` (m, − = below the surface), `seed` for the renderer's noise.
"""
from __future__ import annotations

import copy
import math

import numpy as np

DEFAULT_RULES = {
    "treeSetbackM": 5.0,
    "hedgeSetbackM": 1.5,
    "shoulderM": {"trunk": 1.0, "primary": 0.9, "secondary": 0.8, "tertiary": 0.6, "unclassified": 0.5, "default": 0.5},
    "guardrail": {"embankmentM": 1.5, "probeM": 4.0, "waterM": 4.0, "minRunM": 12.0, "gapM": 12.0},
    # per km of road, by course-road surface material
    "defects": {
        "asphalt": {"pothole": 0.4, "patch": 3.0, "crackSealed": 4.0, "crackOpen": 1.0, "transverse": 2.0, "edgeBreak": 0.0},
        "asphalt_worn": {"pothole": 3.0, "patch": 10.0, "crackSealed": 14.0, "crackOpen": 6.0, "transverse": 8.0, "edgeBreak": 2.5},
        "gravel": {"pothole": 14.0, "patch": 0.0, "crackSealed": 0.0, "crackOpen": 0.0, "transverse": 0.0, "edgeBreak": 0.0},
    },
}
KINDS = ("pothole", "patch", "crackSealed", "crackOpen", "transverse", "edgeBreak")


def rules(kit: dict) -> dict:
    """Kit "rules" merged over the defaults (nested dicts merge key by key)."""
    out = copy.deepcopy(DEFAULT_RULES)

    def merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v)
            else:
                dst[k] = v

    merge(out, kit.get("rules", {}))
    return out


def road_material(surface_code: int, highway: str) -> str:
    """Course-road surface material (matches the chunk bake): gravel, porphyry setts, or new/worn asphalt by class."""
    if surface_code in (6, 7, 8):
        return "gravel"
    if surface_code in (4, 5):
        return "paving_porphyry"
    return "asphalt" if highway in ("primary", "secondary", "trunk") else "asphalt_worn"


def _rng(*key) -> np.random.Generator:
    from .prep import rng

    return rng(*key)


# ---- shoulders --------------------------------------------------------------------------------------------------------


def shoulder_widths(r: dict, idx, urban, rules_: dict) -> list[float]:
    """Gravel shoulder width per route sample (both sides): 0 in towns, on bridges and on gravel/sett roads."""
    out = []
    widths = rules_["shoulderM"]
    for i in idx:
        mat = road_material(int(r["surfaceCode"][i]), str(r["highway"][i]))
        if urban[i] or r["bridgeMask"][i] or mat in ("gravel", "paving_porphyry"):
            out.append(0.0)
        else:
            out.append(float(widths.get(str(r["highway"][i]), widths["default"])))
    return out


# ---- guardrails -------------------------------------------------------------------------------------------------------


def guardrail_need(r: dict, H, urban, water_near=None, rules_: dict | None = None) -> dict[int, np.ndarray]:
    """Per side (+1 right, −1 left), per route sample: does this edge need a guardrail?"""
    g = (rules_ or DEFAULT_RULES)["guardrail"]
    hd = np.asarray(r["headingRad"], float)
    nx, ny = np.cos(hd), -np.sin(hd)  # right-hand normal (compass heading, x = east)
    hw = np.asarray(r["roadWidthM"], float) / 2
    x, y, z = (np.asarray(r[k], float) for k in ("x", "y", "z"))
    bridge = np.asarray(r["bridgeMask"], bool)
    urb = np.asarray(urban, bool)
    out = {}
    for side in (1, -1):
        off = hw + 0.5 + g["probeM"]
        drop = z - H(x + nx * off * side, y + ny * off * side)
        need = bridge | ((drop > g["embankmentM"]) & ~urb)
        if water_near is not None:
            wo = hw + g["waterM"] / 2
            need |= water_near(x + nx * wo * side, y + ny * wo * side, g["waterM"] / 2) & ~urb
        out[side] = need
    return out


def runs_from_need(need: np.ndarray, spacing: float, min_run_m: float, gap_m: float) -> list[tuple[int, int]]:
    """Boolean per sample → [(i0, i1)] inclusive sample ranges, with short gaps closed and short runs dropped."""
    idx = np.nonzero(need)[0]
    if len(idx) == 0:
        return []
    runs = []
    a = b = int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if (i - b) * spacing <= gap_m:
            b = i
        else:
            runs.append((a, b))
            a = b = i
    runs.append((a, b))
    return [(a, b) for a, b in runs if (b - a + 1) * spacing >= min_run_m]


def guardrail_runs(r: dict, H, urban, water_near=None, rules_: dict | None = None) -> list[tuple[int, float, float]]:
    """Whole-route guardrail runs: [(side, sStart, sEnd)]."""
    g = (rules_ or DEFAULT_RULES)["guardrail"]
    sp = float(r["spacing"])
    s = np.asarray(r["s"], float)
    out = []
    for side, need in guardrail_need(r, H, urban, water_near, rules_).items():
        for a, b in runs_from_need(need, sp, g["minRunM"], g["gapM"]):
            out.append((side, float(s[a]), float(min(s[-1], s[b] + sp))))
    return sorted(out, key=lambda t: (t[1], t[0]))


def place_guardrails(runs, r: dict, s0: float, s1: float, H, put, seg_m: float = 4.0) -> int:
    """4 m W-beam segments for the parts of `runs` inside [s0, s1). The kit segment spans +X from its origin with the
    beam facing −Y, so right-side segments start at the step and left-side ones (turned 180°) at its end."""
    s = np.asarray(r["s"], float)
    hs, hc = np.sin(r["headingRad"]), np.cos(r["headingRad"])
    n = 0
    for side, a, b in runs:
        lo, hi = max(a, s0), min(b, s1)
        # steps on a global 4 m grid along each run, so neighbouring chunks continue it seamlessly
        t = a + math.ceil((lo - a) / seg_m - 1e-9) * seg_m
        while t < hi - 1e-6 and t + seg_m <= b + 1e-6:
            tm = t + seg_m / 2
            hx, hy = float(np.interp(tm, s, hs)), float(np.interp(tm, s, hc))
            L = math.hypot(hx, hy) or 1.0
            ux, uy = hx / L, hy / L
            nx, ny = uy, -ux
            hw = float(np.interp(tm, s, r["roadWidthM"])) / 2
            off = (hw + 0.5) * side
            sx, sy, sz = (float(np.interp(t if side > 0 else t + seg_m, s, r[k])) for k in ("x", "y", "z"))
            px, py = sx + nx * off, sy + ny * off
            put("guardrail_4m", px, py, sz - 0.05, math.atan2(uy, ux) + (math.pi if side < 0 else 0.0), 1.0)
            n += 1
            t += seg_m
    return n


# ---- defects ----------------------------------------------------------------------------------------------------------


def _lateral(g: np.random.Generator, hw: float, kind: str) -> float:
    """Where on the road a defect sits: wheel paths and the right lane mostly; the edge for potholes now and then."""
    side = 1.0 if g.random() < 0.6 else -1.0
    lane_c = hw / 2
    if kind == "pothole" and g.random() < 0.35:
        return side * (hw - 0.35 - 0.5 * g.random())
    if kind in ("crackSealed", "crackOpen") and g.random() < 0.4:
        return g.normal(0, 0.08)  # the centre joint between the two paving passes
    return side * (lane_c + (0.85 if g.random() < 0.5 else -0.85) + g.normal(0, 0.15))


def defects_for(r: dict, idx, urban, rules_: dict | None = None) -> list[dict]:
    """Road-surface defects for route samples `idx` (deterministic per sample, independent of chunking)."""
    cfg = (rules_ or DEFAULT_RULES)["defects"]
    sp = float(r["spacing"])
    out = []
    for i in idx:
        i = int(i)
        mat = road_material(int(r["surfaceCode"][i]), str(r["highway"][i]))
        dens = cfg.get(mat)
        if not dens or r["bridgeMask"][i]:
            continue
        hw = float(r["roadWidthM"][i]) / 2
        g = _rng("defect", i)
        for kind in KINDS:
            lam = dens.get(kind, 0.0) * sp / 1000.0
            if kind == "edgeBreak" and urban[i]:
                lam = 0.0
            for _ in range(int(g.poisson(lam)) if lam > 0 else 0):
                s = float(r["s"][i]) + float(g.random()) * sp
                d = {"kind": kind, "s": round(s, 2), "seed": int(g.integers(0, 2**31 - 1))}
                if kind == "pothole":
                    rad = float(np.clip(g.lognormal(math.log(0.22), 0.4), 0.1, 0.5))
                    d.update(off=_lateral(g, hw, kind), len=2 * rad, wid=2 * rad * (0.7 + 0.3 * g.random()), rot=float(g.uniform(-0.6, 0.6)),
                             depth=-float(np.clip(0.02 + 0.06 * g.random() * rad / 0.3, 0.015, 0.08)))
                elif kind == "patch":
                    if g.random() < 0.18:  # trench repair across the lane
                        lw = hw - 0.15
                        d.update(off=(1 if g.random() < 0.6 else -1) * lw / 2, len=float(g.uniform(0.45, 0.8)), wid=lw, rot=float(g.normal(0, 0.03)),
                                 depth=0.004)
                    else:
                        d.update(off=_lateral(g, hw, kind), len=float(g.uniform(0.8, 4.0)), wid=float(g.uniform(0.6, 1.8)),
                                 rot=float(g.normal(0, 0.05)), depth=0.003)
                elif kind in ("crackSealed", "crackOpen"):
                    d.update(off=_lateral(g, hw, kind), len=float(g.uniform(2.0, 14.0)), wid=0.045 if kind == "crackSealed" else 0.015,
                             rot=float(g.normal(0, 0.02)), depth=0.0015 if kind == "crackSealed" else -0.008)
                elif kind == "transverse":
                    full = g.random() < 0.4
                    lw = 2 * hw - 0.3 if full else hw - 0.15
                    d.update(off=0.0 if full else (1 if g.random() < 0.6 else -1) * lw / 2, len=0.04, wid=lw, rot=float(g.normal(0, 0.06)),
                             depth=0.0015 if g.random() < 0.6 else -0.008)
                else:  # edgeBreak: the edge crumbles inward over a stretch
                    d.update(off=(1 if g.random() < 0.55 else -1) * hw, len=float(g.uniform(4.0, 25.0)), wid=float(g.uniform(0.08, 0.35)),
                             rot=0.0, depth=-0.04)
                for k in ("off", "len", "wid", "rot", "depth"):
                    d[k] = round(float(d[k]), 4)
                # keep everything on the road (the rotated footprint, 10 cm in from the edge)
                if kind != "edgeBreak":
                    half = abs(d["wid"] / 2 * math.cos(d["rot"])) + abs(d["len"] / 2 * math.sin(d["rot"]))
                    lim = max(0.0, hw - 0.1 - half - 1e-3)
                    d["off"] = round(float(np.clip(d["off"], -lim, lim)), 4)
                out.append(d)
    return out


def summary(defects: list[dict]) -> dict[str, int]:
    out = {k: 0 for k in KINDS}
    for d in defects:
        out[d["kind"]] += 1
    return out
