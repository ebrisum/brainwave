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
