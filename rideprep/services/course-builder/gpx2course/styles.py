"""Regional style profiles: make each course look like its country and terrain (spec §10.2 "regional material preset").

A profile overrides material colours (asphalt tone, cycle paths, facades, roofs, vegetation, fields), the default roof
shape when OSM has none, road-marking style and the tree species mix. It is chosen from the course origin (country
bounding boxes, checked smallest-first) and the terrain (alpine when the course climbs above 1200 m).
Both renderers read the result from the package's materials.json / manifest.style, so no per-renderer work is needed.
"""
from __future__ import annotations

import copy

# (w, s, e, n) — coarse national boxes; ordered smallest/most specific first.
COUNTRIES = [
    ("lu", (5.73, 49.44, 6.53, 50.19)), ("be", (2.54, 49.49, 6.41, 51.51)), ("nl", (3.31, 50.75, 7.23, 53.56)),
    ("dk", (8.07, 54.55, 12.7, 57.76)), ("ch", (5.95, 45.82, 10.49, 47.81)), ("at", (9.53, 46.37, 17.16, 49.02)),
    ("uk", (-8.65, 49.86, 1.77, 60.86)), ("it", (6.62, 36.6, 18.52, 47.1)), ("es", (-9.39, 35.95, 3.34, 43.79)),
    ("de", (5.87, 47.27, 15.04, 55.06)), ("fr", (-5.14, 41.33, 9.56, 51.09)),
]

BASE = {
    "name": "generic", "label": "Generic temperate", "roofDefault": "gabled", "markings": {"edge": "solid", "centre": "dashed"},
    "redCycleways": False, "treeMix": {"deciduous": 0.6, "conifer": 0.3, "poplar": 0.1}, "materials": {},
}

PROFILES = {
    "nl": {"label": "Netherlands — polder & brick", "redCycleways": True, "roofDefault": "gabled",
           "markings": {"edge": "dashed", "centre": "none"}, "treeMix": {"deciduous": 0.55, "conifer": 0.05, "poplar": 0.4},
           "materials": {"road_asphalt": [0.24, 0.24, 0.25], "road_asphalt_red": [0.55, 0.22, 0.18], "facade_brick": [0.52, 0.27, 0.19],
                         "roof_tile": [0.36, 0.22, 0.18], "terrain_grass": [0.36, 0.55, 0.22], "terrain_crop": [0.45, 0.55, 0.25],
                         "verge_grass": [0.34, 0.52, 0.22], "water": [0.18, 0.27, 0.32]}},
    "be": {"label": "Belgium — Flemish cobbles & brick", "roofDefault": "gabled", "markings": {"edge": "dashed", "centre": "dashed"},
           "materials": {"road_sett": [0.42, 0.40, 0.37], "facade_brick": [0.58, 0.33, 0.24], "roof_tile": [0.30, 0.25, 0.24],
                         "terrain_grass": [0.34, 0.50, 0.22]}},
    "lu": {"label": "Luxembourg — Ardennes", "roofDefault": "hipped", "treeMix": {"deciduous": 0.5, "conifer": 0.5, "poplar": 0.0},
           "materials": {"facade_plaster": [0.85, 0.82, 0.74], "roof_tile": [0.22, 0.22, 0.25]}},
    "fr": {"label": "France — limestone & plane trees", "roofDefault": "hipped", "markings": {"edge": "dashed", "centre": "dashed"},
           "treeMix": {"deciduous": 0.7, "conifer": 0.2, "poplar": 0.1},
           "materials": {"facade_plaster": [0.86, 0.80, 0.68], "facade_brick": [0.80, 0.74, 0.62], "roof_tile": [0.62, 0.35, 0.24],
                         "road_asphalt": [0.28, 0.28, 0.28], "terrain_crop": [0.62, 0.58, 0.32]}},
    "de": {"label": "Germany", "roofDefault": "gabled", "materials": {"facade_plaster": [0.88, 0.86, 0.80], "roof_tile": [0.48, 0.24, 0.18]}},
    "uk": {"label": "United Kingdom — hedgerows", "roofDefault": "gabled", "markings": {"edge": "solid", "centre": "dashed"},
           "materials": {"facade_brick": [0.55, 0.32, 0.24], "roof_tile": [0.28, 0.28, 0.30], "hedge": [0.18, 0.36, 0.13],
                         "terrain_grass": [0.30, 0.52, 0.22]}},
    "dk": {"label": "Denmark", "roofDefault": "gabled", "redCycleways": False,
           "materials": {"facade_brick": [0.62, 0.36, 0.22], "facade_plaster": [0.90, 0.80, 0.55]}},
    "it": {"label": "Italy — terracotta", "roofDefault": "hipped", "treeMix": {"deciduous": 0.5, "conifer": 0.4, "poplar": 0.1},
           "materials": {"facade_plaster": [0.85, 0.70, 0.52], "roof_tile": [0.66, 0.36, 0.24], "terrain_grass": [0.42, 0.50, 0.26],
                         "road_asphalt": [0.30, 0.30, 0.30]}},
    "es": {"label": "Spain — dry & whitewashed", "roofDefault": "hipped", "treeMix": {"deciduous": 0.3, "conifer": 0.7, "poplar": 0.0},
           "materials": {"facade_plaster": [0.93, 0.91, 0.86], "roof_tile": [0.66, 0.38, 0.26], "terrain_grass": [0.55, 0.52, 0.32],
                         "terrain_crop": [0.70, 0.62, 0.38], "terrain_bare": [0.70, 0.58, 0.42]}},
    "ch": {"label": "Switzerland", "roofDefault": "gabled", "materials": {"facade_plaster": [0.90, 0.88, 0.82]}},
    "at": {"label": "Austria", "roofDefault": "gabled", "materials": {"facade_plaster": [0.92, 0.88, 0.78]}},
    "alpine": {"label": "Alpine — rock, larch & guardrails", "roofDefault": "gabled", "markings": {"edge": "solid", "centre": "dashed"},
               "treeMix": {"deciduous": 0.15, "conifer": 0.85, "poplar": 0.0},
               "materials": {"terrain_bare": [0.55, 0.53, 0.50], "terrain_grass": [0.36, 0.48, 0.24], "facade_barn": [0.38, 0.27, 0.18],
                             "roof_tile": [0.30, 0.30, 0.32], "road_asphalt": [0.30, 0.30, 0.31]}},
}


def country_of(lat: float, lon: float) -> str | None:
    for code, (w, s, e, n) in COUNTRIES:
        if w <= lon <= e and s <= lat <= n:
            return code
    return None


def choose(lat: float, lon: float, max_elevation_m: float, override: str | None = None) -> dict:
    key = override or ("alpine" if max_elevation_m > 1200 else country_of(lat, lon))
    prof = copy.deepcopy(BASE)
    if key in PROFILES:
        p = PROFILES[key]
        prof.update({k: v for k, v in p.items() if k != "materials"})
        prof["materials"] = dict(p.get("materials", {}))
        prof["name"] = key
    prof["country"] = country_of(lat, lon)
    return prof


def apply_to_catalogue(cat: dict, profile: dict) -> dict:
    out = copy.deepcopy(cat)
    for mid, rgb in profile["materials"].items():
        if mid in out["materials"]:
            out["materials"][mid]["baseColor"] = rgb
    out["style"] = {k: profile[k] for k in ("name", "label", "roofDefault", "markings", "redCycleways", "treeMix")}
    return out
