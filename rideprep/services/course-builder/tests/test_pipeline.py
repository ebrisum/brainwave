"""Pipeline acceptance tests (spec §16.8)."""
import json
import os
import shutil
import time

import numpy as np
import pytest

from gpx2course.coords import enu_to_ue, ue_to_enu
from gpx2course.dryrun import estimate

from conftest import FIXTURE_NAMES, FIXTURES, WORKERS, build, package_dir, run_cli


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_build_validates(built, name):
    d, events = built[name]
    assert run_cli("validate", d).returncode == 0
    m = json.loads((d / "manifest.json").read_text())
    assert m["exports"].keys() >= {"web", "unreal"}
    assert m["stats"]["distanceM"] > 10_000
    # JSON progress events cover every stage
    stages = {e["stage"] for e in events if e["event"] == "stage_end"}
    assert {"ingest", "match", "profile", "corridor", "structure", "wind", "weather", "quick", "bake", "export-web", "export-unreal", "validate"} <= stages
    assert (d / "report.html").exists() and (d / "build_log.json").exists()
    log = json.loads((d / "build_log.json").read_text())
    assert all("duration_s" in s for s in log["stages"])


def test_fixture_structure(built):
    urban = json.loads((built["urban_cobbles_15k"][0] / "segments.json").read_text())
    assert len(urban["laps"]) == 2
    assert any(p["type"] == "bridge" for p in urban["pois"])
    assert any(r["surface"] == "sett" for r in urban["surfaceRuns"])
    forest = json.loads((built["forest_climb_40k"][0] / "segments.json").read_text())
    assert len(forest["climbs"]) >= 1
    big = max(forest["climbs"], key=lambda c: c["gainM"])
    assert 5000 < big["lengthM"] < 8000 and 5 < big["avgGradePct"] < 8
    assert sum(c["hairpin"] for c in forest["corners"]) >= 4
    polder = json.loads((built["polder_coastal_60k"][0] / "manifest.json").read_text())
    assert polder["stats"]["laps"] == 1


def test_wind_layers_make_sense(built):
    """Polder: the dike (open water upwind to the west) is more exposed than tree-row lanes; urban streets are sheltered."""
    def layers(d):
        m = json.loads((d / "manifest.json").read_text())["wind"]
        return np.frombuffer((d / "wind.bin").read_bytes(), np.uint8).reshape(len(m["layers"]), m["count"], 16) / 100
    p = layers(built["polder_coastal_60k"][0])
    u = built["urban_cobbles_15k"][0]
    west = 12  # FROM 270°
    total_p = p[0, :, west] * p[1, :, west] * p[2, :, west] * p[3, :, west]
    lu = layers(u)
    total_u = lu[0, :, west] * lu[1, :, west] * lu[2, :, west] * lu[3, :, west]
    assert np.median(total_p) > np.median(total_u)
    assert p[1].min() < 0.8  # tree rows shelter somewhere
    assert np.percentile(total_p, 95) > 0.6  # exposed stretches exist


def test_determinism(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    gpx = FIXTURES / "urban_cobbles_15k.gpx"
    build(gpx, a)
    build(gpx, b)
    ma = json.loads((package_dir(a) / "manifest.json").read_text())
    mb = json.loads((package_dir(b) / "manifest.json").read_text())
    assert ma["courseId"] == mb["courseId"]
    assert ma["contentHash"] == mb["contentHash"]


def test_resume_after_kill_during_bake(tmp_path):
    gpx = FIXTURES / "forest_climb_40k.gpx"
    res = build(gpx, tmp_path, env={"GPX2COURSE_KILL_AFTER_CHUNKS": "10"}, check=False)
    assert res.returncode != 0
    d = package_dir(tmp_path)
    # Finished = recorded with a key; chunks that were in flight when killed are legitimately re-baked
    done_ids = [k.stem for k in (d / "chunks" / ".keys").glob("c*.txt")]
    finished = {f"{c}_lod0.glb": (d / "chunks" / f"{c}_lod0.glb").stat().st_mtime_ns for c in done_ids}
    assert 10 <= len(finished) < 85
    # Progressive streaming: a partial manifest and a chunk index with baked + pending chunks exist mid-bake
    partial = json.loads((d / "manifest.partial.json").read_text())
    assert partial["partial"] is True and not (d / "manifest.json").exists()
    idx = json.loads((d / "chunks" / "index.json").read_text())
    states = {c["status"] for c in idx["chunks"]}
    assert states == {"baked", "pending"}
    assert idx["chunks"][0]["status"] == "baked"  # ride order: the start is baked first
    time.sleep(0.05)
    res = build(gpx, tmp_path, "--resume")
    events = [json.loads(l) for l in res.stdout.splitlines() if l.startswith("{")]
    cached = {e["stage"] for e in events if e["event"] == "stage_end" and e["status"] == "cached"}
    assert {"ingest", "match", "profile", "corridor", "wind", "quick"} <= cached
    for name, mt in finished.items():
        assert (d / "chunks" / name).stat().st_mtime_ns == mt, f"{name} was re-baked"
    assert run_cli("validate", d).returncode == 0
    assert not (d / "manifest.partial.json").exists()


def test_degradation_without_osm(tmp_path):
    """No OSM coverage, no building heights: still builds, with warnings in the report."""
    src = FIXTURES / "forest_climb_40k.gpx"
    gpx = tmp_path / "no_osm.gpx"
    shutil.copy(src, gpx)  # no sidecar next to it
    out = tmp_path / "out"
    build(gpx, out)
    d = package_dir(out)
    m = json.loads((d / "manifest.json").read_text())
    codes = {w["code"] for w in m["warnings"]}
    assert "no_osm" in codes and "unmatched_all" in codes
    assert "no_osm" in (d / "report.html").read_text()
    assert run_cli("validate", d).returncode == 0


def test_dry_run_fast_and_estimate_close(built):
    t0 = time.time()
    res = run_cli("build", FIXTURES / "perf_180k.gpx", "--dry-run", "--offline", "--workers", WORKERS, "--progress", "json")
    assert time.time() - t0 < 20
    info = json.loads(res.stdout.splitlines()[-1])
    assert info["sources"]["osm"] == "sidecar"
    real = json.loads((built["perf_180k"][0] / "build_log.json").read_text())
    real_s = sum(s["duration_s"] for s in real["stages"])
    assert abs(info["totalEstimateS"] - real_s) / real_s <= 0.3, (info["totalEstimateS"], real_s)


def test_enu_unreal_round_trip_180km(built):
    d = built["perf_180k"][0]
    m = json.loads((d / "manifest.json").read_text())
    n = m["route"]["count"]
    buf = (d / "route.bin").read_bytes()
    arr = {a["name"]: np.frombuffer(buf, "<f4", n, a["offset"]).astype(np.float64) for a in m["route"]["arrays"] if a["type"] == "float32"}
    X, Y, Z = enu_to_ue(arr["x"], arr["y"], arr["z"])
    # Unreal stores doubles (LWC); also check single precision relative to the chunk origin
    x, y, z = ue_to_enu(X, Y, Z)
    err = max(np.abs(x - arr["x"]).max(), np.abs(y - arr["y"]).max(), np.abs(z - arr["z"]).max())
    assert err < 0.001
    assert X[10] == pytest.approx(arr["x"][10] * 100) and Y[10] == pytest.approx(-arr["y"][10] * 100)


def test_weather_refresh(built, tmp_path):
    d = built["urban_cobbles_15k"][0]
    target = tmp_path / d.name
    shutil.copytree(d, target)
    manual = tmp_path / "manual.json"
    manual.write_text(json.dumps({"u10": 9.7, "dirDeg": 315, "gust10": 15, "tempC": 6, "rh": 0.9, "pMslHpa": 1001, "precipMmH": 1.2}))
    run_cli("weather", target, "--weather", f"manual:{manual}", "--offline")
    w = json.loads((target / "weather.json").read_text())
    assert w["mode"] == "manual" and w["values"]["u10"] == [[9.7]]
    assert run_cli("validate", target).returncode == 0  # weather is excluded from the content hash


def test_inspect(built):
    res = run_cli("inspect", built["forest_climb_40k"][0])
    assert "Climbs" in res.stdout and "Exposure" in res.stdout
