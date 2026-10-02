"""Snap-to-road for sparse route files (planner exports such as Openrunner/Komoot/Strava routes: one point every
100–1500 m). A straight line between such points cuts every bend and misses roundabouts, so before resampling we
rebuild the geometry on the road network: HMM map matching (Newson & Krumm 2009) with candidates on nearby road
edges, emissions from the point-to-road distance and transitions from |network distance − straight distance|,
then the shortest network path between consecutive chosen candidates. Works on any OSM-style road Feature list
(OSM, Overture). Pure numpy/scipy/shapely; deterministic.
"""
from __future__ import annotations

import math

import numpy as np
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

# Road classes a bike course can use, with a mild preference for proper roads over paths
PENALTY = {"motorway": None, "motorway_link": None, "steps": None, "construction": None, "proposed": None, "bridleway": None,
           "footway": 1.6, "path": 1.4, "pedestrian": 1.3, "track": 1.3, "service": 1.15, "cycleway": 1.0}


def needs_snap(x: np.ndarray, y: np.ndarray, sparse_spacing_m: float = 30.0) -> bool:
    d = np.hypot(np.diff(x), np.diff(y))
    d = d[d > 0]
    return len(d) > 0 and (float(np.median(d)) > sparse_spacing_m or float(np.mean(d > 60.0)) > 0.25)


class RoadGraph:
    def __init__(self, roads, frame):
        coords, edges_u, edges_v, w, eid_tags = {}, [], [], [], []
        seg_a, seg_b, seg_e = [], [], []

        def node(p):
            k = (round(p[0], 2), round(p[1], 2))
            i = coords.get(k)
            if i is None:
                i = coords[k] = len(coords)
            return i

        for f in roads:
            hw = f.tags.get("highway")
            if hw is None:
                continue
            pen = PENALTY.get(hw, 1.0)
            if pen is None:
                continue
            g = f.geom_xy(frame)
            for part in getattr(g, "geoms", [g]):
                co = np.asarray(part.coords)[:, :2]
                ids = [node(p) for p in co]
                for k in range(len(co) - 1):
                    if ids[k] == ids[k + 1]:
                        continue
                    L = float(np.hypot(*(co[k + 1] - co[k])))
                    edges_u.append(ids[k])
                    edges_v.append(ids[k + 1])
                    w.append(L * pen)
                    seg_a.append(co[k])
                    seg_b.append(co[k + 1])
                    seg_e.append(len(w) - 1)
        self.xy = np.array(list(coords.keys()), dtype=np.float64).reshape(-1, 2)
        n = len(self.xy)
        self.u = np.array(edges_u, dtype=np.int64)
        self.v = np.array(edges_v, dtype=np.int64)
        self.w = np.array(w)
        self.a = np.array(seg_a).reshape(-1, 2)
        self.b = np.array(seg_b).reshape(-1, 2)
        self.len = np.hypot(*(self.b - self.a).T) if len(self.a) else np.zeros(0)
        self.G = coo_matrix((np.r_[self.w, self.w], (np.r_[self.u, self.v], np.r_[self.v, self.u])), shape=(n, n)).tocsr()
        self.tree = shapely.STRtree(shapely.linestrings(np.stack([self.a, self.b], axis=1))) if len(self.a) else None

    def candidates(self, px, py, radius, k):
        """Up to k nearest edges within radius: (edge, t∈[0,1], dist, point)."""
        if self.tree is None:
            return []
        idx = self.tree.query(shapely.Point(px, py), predicate="dwithin", distance=radius)
        if len(idx) == 0:
            return []
        a, b = self.a[idx], self.b[idx]
        ab = b - a
        L2 = np.maximum((ab**2).sum(1), 1e-9)
        t = np.clip(((np.array([px, py]) - a) * ab).sum(1) / L2, 0, 1)
        q = a + ab * t[:, None]
        d = np.hypot(q[:, 0] - px, q[:, 1] - py)
        order = np.argsort(d)
        out, seen = [], set()
        for j in order:
            # Keep at most one candidate per road position cluster (adjacent edges of the same way)
            key = (round(q[j, 0] / 8), round(q[j, 1] / 8))
            if key in seen:
                continue
            seen.add(key)
            out.append((int(idx[j]), float(t[j]), float(d[j]), q[j]))
            if len(out) >= k:
                break
        return out


def _route_cost(g: RoadGraph, c1, c2, dist_rows, src_index):
    """Network distance from candidate c1 to c2 (both on edges), using precomputed Dijkstra rows from c1's ends."""
    e1, t1, _, _ = c1
    e2, t2, _, _ = c2
    if e1 == e2:
        return abs(t2 - t1) * g.len[e1], None
    best, how = math.inf, None
    ends1 = ((g.u[e1], t1 * g.len[e1]), (g.v[e1], (1 - t1) * g.len[e1]))
    ends2 = ((g.u[e2], t2 * g.len[e2]), (g.v[e2], (1 - t2) * g.len[e2]))
    for n1, d1 in ends1:
        row = dist_rows[src_index[n1]]
        for n2, d2 in ends2:
            c = d1 + row[n2] + d2
            if c < best:
                best, how = c, (n1, n2)
    return best, how


def snap(x: np.ndarray, y: np.ndarray, roads, frame, sigma_m: float = 15.0, beta_m: float = 60.0, radius_m: float = 45.0,
         k: int = 6, step_m: float = 5.0):
    """Returns (xs, ys, src) — dense road-following geometry and, per output vertex, the fractional index into the
    input points (for carrying elevation/time across). Points without a road nearby keep the straight segment."""
    g = RoadGraph(roads, frame)
    n = len(x)
    if g.tree is None or n < 2:
        return x, y, np.arange(n, dtype=float), 0.0
    cands = [g.candidates(x[i], y[i], radius_m, k) for i in range(n)]
    # Viterbi in log space; chains restart where no candidate exists or transitions are impossible
    score = [None] * n
    back = [None] * n
    hows = [None] * n
    prev = None
    for i in range(n):
        C = cands[i]
        if not C:
            prev = None
            continue
        emis = np.array([-(c[2] ** 2) / (2 * sigma_m**2) for c in C])
        if prev is None:
            score[i] = emis
            back[i] = np.full(len(C), -1)
            prev = i
            continue
        P = cands[prev]
        straight = math.hypot(x[i] - x[prev], y[i] - y[prev])
        limit = 3.0 * straight + 400.0
        srcs = sorted({int(g.u[c[0]]) for c in P} | {int(g.v[c[0]]) for c in P})
        rows = dijkstra(g.G, directed=False, indices=srcs, limit=limit)
        src_index = {s: r for r, s in enumerate(srcs)}
        trans = np.full((len(P), len(C)), -np.inf)
        how = [[None] * len(C) for _ in P]
        for a, cp in enumerate(P):
            for b, cc in enumerate(C):
                d, hw = _route_cost(g, cp, cc, rows, src_index)
                if math.isfinite(d):
                    trans[a, b] = -abs(d - straight) / beta_m
                    how[a][b] = hw
        tot = score[prev][:, None] + trans
        best_prev = np.argmax(tot, axis=0)
        best = tot[best_prev, np.arange(len(C))]
        if not np.isfinite(best).any():
            # Disconnected: restart the chain here
            score[i] = emis
            back[i] = np.full(len(C), -1)
        else:
            score[i] = best + emis
            back[i] = best_prev
            hows[i] = (prev, how)
        prev = i
    # Backtrack every chain
    chosen = [-1] * n
    i = n - 1
    while i >= 0:
        if score[i] is None:
            i -= 1
            continue
        j = int(np.argmax(score[i]))
        while True:
            chosen[i] = j
            if back[i][j] < 0 or hows[i] is None:
                break
            p = hows[i][0]
            j = int(back[i][j])
            i = p
        i -= 1
    # Build geometry
    out_x, out_y, out_src = [x[0]], [y[0]], [0.0]
    matched_pairs = 0

    def emit(px, py, src):
        if math.hypot(px - out_x[-1], py - out_y[-1]) > 0.05:
            out_x.append(px)
            out_y.append(py)
            out_src.append(src)

    last = None
    for i in range(n):
        if chosen[i] < 0:
            emit(x[i], y[i], float(i))
            last = None
            continue
        c = cands[i][chosen[i]]
        if last is not None and hows[i] is not None and hows[i][0] == last:
            cp = cands[last][chosen[last]]
            hw = hows[i][1][chosen[last]][chosen[i]]
            pts = _path_points(g, cp, c, hw)
            L = np.r_[0, np.cumsum(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1])))]
            for (px, py), l in zip(pts[1:], L[1:]):
                emit(px, py, last + (i - last) * (l / max(L[-1], 1e-9)))
            matched_pairs += 1
        else:
            emit(c[3][0], c[3][1], float(i))
        last = i
    xs, ys, src = np.array(out_x), np.array(out_y), np.array(out_src)
    return xs, ys, src, matched_pairs / max(n - 1, 1)


def _path_points(g: RoadGraph, c1, c2, how):
    e1, t1, _, q1 = c1
    e2, t2, _, q2 = c2
    if how is None:  # same edge
        return np.array([q1, q2])
    n1, n2 = how
    # Shortest node path n1 → n2 (single-source Dijkstra with predecessors; small limit around the pair)
    straight = float(np.hypot(*(g.xy[n2] - g.xy[n1])))
    _, pred = dijkstra(g.G, directed=False, indices=[n1], limit=3.0 * straight + 600.0, return_predecessors=True)
    pred = pred[0]
    path = [n2]
    while path[-1] != n1:
        p = pred[path[-1]]
        if p < 0:
            return np.array([q1, q2])
        path.append(int(p))
    path.reverse()
    return np.vstack([q1, g.xy[path], q2])
