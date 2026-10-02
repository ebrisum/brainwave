"""Unit tests for pipeline building blocks."""
import math

import numpy as np
import pytest

from gpx2course.geo import turning_radius
from gpx2course.gltf import Mesh, read_glb_json, write_glb
from gpx2course.ingest import parse_gpx, parse_tcx
from gpx2course.models.wind import f_rough, is_leaf_on, shelter_r
from gpx2course.stages.profile import ascent_with_hysteresis
from gpx2course.stages.structure import detect_climbs, detect_corners, detect_laps
from gpx2course.surfaces import classify, width_m


def test_wind_profile_matches_spec_vectors():
    assert 10 * f_rough(0.03) == pytest.approx(6.35, rel=0.01)
    assert 10 * f_rough(0.0002) == pytest.approx(9.0, rel=0.01)
    assert 10 * f_rough(0.30) == pytest.approx(3.4, rel=0.01)


def test_shelter_formula():
    assert shelter_r(30, 10, 0.0) == pytest.approx(0.15)  # x/H = 3 → f = 1 → u_min
    assert shelter_r(10, 10, 0.3) == pytest.approx(1 - 0.595 * 0.8)
    assert shelter_r(1000, 10, 0.3) == 1.0
    assert shelter_r(5, 0, 0.3) == 1.0


def test_leaf_season():
    assert is_leaf_on(7, 1, 52) and not is_leaf_on(1, 10, 52) and not is_leaf_on(7, 1, -40)


@pytest.mark.parametrize("surface,smooth,hw,expected", [
    ("asphalt", "good", "primary", 1.0), ("asphalt", "bad", "primary", 1.25), ("concrete", None, None, 1.1),
    ("paving_stones", None, None, 1.6), ("sett", None, None, 2.5), ("cobblestone", None, None, 2.5), ("fine_gravel", None, None, 2.0),
    ("gravel", None, None, 3.0), ("dirt", None, None, 3.0), (None, None, "residential", 1.0), (None, None, "cycleway", 1.0),
])
def test_crr_table(surface, smooth, hw, expected):
    assert classify(surface, smooth, hw)[1] == expected


def test_width():
    assert width_m({"width": "6.5"}) == 6.5
    assert width_m({"lanes": "2"}) == 6.0
    assert width_m({"highway": "cycleway"}) == 2.5


def test_hysteresis_ascent():
    z = np.array([0, 0.5, 0.2, 0.6, 0.1, 5, 4.5, 10])
    up, down = ascent_with_hysteresis(z, 1.0)
    assert up == pytest.approx(10.0)
    assert down == pytest.approx(0.0)


def test_climb_detection_merges_short_dips():
    s = np.arange(0, 4000, 5.0)
    z = np.where(s < 1000, 0, np.where(s < 3000, (s - 1000) * 0.06, 120.0))
    # a 100 m dip losing 3 m in the middle — merged
    dip = (s > 2000) & (s < 2100)
    z = z.astype(float)
    z[dip] = z[dip] - 3
    climbs = detect_climbs(s, z, np.gradient(z, s) * 100)
    assert len(climbs) == 1
    assert climbs[0]["lengthM"] == pytest.approx(2000, abs=60)
    assert climbs[0]["avgGradePct"] == pytest.approx(6, abs=0.3)


def test_climb_detection_splits_on_big_dip():
    s = np.arange(0, 4000, 5.0)
    z = np.interp(s, [0, 1000, 1100, 2200], [0, 60, 50, 110])
    climbs = detect_climbs(s, z, np.gradient(z, s) * 100)
    assert len(climbs) == 2


def _circle_track(radius, n_turns=1.0, spacing=5.0):
    L = 2 * math.pi * radius * n_turns
    t = np.arange(0, L, spacing) / radius
    return radius * np.sin(t), radius * (1 - np.cos(t))


def test_turning_radius():
    x, y = _circle_track(50)
    r = turning_radius(x, y, 5.0)
    assert np.median(r[5:-5]) == pytest.approx(50, rel=0.02)
    xs = np.arange(0, 500, 5.0)
    assert np.isinf(turning_radius(xs, np.zeros_like(xs), 5.0)[5:-5]).all()


def test_corner_and_lap_detection():
    # straight, hairpin of radius 12, straight back
    xs = list(np.arange(0, 300, 5.0))
    ys = [0.0] * len(xs)
    for a in np.linspace(0, math.pi, 8)[1:-1]:
        xs.append(300 + 12 * math.sin(a)); ys.append(12 - 12 * math.cos(a))
    xs += list(np.arange(300, 0, -5.0)); ys += [24.0] * len(np.arange(300, 0, -5.0))
    x, y = np.array(xs), np.array(ys)
    s = np.concatenate([[0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
    from gpx2course.geo import heading_compass, resample_uniform
    g, (xx, yy) = resample_uniform(s, 5.0, x, y)
    hd = heading_compass(xx, yy)
    corners = detect_corners(g, xx, yy, hd, turning_radius(xx, yy, 5.0))
    assert len(corners) == 1 and corners[0]["hairpin"]
    # Two laps of a 400 m square
    sq = np.array([[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]], float)
    pts = np.vstack([np.linspace(sq[i], sq[i + 1], 21)[:-1] for i in range(4)] * 2 + [sq[:1]])
    s2 = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
    g2, (x2, y2) = resample_uniform(s2, 5.0, pts[:, 0], pts[:, 1])
    laps = detect_laps(g2, x2, y2, heading_compass(x2, y2), min_lap=300)
    assert len(laps) == 2


def test_gpx_and_tcx_parsing():
    gpx = b"""<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
<wpt lat="52.0" lon="5.0"><name>Feed</name><type>aid</type></wpt>
<rte><name>R</name><rtept lat="52.0" lon="5.0"/><rtept lat="52.001" lon="5.0"/></rte></gpx>"""
    rc = parse_gpx(gpx, "x")
    assert len(rc.lat) == 2 and rc.pois[0]["name"] == "Feed" and rc.name == "R"
    tcx = b"""<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"><Courses><Course><Name>C</Name>
<Track><Trackpoint><Position><LatitudeDegrees>52</LatitudeDegrees><LongitudeDegrees>5</LongitudeDegrees></Position><AltitudeMeters>3</AltitudeMeters></Trackpoint>
<Trackpoint><Position><LatitudeDegrees>52.001</LatitudeDegrees><LongitudeDegrees>5</LongitudeDegrees></Position><AltitudeMeters>4</AltitudeMeters></Trackpoint></Track>
</Course></Courses></TrainingCenterDatabase>"""
    rc = parse_tcx(tcx, "x")
    assert len(rc.lat) == 2 and rc.ele[1] == 4


def test_glb_round_trip():
    pos = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32)
    glb = write_glb([Mesh("t", "road_asphalt", pos, np.array([0, 1, 2], np.uint32))], {"road_asphalt": {"baseColor": [0.2, 0.2, 0.2]}})
    j = read_glb_json(glb)
    assert j["asset"]["version"] == "2.0" and j["materials"][0]["extras"]["materialId"] == "road_asphalt"
    assert len(glb) % 4 == 0


def test_roadsnap_rebuilds_sparse_route_on_the_network():
    """A planner export with one point per ~150 m around an L-bend must follow the road, not cut the corner."""
    import shapely

    from gpx2course.geo import LocalFrame
    from gpx2course.providers.osm import Feature
    from gpx2course.roadsnap import needs_snap, snap

    frame = LocalFrame(44.25, 12.35)
    # Road network (local metres): an L (east 600 m, then north 600 m) plus a diagonal shortcut track that a
    # straight line between the sparse points would hug.
    def feat(xy, hw):
        lat, lon = frame.to_latlon(np.array([p[0] for p in xy]), np.array([p[1] for p in xy]))
        return Feature(shapely.LineString(np.c_[lon, lat]), {"highway": hw})
    roads = [feat([(0, 0), (300, 0), (600, 0)], "tertiary"), feat([(600, 0), (600, 300), (600, 600)], "tertiary"),
             feat([(300, 0), (600, 300)], "footway")]
    x = np.array([0.0, 160, 330, 470, 600, 600, 600])
    y = np.array([0.0, 4, -3, 5, 150, 330, 600])
    assert needs_snap(x, y)
    sx, sy, src, share = snap(x, y, roads, frame)
    assert share == 1.0
    L = float(np.sum(np.hypot(np.diff(sx), np.diff(sy))))
    assert L == pytest.approx(1200, abs=15)  # along the L, not the 1000 m-ish corner cut
    # Every output vertex lies on the L (≤ 1 m), i.e. the footway shortcut was not taken
    line = shapely.LineString([(0, 0), (600, 0), (600, 600)])
    assert max(line.distance(shapely.Point(p)) for p in zip(sx, sy)) < 1.0
    assert src[0] == 0 and src[-1] == pytest.approx(len(x) - 1)
    assert not needs_snap(np.arange(0, 500, 5.0), np.zeros(100))


def test_overture_rows_become_osm_style_features():
    import shapely

    from gpx2course.providers.overture import _buildings, _land_use, _segments, _water

    seg = {"id": "s1", "subtype": "road", "class": "tertiary", "names": {"primary": "Via Salara"}, "geometry": shapely.LineString([(0, 0), (1, 0)]),
           "road_surface": [{"value": "paved", "between": None}], "road_flags": [{"values": ["is_bridge"], "between": [0.25, 0.5]}],
           "width_rules": None}
    f = _segments([seg])
    assert [x.tags.get("bridge") for x in f] == [None, "yes", None]
    assert f[1].geom.length == pytest.approx(0.25) and all(x.tags["highway"] == "tertiary" and x.tags["name"] == "Via Salara" for x in f)
    b = _buildings([{"id": "b1", "class": "church", "height": 21.5, "num_floors": None, "roof_shape": "hipped", "roof_color": None,
                     "facade_color": None, "facade_material": None, "roof_material": None, "geometry": shapely.box(0, 0, 1, 1)}])[0]
    assert b.tags == {"building": "church", "overture:id": "b1", "height": "21.5", "roof:shape": "hipped"}
    w = _water([{"id": "w", "subtype": "water", "class": "salt_pond", "names": {"primary": "Saline di Cervia"}, "geometry": shapely.box(0, 0, 1, 1)}])[0]
    assert w.tags == {"natural": "water", "water": "salt_pond", "name": "Saline di Cervia"}
    lu = _land_use([{"id": "l", "subtype": "horticulture", "class": "vineyard", "names": None, "geometry": shapely.box(0, 0, 1, 1)}])[0]
    assert lu.tags["landuse"] == "vineyard"


def test_kit_textures_tile_and_are_deterministic():
    from gpx2course.gamekit import textures as tx

    a = tx.pnoise(64, 8, 3)
    assert np.array_equal(a, tx.pnoise(64, 8, 3))
    # Periodic: the wrap-around step is no larger than a typical interior step
    assert np.abs(a[:, 0] - a[:, -1]).mean() < 3 * np.abs(np.diff(a, axis=1)).mean()
    rgb, h, r = tx.coppi(64, 1)
    assert rgb.shape == (64, 64, 3) and 0 <= rgb.min() and rgb.max() <= 1.5 and 0 < r <= 1


def test_superelevation_follows_turn_direction_and_road_class():
    from gpx2course.roadgeom import cross_slope_dz, superelevation

    sp = 5.0
    n = 400
    # Straight north, then a right-hand bend R = 150 m, then straight east
    heading = np.r_[np.zeros(150), np.linspace(0, math.pi / 2, 100), np.full(150, math.pi / 2)]
    radius = np.r_[np.full(150, np.inf), np.full(100, 150.0), np.full(150, np.inf)]
    bank = superelevation(heading, radius, ["secondary"] * n, sp)
    assert abs(bank[50]) < 0.05 and abs(bank[350]) < 0.05  # crowned on the straights
    assert 1.4 < bank[200] <= math.degrees(math.atan(0.07)) + 1e-6  # right bend → right edge lower, ≤ 7 %
    left = superelevation(-heading, radius, ["secondary"] * n, sp)
    assert left[200] == pytest.approx(-bank[200])
    assert np.allclose(superelevation(heading, radius, ["residential"] * n, sp), 0)  # town streets stay crowned
    assert cross_slope_dz(3.5, 0.0) == pytest.approx(-0.07) and cross_slope_dz(-3.5, 0.0) == pytest.approx(-0.07)
    t = math.tan(math.radians(4.0))
    assert cross_slope_dz(3.5, 4.0) == pytest.approx(-3.5 * t) and cross_slope_dz(-3.5, 4.0) == pytest.approx(3.5 * t)


def _straight_route(n=400, sp=5.0, width=6.0, highway="tertiary", surface=0):
    s = np.arange(n) * sp
    return {"s": s, "x": np.zeros(n), "y": s.copy(), "z": np.zeros(n), "headingRad": np.zeros(n), "roadWidthM": np.full(n, width),
            "bridgeMask": np.zeros(n, bool), "surfaceCode": np.full(n, surface), "highway": np.array([highway] * n, object), "spacing": sp}


def test_road_defects_are_deterministic_on_the_road_and_scale_with_wear():
    from gpx2course.gamekit import roadside

    r = _straight_route(2000)  # 10 km
    urban = np.zeros(2000, bool)
    worn = roadside.defects_for(r, range(2000), urban)
    assert worn == roadside.defects_for(r, range(2000), urban)  # deterministic
    # chunking-independent: two halves give the same defects as the whole
    assert roadside.defects_for(r, range(1000), urban) + roadside.defects_for(r, range(1000, 2000), urban) == worn
    for d in worn:
        if d["kind"] != "edgeBreak":
            half = abs(d["wid"] / 2 * math.cos(d["rot"])) + abs(d["len"] / 2 * math.sin(d["rot"]))
            assert abs(d["off"]) + half <= 3.0 - 0.1 + 1e-6, d
    count = roadside.summary(worn)
    assert 15 <= count["pothole"] <= 50 and count["patch"] > count["pothole"] and count["edgeBreak"] > 0
    good = roadside.summary(roadside.defects_for(_straight_route(2000, highway="primary"), range(2000), urban))
    assert good["pothole"] < count["pothole"] / 3 and good["edgeBreak"] == 0
    # porphyry setts and bridges: none
    assert roadside.defects_for(_straight_route(400, surface=4), range(400), np.ones(400, bool)) == []
    rb = _straight_route(400)
    rb["bridgeMask"][:] = True
    assert roadside.defects_for(rb, range(400), np.zeros(400, bool)) == []


def test_guardrail_runs_follow_drops_and_water_and_ignore_blips():
    from gpx2course.gamekit import roadside

    r = _straight_route(400)

    def H(x, y):  # an embankment on the right between y = 500 and 800 m, a 5 m blip at y = 1500
        x, y = np.asarray(x, float), np.asarray(y, float)
        return np.where((x > 0) & (((y > 500) & (y < 800)) | ((y > 1500) & (y < 1505))), -3.0, 0.0)

    runs = roadside.guardrail_runs(r, H, np.zeros(400, bool))
    assert [(sd, round(a), round(b)) for sd, a, b in runs] == [(1, 505, 800)]
    # water within 4 m of the left edge from y = 1000 to 1200
    runs = roadside.guardrail_runs(r, H, np.zeros(400, bool), lambda xs, ys, d: (np.asarray(xs) < 0) & (np.asarray(ys) >= 1000) & (np.asarray(ys) <= 1200))
    assert (-1, 1000.0, 1205.0) in [(sd, a, b) for sd, a, b in runs]
    # placed as 4 m segments on a global grid: chunks [0, 650) and [650, 1300) together cover the run exactly once
    put_log = []
    put = lambda *a: put_log.append(a)  # noqa: E731
    run = [(1, 505.0, 800.0)]
    n = roadside.place_guardrails(run, r, 0, 650, H, put) + roadside.place_guardrails(run, r, 650, 1300, H, put)
    assert n == int((800 - 505) // 4) and len({round(p[2], 2) for p in put_log}) == n
    assert all(p[1] > 3.0 for p in put_log)  # right side, outside the edge


def test_tree_setback_rule_from_kit():
    from gpx2course.gamekit import roadside

    rr = roadside.rules({"rules": {"treeSetbackM": 7.0, "guardrail": {"waterM": 3.0}}})
    assert rr["treeSetbackM"] == 7.0 and rr["guardrail"]["waterM"] == 3.0 and rr["guardrail"]["embankmentM"] == 1.5
    assert roadside.rules({})["treeSetbackM"] == 5.0
    sh = roadside.shoulder_widths(_straight_route(10, highway="secondary"), range(10), np.r_[np.zeros(5, bool), np.ones(5, bool)], rr)
    assert sh[:5] == [0.8] * 5 and sh[5:] == [0.0] * 5


def test_roadfx_shapes_and_surface_heights():
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "blender", "game"))
    import roadfx

    road = {"s": [0.0, 5.0, 10.0, 15.0], "x": [0.0] * 4, "y": [0.0, 5.0, 10.0, 15.0], "z": [1.0] * 4, "heading": [0.0] * 4,
            "width": [6.0] * 4, "bankDeg": [0.0] * 4}
    cl = roadfx.Centreline(road)
    x, y, z = cl.point(7.5, 2.0)
    assert (x, y) == pytest.approx((2.0, 7.5)) and z == pytest.approx(1.0 + 0.04 - 0.04)  # right of travel = east; 2 % crown
    pot = {"kind": "pothole", "s": 7.0, "off": 1.5, "len": 0.5, "wid": 0.4, "rot": 0.3, "depth": -0.05, "seed": 7}
    patch = {"kind": "patch", "s": 3.0, "off": -1.0, "len": 2.0, "wid": 1.0, "rot": 0.0, "depth": 0.003, "seed": 3}
    crack = {"kind": "crackOpen", "s": 11.0, "off": 0.0, "len": 4.0, "wid": 0.015, "rot": 0.0, "depth": -0.008, "seed": 5}
    edge = {"kind": "edgeBreak", "s": 1.0, "off": 3.0, "len": 10.0, "wid": 0.3, "rot": 0.0, "depth": -0.04, "seed": 9}
    assert roadfx.pothole_outline(pot) == roadfx.pothole_outline(pot)  # seeded
    surf = roadfx.Surface([pot, patch, crack, edge], lambda s: 3.0)
    assert surf.height(7.0, 1.5) < -0.035 and surf.material(7.0, 1.5) == "pothole"  # pothole bottom
    assert surf.height(7.0, 0.5) == 0.0 and not surf.fine(7.0, 0.5)  # clean asphalt, coarse mesh is enough
    assert surf.height(3.0, -1.0) == pytest.approx(0.003) and surf.material(3.0, -1.0) == "asphalt_patch"
    ys = [p[1] for p in roadfx.crack_path(crack)]
    assert max(abs(v) for v in ys) < 0.1  # meanders but stays near its line
    assert min(surf.height(11.0, o / 1000) for o in range(-60, 61)) < -0.004  # a groove somewhere across the crack line
    assert surf.height(6.0, 2.98) == pytest.approx(-0.04) and surf.height(6.0, -2.98) == 0.0  # right edge crumbled only
    assert 0 < roadfx.stone_height(0.31, 0.12) <= 0.016 or roadfx.stone_height(0.33, 0.14) > 0  # stones exist


def test_hero_chunk_selection():
    from gpx2course.gamekit.run import parse_hero

    assert parse_hero(None, 90470) == []
    assert parse_hero("km:44-46.5", 90470) == [88, 89, 90, 91, 92]
    assert parse_hero("84-86,170", 90470) == [84, 85, 86, 170]
    assert parse_hero("km:0-0.2", 90470) == [0]
    assert len(parse_hero("all", 90470)) == 182  # one past the manifest distance: the route may end a few metres later
