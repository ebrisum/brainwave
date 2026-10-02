"""Game-art level data: turn a built course package into per-chunk "game chunk specs" for the Blender bake.

All GIS work happens here (numpy/shapely); Blender only turns specs into meshes. Per 500 m chunk:
  terrain   global 6 m lattice within `halfWidthM` of the route (cells assigned to the chunk of their nearest route
            sample, so neighbouring chunks share vertices exactly); heights = DEM, blended to the road under the
            course; one kit material per cell (water > land use > WorldCover).
  road      the course road (route samples, widths, urban flag → kerbs/sidewalks, bridge flag, surface material).
  sideRoads every other road piece in the cell area, draped on the terrain, with width and material by class.
  buildings footprints with base height, eave height, roof type, wall/roof materials and ground-floor flag.
  instances kit asset → [[x, y, z, rotZ, scale]] (vines along real vineyard rows, orchard grids, forest scatter,
            poplars on canals, reeds and flamingos at the salt pans, garden trees, delineators, guardrails,
            streetlights, town signs, race barriers).
Coordinates are ENU metres relative to the chunk origin. Deterministic (hash-seeded RNG per chunk/feature).
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import shape
from shapely.ops import substring

GRID_M = 6.0
HALF_WIDTH_M = 240.0
CHUNK_M = 500.0

SIDE_ROAD = {  # highway → (width m, material)
    "motorway": (11.0, "asphalt"), "trunk": (9.0, "asphalt"), "primary": (7.5, "asphalt"), "secondary": (7.0, "asphalt"),
    "tertiary": (6.0, "asphalt_worn"), "unclassified": (5.0, "asphalt_worn"), "residential": (5.5, "asphalt_worn"),
    "living_street": (4.5, "paving_porphyry"), "service": (3.5, "asphalt_worn"), "road": (4.5, "asphalt_worn"),
    "track": (3.0, "gravel"), "cycleway": (2.5, "asphalt"), "footway": (1.8, "gravel"), "path": (1.5, "gravel"),
    "pedestrian": (6.0, "paving_porphyry"), "bridleway": (2.0, "gravel"), "steps": (2.0, "paving_porphyry"),
    "motorway_link": (6.0, "asphalt"), "trunk_link": (6.0, "asphalt"), "primary_link": (6.0, "asphalt"), "secondary_link": (6.0, "asphalt"),
}


class Pkg:
    """Minimal read-only view of a course package (enough for CorridorRaster / load_route)."""

    def __init__(self, d: Path):
        self.dir = Path(d)
        self.cache: dict = {}

    def path(self, rel: str) -> Path:
        return self.dir / rel

    def read_json(self, rel: str):
        return json.loads(self.path(rel).read_text())


def terrain_classes(kit: dict) -> list[str]:
    """Global, stable list of terrain material ids (index = land-use mask value; 0 = no data)."""
    t = kit["terrain"]
    names = set(t["water"].values()) | set(t["worldcover"].values())
    for v in t["landuse"].values():
        names |= set(v) if isinstance(v, list) else {v}
    return ["none"] + sorted(names)


def landuse_mask(spec: dict, classes: list[str]):
    """8-bit PNG (one pixel per terrain cell, north up) of class indices + its ENU bounds relative to the chunk origin."""
    import io

    from PIL import Image

    t = spec["terrain"]
    if not t["cells"]:
        return None
    c = np.asarray(t["cells"])
    G = t["gridM"]
    i0, j0 = c[:, 0].min(), c[:, 1].min()
    w, h = c[:, 0].max() - i0 + 1, c[:, 1].max() - j0 + 1
    img = np.zeros((h, w), np.uint8)
    lut = np.array([classes.index(m) for m in t["materials"]], np.uint8)
    img[h - 1 - (c[:, 1] - j0), c[:, 0] - i0] = lut[c[:, 2]]
    buf = io.BytesIO()
    Image.fromarray(img, "L").save(buf, format="PNG", optimize=True)
    ox, oy, _ = spec["origin"]
    return buf.getvalue(), [round(i0 * G - ox, 2), round(j0 * G - oy, 2), round((i0 + w) * G - ox, 2), round((j0 + h) * G - oy, 2)]


def rng(*key) -> np.random.Generator:
    return np.random.default_rng(int.from_bytes(hashlib.sha256(json.dumps(key, default=str).encode()).digest()[:8], "little"))


def h01(*key) -> float:
    return int.from_bytes(hashlib.sha256(json.dumps(key, default=str).encode()).digest()[:4], "little") / 2**32


class Heights:
    """Terrain height function shared by vertices and instances: DEM, blended to the course road surface."""

    def __init__(self, dem, route):
        self.dem = dem
        self.rxy = np.c_[route["x"], route["y"]]
        self.rz = route["z"]
        self.hw = route["roadWidthM"] / 2
        self.bridge = route["bridgeMask"]
        self.tree = cKDTree(self.rxy)

    def __call__(self, x, y):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        z = self.dem.sample(x, y)
        P = np.c_[x.ravel(), y.ravel()]
        zf = z.ravel().copy()
        reach = float(self.hw.max()) + 14
        d, i = self.tree.query(P, distance_upper_bound=reach)
        ok = np.isfinite(d)
        ii = i[ok]
        w = np.clip(1 - (d[ok] - self.hw[ii] - 2.0) / 10.0, 0, 1)
        w[self.bridge[ii]] = 0.0  # keep the valley under bridges
        zf[ok] = zf[ok] * (1 - w) + (self.rz[ii] - 0.25) * w
        # Switchbacks/overlaps: never let terrain rise above ANY road surface it lies under (other hairpin legs)
        idx = np.nonzero(ok)[0]
        if len(idx):
            near = self.tree.query_ball_point(P[idx], float(self.hw.max()) + 2.5)
            for q, lst in zip(idx, near):
                if len(lst) < 2:
                    continue
                lst = np.asarray(lst)
                dd = np.hypot(*(self.rxy[lst] - P[q]).T)
                on = lst[(dd < self.hw[lst] + 2.5) & ~self.bridge[lst]]
                if len(on):
                    zf[q] = min(zf[q], float(self.rz[on].min()) - 0.25)
        return zf.reshape(z.shape)


def _polys(features, pred):
    out = []
    for f in features:
        p = f["properties"]
        if not pred(p):
            continue
        g = shape(f["geometry"])
        if g.geom_type in ("Polygon", "MultiPolygon") and g.is_valid and g.area > 1:
            out.append((g, p))
    return out


def prepare(pkg_dir: Path, kit: dict, out_dir: Path, half_width_m: float = HALF_WIDTH_M, grid_m: float = GRID_M,
            chunk_ids: list[int] | None = None) -> dict:
    from ..stages.common import CorridorRaster, load_route

    pkg = Pkg(pkg_dir)
    r = load_route(pkg)
    r["bridgeMask"] = np.array([(b or "") not in ("", "no") for b in r["bridge"]])
    dem = CorridorRaster(pkg, "dem")
    lc = CorridorRaster(pkg, "lc")
    H = Heights(dem, r)
    L = float(r["s"][-1])
    n_chunks = int(math.ceil(L / CHUNK_M - 1e-9))
    rtree = cKDTree(np.c_[r["x"], r["y"]])
    sample_chunk = np.minimum((r["s"] // CHUNK_M).astype(int), n_chunks - 1)
    origin = pkg.read_json("origin.json")
    frame_lat0 = origin["lat"]

    osm = pkg.read_json("corridor/osm.geojson")["features"]
    blds = pkg.read_json("corridor/buildings.geojson")["features"]
    tmap = kit["terrain"]
    # Land-use and water polygons (priority: water, then smaller land-use polygons first)
    water = _polys(osm, lambda p: p.get("natural") == "water")
    landuse = _polys(osm, lambda p: "landuse" in p or p.get("leisure") in ("park", "pitch", "nature_reserve") or p.get("natural") in ("beach", "wetland"))
    landuse.sort(key=lambda gp: gp[0].area)
    lu_tree = shapely.STRtree([g for g, _ in landuse]) if landuse else None
    w_tree = shapely.STRtree([g for g, _ in water]) if water else None

    def lu_material(g_idx):
        g, p = landuse[g_idx]
        key = p.get("landuse") or p.get("leisure") or p.get("natural")
        m = tmap["landuse"].get(key)
        if isinstance(m, list):
            m = m[int(h01("farm", round(g.centroid.x), round(g.centroid.y)) * len(m))]
        return m

    def water_material(g_idx):
        return tmap["water"].get(water[g_idx][1].get("water"), tmap["water"]["default"])

    waterways = [shape(f["geometry"]) for f in osm if f["properties"].get("waterway") in ("canal", "river", "stream")
                 and f["geometry"]["type"] == "LineString"]
    # Side roads (everything but the course road itself), cut into ≤ 24 m pieces
    roads = []
    for f in osm:
        p = f["properties"]
        hw = p.get("highway")
        if hw not in SIDE_ROAD:
            continue
        g = shape(f["geometry"])
        if g.geom_type != "LineString" or g.length < 1:
            continue
        w, mat = SIDE_ROAD[hw]
        if p.get("width"):
            try:
                w = float(p["width"])
            except ValueError:
                pass
        n = max(1, int(math.ceil(g.length / 24)))
        for k in range(n):
            piece = substring(g, k / n * g.length, (k + 1) / n * g.length)
            if piece.length < 0.5:
                continue
            roads.append((piece, w, mat, hw, p.get("bridge") == "yes", p.get("tunnel") == "yes"))
    side_lines = [rd[0] for rd in roads]
    side_tree = shapely.STRtree(side_lines) if side_lines else None

    # Buildings
    bpolys = []
    for f in blds:
        g = shape(f["geometry"])
        if not g.is_valid or g.area < 6:
            continue
        bpolys.append((g, f["properties"]))
    b_tree = shapely.STRtree([g for g, _ in bpolys]) if bpolys else None
    # Urban density per route sample: buildings within 45 m
    if bpolys:
        cent = np.array([[g.centroid.x, g.centroid.y] for g, _ in bpolys])
        btree_pts = cKDTree(cent)
        dens = np.array([len(v) for v in btree_pts.query_ball_point(np.c_[r["x"], r["y"]], 45.0)])
    else:
        dens = np.zeros(r["count"], int)
    urban = np.convolve(dens >= 4, np.ones(9) / 9, mode="same") > 0.5

    # Town centres → local frame (for town signs and coastal species)
    from ..geo import LocalFrame

    frame = LocalFrame(origin["lat"], origin["lon"])
    towns = kit.get("towns", [])
    tc = kit.get("townCentres", {})
    town_xy = np.array([frame.to_xy(np.array([tc[t][0]]), np.array([tc[t][1]])) for t in towns if t in tc]).reshape(-1, 2)
    town_idx = [k for k, t in enumerate(towns) if t in tc]
    coast = kit.get("coastline")
    coast_x = float(frame.to_xy(np.array([frame_lat0]), np.array([coast["lonEast"]]))[0][0]) if coast else None

    out_dir.mkdir(parents=True, exist_ok=True)
    classes = terrain_classes(kit)
    index = []
    ids = chunk_ids if chunk_ids is not None else list(range(n_chunks))
    for k in ids:
        spec = _chunk(k, r, H, lc, rtree, sample_chunk, n_chunks, half_width_m, grid_m, kit, landuse, lu_tree, lu_material, water, w_tree,
                      water_material, roads, side_tree, bpolys, b_tree, urban, town_xy, town_idx, coast_x, waterways)
        (out_dir / f"g{k}.json").write_text(json.dumps(spec, separators=(",", ":")))
        mask = landuse_mask(spec, classes)
        if mask is not None:
            png, bounds = mask
            (out_dir / f"lu{k}.png").write_bytes(png)
            spec_bounds = bounds
        else:
            spec_bounds = None
        cells = np.asarray(spec["terrain"]["cells"]) if spec["terrain"]["cells"] else np.zeros((0, 3))
        bounds = ([round(float(cells[:, 0].min() * grid_m), 1), round(float(cells[:, 1].min() * grid_m), 1),
                   round(float((cells[:, 0].max() + 1) * grid_m), 1), round(float((cells[:, 1].max() + 1) * grid_m), 1)] if len(cells) else None)
        index.append({"landuseBounds": spec_bounds, "bounds": bounds, "id": k, "sStart": k * CHUNK_M, "sEnd": min(L, (k + 1) * CHUNK_M), "origin": spec["origin"],
                      "counts": {"cells": len(spec["terrain"]["cells"]), "buildings": len(spec["buildings"]), "sideRoads": len(spec["sideRoads"]),
                                 "instances": sum(len(v) for v in spec["instances"].values())}})
    far = _far_terrain(pkg, H, lc, rtree, half_width_m, kit, sample_chunk)
    (out_dir / "far.json").write_text(json.dumps(far, separators=(",", ":")))
    doc = {"kit": kit["name"], "gridM": grid_m, "halfWidthM": half_width_m, "chunkM": CHUNK_M, "chunks": index, "landuseClasses": classes}
    (out_dir / "index.json").write_text(json.dumps(doc, indent=1))
    return doc


def _chunk(k, r, H, lc, rtree, sample_chunk, n_chunks, W, G, kit, landuse, lu_tree, lu_material, water, w_tree, water_material,
           roads, side_tree, bpolys, b_tree, urban, town_xy, town_idx, coast_x, waterways):
    sel = np.nonzero(sample_chunk == k)[0]
    a, b = max(0, sel[0] - 1), min(r["count"] - 1, sel[-1] + 1)
    ox, oy, oz = round(float(r["x"][a])), round(float(r["y"][a])), round(float(r["z"][a]))
    # ---- terrain cells: lattice cells whose centre's nearest route sample is in this chunk and within W
    x0, x1 = r["x"][a:b + 1].min() - W - G, r["x"][a:b + 1].max() + W + G
    y0, y1 = r["y"][a:b + 1].min() - W - G, r["y"][a:b + 1].max() + W + G
    i0, i1 = int(math.floor(x0 / G)), int(math.ceil(x1 / G))
    j0, j1 = int(math.floor(y0 / G)), int(math.ceil(y1 / G))
    I, J = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1), indexing="ij")
    cx, cy = (I.ravel() + 0.5) * G, (J.ravel() + 0.5) * G
    d, nearest = rtree.query(np.c_[cx, cy])
    keep = (d <= W) & (sample_chunk[nearest] == k)
    ci, cj = I.ravel()[keep], J.ravel()[keep]
    cx, cy = cx[keep], cy[keep]
    # Vertex heights for the needed lattice vertices
    V = np.unique(np.r_[np.c_[ci, cj], np.c_[ci + 1, cj], np.c_[ci, cj + 1], np.c_[ci + 1, cj + 1]], axis=0)
    vi, vj = V[:, 0], V[:, 1]
    vz = H(vi * G, vj * G)
    # Cell materials
    mats = np.array([None] * len(cx), dtype=object)
    pts = shapely.points(cx, cy)
    if w_tree is not None:
        pi, gi = w_tree.query(pts, predicate="within")
        for p_, g_ in zip(pi, gi):
            if mats[p_] is None:
                mats[p_] = water_material(g_)
    if lu_tree is not None:
        pi, gi = lu_tree.query(pts, predicate="within")
        order = np.lexsort((gi, pi))  # smaller polygons have lower indices (sorted by area)
        for p_, g_ in zip(pi[order], gi[order]):
            if mats[p_] is None:
                mats[p_] = lu_material(g_)
    rest = np.array([m is None for m in mats])
    if rest.any():
        cls = lc.sample(cx[rest], cy[rest]).astype(int)
        wc = kit["terrain"]["worldcover"]
        fields = kit["terrain"]["landuse"]["farmland"]
        fx, fy = np.floor(cx[rest] / 170.0).astype(int), np.floor(cy[rest] / 110.0).astype(int)
        mats[rest] = [fields[int(h01("field", int(a_), int(b_)) * len(fields))] if c == 40 else wc.get(str(c), "grass_dry")
                      for c, a_, b_ in zip(cls, fx, fy)]
    # Towns: residential/industrial land use is mostly gardens and yards — paved only near buildings
    urb = np.array([m == "urban_ground" for m in mats])
    if urb.any() and b_tree is not None:
        near_b = np.zeros(len(cx), bool)
        pi, _ = b_tree.query(pts[urb], predicate="dwithin", distance=7.0)
        near_b[np.nonzero(urb)[0][pi]] = True
        garden = urb & ~near_b
        mats[garden] = ["grass_green" if h01("garden", int(i_), int(j_)) < 0.6 else "grass_dry" for i_, j_ in zip(ci[garden], cj[garden])]
    mat_names = sorted(set(mats))
    mat_idx = {m: i for i, m in enumerate(mat_names)}
    terrain = {"gridM": G, "materials": mat_names, "vertices": np.c_[vi, vj, np.round(vz - oz, 2)].tolist(),
               "cells": np.c_[ci, cj, [mat_idx[m] for m in mats]].tolist()}
    cell_mat_lookup = {(int(i), int(j)): m for i, j, m in zip(ci, cj, mats)}

    # ---- course road
    rs = slice(a, b + 1)
    surf = r["surfaceCode"][rs]
    road = {"s": np.round(r["s"][rs], 2).tolist(), "x": np.round(r["x"][rs] - ox, 3).tolist(), "y": np.round(r["y"][rs] - oy, 3).tolist(),
            "z": np.round(r["z"][rs] - oz, 3).tolist(), "heading": np.round(r["headingRad"][rs], 5).tolist(),
            "width": np.round(r["roadWidthM"][rs], 2).tolist(), "bridge": r["bridgeMask"][rs].tolist(), "urban": urban[rs].tolist(),
            "material": ["gravel" if c in (6, 7, 8) else ("paving_porphyry" if c in (4, 5) else
                         ("asphalt" if h in ("primary", "secondary", "trunk") else "asphalt_worn")) for c, h in zip(surf, r["highway"][rs])],
            "terrainZ": np.round(H(r["x"][rs], r["y"][rs]) - oz, 2).tolist(),
            "bankDeg": np.round(r["bankDeg"][rs], 2).tolist() if "bankDeg" in r else [0.0] * (b + 1 - a)}
    hw_route = r["roadWidthM"] / 2

    # Area of this chunk (union of its cells as a rough polygon) for selecting features
    area = shapely.union_all(shapely.box(cx - G / 2, cy - G / 2, cx + G / 2, cy + G / 2)) if len(cx) else shapely.Polygon()
    area_tree_box = shapely.box(*area.bounds) if not area.is_empty else area

    # ---- side roads
    side = []
    if side_tree is not None and not area.is_empty:
        for gi in side_tree.query(area_tree_box):
            line, w, mat, hwy, is_bridge, is_tunnel = roads[gi]
            mid = line.interpolate(0.5, normalized=True)
            dd, ii = rtree.query([mid.x, mid.y])
            if dd > W or sample_chunk[ii] != k:
                continue
            # Skip pieces that are the course road itself (close and parallel)
            co = np.asarray(line.coords)
            if dd < hw_route[ii] + 2.5:
                v = co[-1] - co[0]
                ang = math.atan2(v[0], v[1])
                diff = abs((ang - r["headingRad"][ii] + math.pi) % math.pi)
                diff = min(diff, math.pi - diff)
                if diff < math.radians(30) or line.length < 8:
                    continue
            if is_tunnel:
                continue
            # Densify to ≤ 4 m and drape (+ clearance); bridges keep a straight interpolation between their ends
            n = max(2, int(math.ceil(line.length / 4)) + 1)
            pts = np.array([line.interpolate(t, normalized=True).coords[0] for t in np.linspace(0, 1, n)])
            z = H(pts[:, 0], pts[:, 1])
            if is_bridge:
                z = np.linspace(z[0], z[-1], n) + np.minimum(np.sin(np.linspace(0, math.pi, n)) * 1.5, 1.5)
            # Don't let side roads poke through the course road near junctions
            d2, i2 = rtree.query(pts)
            near = d2 < hw_route[i2] + 0.5
            z[near] = np.minimum(z[near], r["z"][i2[near]] - 0.03)
            side.append({"pts": np.c_[np.round(pts[:, 0] - ox, 2), np.round(pts[:, 1] - oy, 2), np.round(z - oz + 0.07, 2)].tolist(),
                         "width": round(w, 1), "material": mat, "highway": hwy})

    # ---- buildings
    bl = []
    church_spots = []
    if b_tree is not None and not area.is_empty:
        for gi in b_tree.query(area_tree_box):
            g, p = bpolys[gi]
            c = g.centroid
            dd, ii = rtree.query([c.x, c.y])
            if dd > W - 4 or sample_chunk[ii] != k:
                continue
            if g.geom_type == "MultiPolygon":
                g = max(g.geoms, key=lambda q: q.area)
            g = g.simplify(0.4, preserve_topology=True)
            if not g.is_valid or g.area < 6:
                continue
            ring = np.asarray(g.exterior.coords)[:-1]
            if len(ring) < 3:
                continue
            zs = H(ring[:, 0], ring[:, 1])
            spec = _building_style(p, g, urban[ii], kit, gi)
            roof_ring = g.buffer(spec.pop("overhang"), join_style=2)
            roof_ring = np.asarray(roof_ring.exterior.coords)[:-1] if roof_ring.geom_type == "Polygon" else ring
            bl.append({"ring": np.round(ring - [ox, oy], 2).tolist(), "roofRing": np.round(roof_ring - [ox, oy], 2).tolist(),
                       "z": round(float(zs.min()) - oz - 0.3, 2), **spec})
            if spec["kind"] == "church" and g.area > 120:
                mrr = np.asarray(g.minimum_rotated_rectangle.exterior.coords)[:-1]
                corner = mrr[int(h01("camp", gi) * 4)]
                church_spots.append((corner, float(zs.min())))

    # ---- instances
    inst: dict[str, list] = {}

    def put(asset, x, y, z, rot, scale=1.0):
        inst.setdefault(asset, []).append([round(float(x) - ox, 2), round(float(y) - oy, 2), round(float(z) - oz, 2), round(float(rot), 3),
                                           round(float(scale), 3)])

    blocked = _Blocker(r, rtree, hw_route, side, (ox, oy), b_tree, bpolys)
    g_rng = rng("chunk", k)
    veg = kit["vegetation"]
    in_area = lambda xs, ys: (rtree.query(np.c_[xs, ys])[0] <= W) & (sample_chunk[rtree.query(np.c_[xs, ys])[1]] == k)  # noqa: E731

    # Vineyards: real rows along the long axis of each vineyard polygon
    for idx, (g, p) in enumerate(landuse):
        if p.get("landuse") not in ("vineyard", "orchard") or not g.intersects(area):
            continue
        part = g.intersection(area).buffer(-1.2)
        if part.is_empty:
            continue
        mrr = np.asarray(g.minimum_rotated_rectangle.exterior.coords)[:4]
        e0, e1 = mrr[1] - mrr[0], mrr[2] - mrr[1]
        axis = e0 if np.hypot(*e0) >= np.hypot(*e1) else e1
        ang = math.atan2(axis[1], axis[0])
        u = np.array([math.cos(ang), math.sin(ang)])
        v = np.array([-u[1], u[0]])
        bx = np.asarray(part.envelope.exterior.coords)[:4]
        cen = np.asarray(part.centroid.coords[0])
        ext = np.hypot(*(bx[2] - bx[0])) / 2 + 5
        if p["landuse"] == "vineyard":
            sp, step, asset = veg["vineyard"]["rowSpacingM"], veg["vineyard"]["stepM"], veg["vineyard"]["asset"]
        else:
            sp, step = veg["orchard"]["spacingM"]
            asset = veg["orchard"]["asset"]
        phase = h01("rows", idx) * sp
        rows = np.arange(-ext + phase, ext, sp)
        along = np.arange(-ext, ext, step)
        R, A = np.meshgrid(rows, along, indexing="ij")
        P = cen + A.ravel()[:, None] * u + R.ravel()[:, None] * v
        if p["landuse"] == "vineyard":
            P2 = P + u * step  # row segment end must be inside too
            ok = shapely.contains_xy(part, P[:, 0], P[:, 1]) & shapely.contains_xy(part, P2[:, 0], P2[:, 1])
        else:
            ok = shapely.contains_xy(part, P[:, 0], P[:, 1])
        P = P[ok]
        if len(P) == 0:
            continue
        z = H(P[:, 0], P[:, 1])
        sc = 0.9 + 0.2 * g_rng.random(len(P))
        for (x, y), zz, s in zip(P, z, sc):
            put(asset, x, y, zz, ang if p["landuse"] == "vineyard" else g_rng.random() * math.tau, s if p["landuse"] == "orchard" else 1.0)

    # Forest and tree cover from WorldCover (class 10) inside the chunk area
    sp = veg["forest"]["spacingM"]
    if len(cx):
        fx = np.arange(x0, x1, sp)
        fy = np.arange(y0, y1, sp)
        FX, FY = np.meshgrid(fx, fy, indexing="ij")
        FX = FX.ravel() + (g_rng.random(FX.size) - 0.5) * sp * 0.8
        FY = FY.ravel() + (g_rng.random(FY.size) - 0.5) * sp * 0.8
        ok = in_area(FX, FY)
        FX, FY = FX[ok], FY[ok]
        cls = lc.sample(FX, FY).astype(int)
        t = cls == 10
        FX, FY = FX[t], FY[t]
        keep = ~blocked(FX, FY, 3.0)
        FX, FY = FX[keep], FY[keep]
        if len(FX):
            z = H(FX, FY)
            for x, y, zz in zip(FX, FY, z):
                put(_species(veg, x, zz, coast_x, kit, g_rng), x, y, zz, g_rng.random() * math.tau, 0.8 + 0.4 * g_rng.random())

    # Gardens: trees among buildings in residential / garden / park land use
    for idx, (g, p) in enumerate(landuse):
        lu = p.get("landuse") or p.get("leisure")
        if lu not in ("residential", "garden", "park", "cemetery", "farmyard", "grass") or not g.intersects(area):
            continue
        part = g.intersection(area)
        n = int(part.area * veg["garden"]["perM2"] * (2.5 if lu in ("park", "garden") else 1.0))
        if n <= 0:
            continue
        mnx, mny, mxx, mxy = part.bounds
        P = np.c_[mnx + g_rng.random(n * 3) * (mxx - mnx), mny + g_rng.random(n * 3) * (mxy - mny)]
        P = P[shapely.contains_xy(part, P[:, 0], P[:, 1])][:n]
        if len(P) == 0:
            continue
        P = P[~blocked(P[:, 0], P[:, 1], 2.5)]
        z = H(P[:, 0], P[:, 1])
        mix = veg["garden"]["mix"]
        if lu == "cemetery":
            mix = {"tree_cypress": 1.0}
        for (x, y), zz in zip(P, z):
            m = mix
            if coast_x is not None and coast_x - x < kit["coastline"]["pinewoodBandM"]:
                m = veg["coastalGarden"]["mix"]
            put(_pick(m, g_rng), x, y, zz, g_rng.random() * math.tau, 0.8 + 0.4 * g_rng.random())

    # Field edges: Romagna farmland is lined with hedgerows, oak/poplar rows and ditches
    edges = kit["vegetation"].get("fieldEdges", {})
    if edges:
        for idx, (g, p) in enumerate(landuse):
            if p.get("landuse") not in ("farmland", "meadow", "orchard", "vineyard") or not g.intersects(area):
                continue
            treat = _pick(edges["mix"], rng("edge", idx))
            if treat == "none":
                continue
            bd = g.boundary.intersection(area)
            for seg in getattr(bd, "geoms", [bd]):
                if seg.is_empty or seg.length < 8 or seg.geom_type != "LineString":
                    continue
                step = 4.0 if treat == "hedge_4m" else edges.get("treeStepM", 11.0)
                for t in np.arange(step / 2, seg.length, step):
                    if treat != "hedge_4m" and g_rng.random() < 0.3:
                        continue
                    q0, q1 = seg.interpolate(t), seg.interpolate(min(seg.length, t + 1.0))
                    x, y = q0.x, q0.y
                    if blocked(np.array([x]), np.array([y]), 1.5)[0]:
                        continue
                    ang = math.atan2(q1.y - q0.y, q1.x - q0.x)
                    put(treat, x, y, float(H(x, y)), ang if treat == "hedge_4m" else g_rng.random() * math.tau,
                        1.0 if treat == "hedge_4m" else 0.8 + 0.4 * g_rng.random())
        # WorldCover crop patches (no polygons): occasional tree rows on patch borders
        for (ia, jb) in {(int(math.floor(x_ / 170.0)), int(math.floor(y_ / 110.0))) for x_, y_ in zip(cx[::7], cy[::7])}:
            if h01("patchedge", ia, jb) > edges.get("patchShare", 0.3):
                continue
            treat = _pick({k_: v_ for k_, v_ in edges["mix"].items() if k_ != "none"}, rng("pe", ia, jb))
            x_line = ia * 170.0
            for yy in np.arange(jb * 110.0 + 3, (jb + 1) * 110.0, 4.0 if treat == "hedge_4m" else edges.get("treeStepM", 11.0)):
                if treat != "hedge_4m" and g_rng.random() < 0.3:
                    continue
                if not in_area(np.array([x_line]), np.array([yy]))[0] or int(lc.sample(np.array([x_line]), np.array([yy]))[0]) != 40:
                    continue
                if blocked(np.array([x_line]), np.array([yy]), 1.5)[0]:
                    continue
                put(treat, x_line, yy, float(H(x_line, yy)), math.pi / 2 if treat == "hedge_4m" else g_rng.random() * math.tau, 1.0)

    # Reeds along salt pans and ponds; flamingos in the salt pans
    for f_idx, (g, p) in enumerate(water):
        if not g.intersects(area):
            continue
        part = g.intersection(area)
        boundary = part.boundary
        if boundary.length > 0:
            n = int(boundary.length / veg["reeds"]["stepM"])
            for t in np.linspace(0, boundary.length, max(n, 0), endpoint=False):
                if g_rng.random() < (0.12 if p.get("water") == "salt_pond" else 0.5):
                    q = boundary.interpolate(t)
                    put("reeds", q.x + g_rng.normal(0, 0.6), q.y + g_rng.normal(0, 0.6), float(H(q.x, q.y)), g_rng.random() * math.tau,
                        0.7 + 0.6 * g_rng.random())
        if p.get("water") == "salt_pond":
            nfl = min(veg["flamingos"]["maxPerPond"], int(part.area / 10_000 * veg["flamingos"]["perHa"] * 6))
            if nfl:
                c = part.representative_point()
                for _ in range(nfl):
                    x, y = c.x + g_rng.normal(0, 12), c.y + g_rng.normal(0, 12)
                    if shapely.contains_xy(part, x, y):
                        put("flamingo", x, y, float(H(x, y)) - 0.25, g_rng.random() * math.tau, 0.9 + 0.2 * g_rng.random())
    # Poplar lines along canals, rivers and streams
    _poplars(kit, area, put, H, g_rng, blocked, waterways)

    # Campanili beside churches
    for (x, y), zb in church_spots:
        put("campanile", x, y, zb - 0.3, h01("camp", x, y) * math.tau, 1.0)

    # ---- road furniture along the course road
    _road_props(k, r, a, b, urban, H, put, kit, town_xy, town_idx, g_rng)
    for key in inst:
        inst[key].sort()
    return {"id": k, "origin": [ox, oy, oz], "terrain": terrain, "road": road, "sideRoads": side, "buildings": bl, "instances": inst}


def _poplars(kit, area, put, H, g_rng, blocked, waterways):
    v = kit["vegetation"]["canal"]
    for line in waterways:
        if not line.intersects(area):
            continue
        part = line.intersection(area)
        for seg in getattr(part, "geoms", [part]):
            if seg.length < 10 or seg.geom_type != "LineString":
                continue
            side = 1 if h01("side", seg.coords[0]) < 0.5 else -1
            for t in np.arange(0, seg.length, v["stepM"]):
                if g_rng.random() > v["share"]:
                    continue
                p0 = seg.interpolate(t)
                p1 = seg.interpolate(min(seg.length, t + 1))
                dx, dy = p1.x - p0.x, p1.y - p0.y
                L = math.hypot(dx, dy) or 1
                x, y = p0.x - dy / L * v["offsetM"] * side, p0.y + dx / L * v["offsetM"] * side
                if blocked(np.array([x]), np.array([y]), 2.5)[0]:
                    continue
                put(v["asset"], x, y, float(H(x, y)), g_rng.random() * math.tau, 0.85 + 0.3 * g_rng.random())


class _Blocker:
    """Rejects scatter points on the course road, side roads or inside buildings."""

    def __init__(self, r, rtree, hw, side, origin, b_tree, bpolys):
        self.rtree, self.hw = rtree, hw
        ox, oy = origin
        lines = [shapely.LineString(np.asarray(s["pts"])[:, :2] + [ox, oy]) for s in side if len(s["pts"]) >= 2]
        self.side = shapely.STRtree(lines) if lines else None
        self.side_w = np.array([s["width"] / 2 for s in side if len(s["pts"]) >= 2])
        self.b_tree, self.bpolys = b_tree, bpolys

    def __call__(self, x, y, margin):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        if len(x) == 0:
            return np.zeros(0, bool)
        d, i = self.rtree.query(np.c_[x, y])
        bad = d < self.hw[i] + margin + 1.5
        pts = shapely.points(x, y)
        if self.side is not None:
            pi, gi = self.side.query(pts, predicate="dwithin", distance=margin + 3.0)
            if len(pi):
                dd = shapely.distance(pts[pi], np.asarray(self.side.geometries)[gi])
                hit = dd < self.side_w[gi] + margin
                bad[pi[hit]] = True
        if self.b_tree is not None:
            pi, _ = self.b_tree.query(pts, predicate="dwithin", distance=margin * 0.6)
            bad[pi] = True
        return bad


def _pick(mix: dict, g) -> str:
    keys = sorted(mix)
    w = np.array([mix[k] for k in keys], float)
    return keys[int(np.searchsorted(np.cumsum(w / w.sum()), g.random()))]


def _species(veg, x, z, coast_x, kit, g):
    if coast_x is not None and coast_x - x < kit["coastline"]["pinewoodBandM"] and z < 15:
        return _pick(veg["forest"]["coastal"], g)
    mix = dict(veg["forest"]["inland"])
    hills = veg.get("hills", {})
    if z > hills.get("aboveM", 1e9):
        mix["tree_olive"] = hills.get("olive", 0)
        mix["tree_cypress"] = mix.get("tree_cypress", 0) + hills.get("cypress", 0)
    return _pick(mix, g)


def _building_style(p, g, is_urban, kit, gi):
    btype = str(p.get("building", "yes"))
    area = g.area
    h = float(p.get("_height") or 6.0)
    pal = kit["palette"]
    colours = list(pal["wall"].keys())
    weights = np.array([kit["palette"]["wallWeights"][c] for c in colours])
    col = colours[int(np.searchsorted(np.cumsum(weights / weights.sum()), h01("wall", gi)))]
    if btype in ("church", "chapel", "cathedral"):
        return {"kind": "church", "height": max(h, 10.0), "wall": "brick", "wallUpper": "brick", "roof": "roof_coppi", "roofType": "hipped",
                "pitchDeg": 20, "overhang": 0.3}
    if btype == "greenhouse":
        return {"kind": "greenhouse", "height": min(h, 4.0), "wall": "greenhouse", "wallUpper": "greenhouse", "roof": "greenhouse",
                "roofType": "gabled", "pitchDeg": 25, "overhang": 0.0}
    if btype in ("industrial", "warehouse", "retail", "commercial", "supermarket", "hangar") or (area > 900 and not is_urban):
        return {"kind": "industrial", "height": max(min(h, 12.0), 5.0), "wall": "concrete_panel", "wallUpper": "concrete_panel",
                "roof": "roof_flat", "roofType": "flat", "pitchDeg": 0, "overhang": 0.0}
    if btype in ("farm_auxiliary", "barn", "shed", "garage", "garages", "roof", "carport", "hut") or h < 3.6:
        brick = h01("barn", gi) < 0.55
        return {"kind": "outbuilding", "height": max(h, 2.8), "wall": "brick" if brick else f"stucco_{col}", "wallUpper": "brick" if brick else f"stucco_{col}",
                "roof": "roof_coppi", "roofType": "gabled" if area < 400 else "hipped", "pitchDeg": 18, "overhang": 0.25}
    if btype == "farm" or (not is_urban and h01("colonica", gi) < 0.25 and area > 90):
        # Casa colonica: brick or faded stucco farmhouse
        brick = h01("farmbrick", gi) < 0.4
        wall = "brick" if brick else f"facade_{col}"
        return {"kind": "farmhouse", "height": max(h, 7.0), "wall": wall, "wallUpper": wall, "roof": "roof_coppi", "roofType": "hipped",
                "pitchDeg": 22, "overhang": 0.45}
    ground = bool(is_urban and h >= 6.5)
    return {"kind": "house", "height": max(h, 4.5), "wall": f"facade_{col}_ground" if ground else f"facade_{col}", "wallUpper": f"facade_{col}",
            "roof": "roof_coppi", "roofType": "hipped" if area > 40 else "gabled", "pitchDeg": 22, "overhang": 0.45}


def _road_props(k, r, a, b, urban, H, put, kit, town_xy, town_idx, g):
    pr = kit["props"]
    s = r["s"]
    L = float(s[-1])
    hw = r["roadWidthM"] / 2
    for i in range(a, b + 1):
        if int(s[i] // CHUNK_M) != k and not (i == b and s[i] >= L - 1e-6):
            continue
        hd = r["headingRad"][i]
        ux, uy = math.sin(hd), math.cos(hd)  # travel direction (compass heading, x = east)
        nx, ny = uy, -ux  # right-hand normal
        x, y, z = r["x"][i], r["y"][i], r["z"][i]
        rural = not urban[i]
        bridge = bool(r["bridgeMask"][i])
        # Delineators every 50 m (rural), both sides
        if rural and not bridge and int(s[i] // pr["delineatorStepM"]) != int((s[i] - r["spacing"]) // pr["delineatorStepM"]):
            for side in (1, -1):
                off = hw[i] + 0.7
                px, py = x + nx * off * side, y + ny * off * side
                put("delineator", px, py, float(H(px, py)), -hd + (math.pi if side < 0 else 0), 1.0)
        # Guardrail: bridges and embankments (terrain falls away beside the road)
        if int(round(s[i] / r["spacing"])) % 4 == 0:  # every 20 m sample stride → place 4 m segments in runs
            for side in (1, -1):
                off = hw[i] + 0.5
                px, py = x + nx * off * side, y + ny * off * side
                drop = z - float(H(x + nx * (off + 4) * side, y + ny * (off + 4) * side))
                if bridge or drop > pr["guardrailEmbankmentM"]:
                    for kk in range(5):
                        qx, qy = px + ux * kk * 4, py + uy * kk * 4
                        put("guardrail_4m", qx, qy, z - 0.05, math.atan2(uy, ux) + (math.pi if side < 0 else 0), 1.0)
        # Streetlights in towns
        if not rural and int(s[i] // pr["streetlightStepM"]) != int((s[i] - r["spacing"]) // pr["streetlightStepM"]):
            off = hw[i] + 1.8
            px, py = x + nx * off, y + ny * off
            put("streetlight", px, py, float(H(px, py)), math.atan2(uy, ux) - math.pi / 2 + math.pi, 1.0)
        # Town entry signs (rural → urban transitions) with a 50 limit after them
        if i > 0 and urban[i] and not urban[i - 1] and len(town_xy):
            dd = np.hypot(town_xy[:, 0] - x, town_xy[:, 1] - y)
            t = town_idx[int(np.argmin(dd))]
            if t < 8:
                off = hw[i] + 1.2
                put(f"town_sign_{t}", x + nx * off, y + ny * off, float(H(x + nx * off, y + ny * off)), math.atan2(uy, ux) + math.pi, 1.0)
                put("sign_50", x + nx * off + ux * 30, y + ny * off + uy * 30, float(H(x + nx * off + ux * 30, y + ny * off + uy * 30)),
                    math.atan2(uy, ux) + math.pi, 1.0)
        # Race furniture: km boards every 10 km, crowd barriers at the start/finish
        if pr.get("raceKmBoards") and i > 0 and int(s[i] // 10_000) != int(s[i - 1] // 10_000):
            off = hw[i] + 1.0
            put("km_marker", x + nx * off, y + ny * off, float(H(x + nx * off, y + ny * off)), math.atan2(uy, ux) + math.pi, 1.6)
        if (s[i] < pr["raceBarrierFirstLastM"] or s[i] > L - pr["raceBarrierFirstLastM"]) and int(round(s[i] / r["spacing"])) % 2 == 0:
            for side in (1, -1):
                off = hw[i] + 0.4
                for kk in range(5):
                    px, py = x + nx * off * side + ux * kk * 2, y + ny * off * side + uy * kk * 2
                    put("race_barrier_2m", px, py, float(H(px, py)), math.atan2(uy, ux) + (math.pi if side < 0 else 0), 1.0)


def _far_terrain(pkg, H, lc, rtree, W, kit, sample_chunk, res=90.0):
    """Coarse textured far field (DEM far raster grid). Cells deep inside the near corridor are tagged with the chunk of
    their nearest route sample ("fill"): engines that stream chunks show a chunk's fill only while it is not loaded."""
    import rasterio

    with rasterio.open(pkg.path("corridor/dem_far.tif")) as ds:
        z = ds.read(1).astype(float)
        tr = ds.transform
    h, w = z.shape
    xs = tr.c + (np.arange(w + 1)) * tr.a
    ys = tr.f + (np.arange(h + 1)) * tr.e
    X, Y = np.meshgrid(xs, ys)
    from scipy.ndimage import map_coordinates

    Z = map_coordinates(z, [np.clip(np.arange(h + 1)[:, None] - 0.5, 0, h - 1) * np.ones((1, w + 1)),
                            np.ones((h + 1, 1)) * np.clip(np.arange(w + 1)[None, :] - 0.5, 0, w - 1)], order=1, mode="nearest")
    ccx, ccy = (X[:-1, :-1] + X[1:, 1:]) / 2, (Y[:-1, :-1] + Y[1:, 1:]) / 2
    d, nearest = rtree.query(np.c_[ccx.ravel(), ccy.ravel()])
    inner = (d < W - res).reshape(ccx.shape)
    fill = np.where(d < W - res, sample_chunk[nearest], -1)
    cls = lc.sample(ccx.ravel(), ccy.ravel()).astype(int).reshape(ccx.shape)
    wc = kit["terrain"]["worldcover"]
    mats = sorted(set(wc.values()))
    mi = {m: i for i, m in enumerate(mats)}
    cell_m = np.vectorize(lambda c: mi[wc.get(str(c), "grass_dry")])(cls)
    return {"res": res, "x0": float(xs[0]), "y0": float(ys[0]), "dx": float(tr.a), "dy": float(tr.e), "w": w, "h": h,
            "z": np.round(Z - 1.0, 1).ravel().tolist(), "skip": inner.ravel().astype(int).tolist(), "fill": fill.astype(int).tolist(), "mat": cell_m.ravel().tolist(), "materials": mats}
