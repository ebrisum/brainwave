import json
import os
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RIDEPREP_COURSES_DIR", str(tmp_path))
    monkeypatch.setenv("GPX2COURSE_OFFLINE", "1")
    monkeypatch.setenv("GPX2COURSE_WORKERS", "2")
    monkeypatch.delenv("REDIS_URL", raising=False)
    import importlib

    from fastapi.testclient import TestClient

    import api.jobs
    import api.app
    importlib.reload(api.jobs)
    importlib.reload(api.app)
    return TestClient(api.app.app)


def test_upload_build_events_and_files(client):
    gpx = (ROOT / "fixtures" / "urban_cobbles_15k.gpx").read_bytes()
    r = client.post("/courses", files={"file": ("urban.gpx", gpx, "application/gpx+xml")}, data={"tier": "quick", "targets": "web"})
    assert r.status_code == 202
    bid = r.json()["buildId"]
    # Server-sent events until closed
    events = []
    with client.stream("GET", f"/courses/{bid}/events") as s:
        for line in s.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
                if events[-1]["event"] == "closed":
                    break
    kinds = [e["event"] for e in events]
    assert "stage_start" in kinds and "course_id" in kinds and kinds[-1] == "closed"
    assert "error" not in kinds, events[-3:]
    cid = next(e["courseId"] for e in events if e["event"] == "course_id")
    m = client.get(f"/courses/{cid}/manifest").json()
    assert m["courseId"] == cid
    assert client.get(f"/courses/{cid}/files/route.bin").status_code == 200
    assert client.get(f"/courses/{cid}/files/../../etc/passwd").status_code in (400, 404)
    assert client.get("/courses").json()[0]["courseId"] == cid
    # Dedup
    r2 = client.post("/courses", files={"file": ("urban.gpx", gpx, "application/gpx+xml")}, data={"tier": "quick"})
    assert r2.json()["status"] == "ready" and r2.json()["courseId"] == cid
    # Weather refresh
    w = client.post(f"/courses/{cid}/weather", json={"weather": "manual", "manual": {"u10": 7, "dirDeg": 200}})
    assert w.status_code == 200 and w.json()["mode"] == "manual"


def test_rejects_bad_files(client):
    r = client.post("/courses", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400
