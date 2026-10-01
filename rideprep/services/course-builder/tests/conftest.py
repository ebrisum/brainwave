import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures"
FIXTURE_NAMES = ["urban_cobbles_15k", "forest_climb_40k", "polder_coastal_60k", "perf_180k"]
WORKERS = str(min(4, os.cpu_count() or 1))


def run_cli(*args, env=None, check=True):
    e = {**os.environ, "GPX2COURSE_OFFLINE": "1", **(env or {})}
    res = subprocess.run([sys.executable, "-m", "gpx2course", *map(str, args)], capture_output=True, text=True, env=e,
                         cwd=Path(__file__).resolve().parents[1])
    if check and res.returncode != 0:
        raise AssertionError(f"gpx2course {' '.join(map(str, args))} failed:\n{res.stdout[-3000:]}\n{res.stderr[-3000:]}")
    return res


def build(gpx: Path, out: Path, *extra, env=None, check=True):
    return run_cli("build", gpx, "--out", out, "--offline", "--workers", WORKERS, "--progress", "json",
                   "--event-start", "2026-07-05T09:00:00+02:00", *extra, env=env, check=check)


def package_dir(out: Path) -> Path:
    dirs = [d for d in out.iterdir() if d.is_dir() and d.name.startswith("c_")]
    assert len(dirs) == 1, dirs
    return dirs[0]


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    """Build every fixture once per session (offline, both targets)."""
    out = {}
    for name in FIXTURE_NAMES:
        d = tmp_path_factory.mktemp(name)
        res = build(FIXTURES / f"{name}.gpx", d)
        events = [json.loads(l) for l in res.stdout.splitlines() if l.startswith("{")]
        out[name] = (package_dir(d), events)
    return out
