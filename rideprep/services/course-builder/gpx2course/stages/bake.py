"""Stage 9 — bake: per-500 m chunk assets in parallel (headless Blender if available, else the Python lite baker)."""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib import resources
from pathlib import Path

import numpy as np
import shapely
from scipy.spatial import cKDTree

from ..litebake import BAKER_VERSION, bake_chunk, bake_far_terrain
from ..pipeline import BuildContext, stable_json
from .common import CorridorRaster, chunk_ranges, load_route

NL_BBOX = (3.2, 50.75, 7.3, 53.7)
BLENDER_SCRIPT = Path(__file__).resolve().parents[2] / "blender" / "bake_chunk.py"


def blender_path() -> str | None:
    return os.environ.get("BLENDER_BIN") or shutil.which("blender")


def _bake_one(args):
    spec_path, out_dir, mode = args
    spec = json.loads(Path(spec_path).read_text())
    if mode == "blender":
        cmd = [blender_path(), "-b", "--factory-startup", "--python", str(BLENDER_SCRIPT), "--", "--input", spec_path, "--out", out_dir]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if res.returncode != 0:
            raise RuntimeError(f"blender failed for chunk {spec['id']}: {res.stderr[-2000:]}")
        return spec["id"], [f"c{spec['id']}_lod{k}.glb" for k in range(3)]
    mats = json.loads(resources.files("gpx2course").joinpath("data/materials.json").read_text())
    return spec["id"], bake_chunk(spec, Path(out_dir), mats)


def build_chunk_specs(ctx: BuildContext) -> list[dict]:
    r = load_route(ctx)
    t = ctx.config.tunables
    dem = CorridorRaster(ctx, "dem")
    L = float(r["s"][-1])
    sp = r["spacing"]
    # Terrain beside the road for verges: sample 4 m beyond each edge and take the mean
    hw = r["roadWidthM"] / 2 + 4
    nx, ny = np.cos(r["headingRad"]), -np.sin(r["headingRad"])
    tz = (dem.sample(r["x"] + nx * hw, r["y"] + ny * hw) + dem.sample(r["x"] - nx * hw, r["y"] - ny * hw)) / 2
    o = ctx.read_json("origin.json")
    red = NL_BBOX[0] <= o["lon"] <= NL_BBOX[2] and NL_BBOX[1] <= o["lat"] <= NL_BBOX[3]
    highway = r["highway"]
    bridge = np.array([(b or "") not in ("", "no") for b in r["bridge"]])
    cyc = np.array([h == "cycleway" for h in highway])
    # Assign each near-zone building to the chunk of its nearest route sample
    tree = cKDTree(np.c_[r["x"], r["y"]])
    q = ctx.read_json("quick/buildings.json")["buildings"]
    by_chunk: dict[int, list] = {}
    for b in q:
        if not b["near"]:
            continue
        c = np.mean(np.array(b["ring"]), axis=0)
        _, i = tree.query(c)
        k = min(int(r["s"][i] // t.chunk_length_m), int(math.ceil(L / t.chunk_length_m)) - 1)
        by_chunk.setdefault(k, []).append(b)
    specs = []
    for k, s0, s1 in chunk_ranges(L, t.chunk_length_m):
        a = max(0, int(math.floor(s0 / sp)) - 1)
        b = min(r["count"] - 1, int(math.ceil(s1 / sp)) + 1)
        sl = slice(a, b + 1)
        origin = [round(float(r["x"][a])), round(float(r["y"][a])), round(float(r["z"][a]))]
        specs.append({"id": k, "sStart": s0, "sEnd": s1, "origin": origin, "redCycleways": red, "seed": k,
                      "route": {"s": np.round(r["s"][sl], 2).tolist(), "x": np.round(r["x"][sl], 3).tolist(), "y": np.round(r["y"][sl], 3).tolist(),
                                "z": np.round(r["z"][sl], 3).tolist(), "heading": np.round(r["headingRad"][sl], 5).tolist(),
                                "width": r["roadWidthM"][sl].astype(int).tolist(), "surface": r["surfaceCode"][sl].astype(int).tolist(),
                                "bridge": bridge[sl].tolist(), "cycleway": cyc[sl].tolist(), "terrainZ": np.round(tz[sl], 2).tolist()},
                      "buildings": by_chunk.get(k, []), "lodDistancesM": [150, 600]})
    return specs


def write_index(ctx: BuildContext, specs, status, version, mode) -> list[dict]:
    """chunks/index.json, rewritten as chunks finish so clients can stream them in ride order during the bake."""
    chunks = [{"id": sp["id"], "sStart": sp["sStart"], "sEnd": sp["sEnd"], "origin": sp["origin"], "status": status[sp["id"]],
               "lod": [f"chunks/c{sp['id']}_lod{l}.glb" for l in range(3)], "lodDistancesM": sp["lodDistancesM"]} for sp in specs]
    ctx.write_json("chunks/index.json", {"baker": version, "mode": mode, "chunks": chunks})
    return chunks


def run(ctx: BuildContext) -> list[str]:
    specs = build_chunk_specs(ctx)
    out_dir = ctx.path("chunks")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ".keys").mkdir(exist_ok=True)
    (out_dir / ".inputs").mkdir(exist_ok=True)
    mode = "blender" if blender_path() and ctx.options.tier == "full" and os.environ.get("GPX2COURSE_LITE_BAKE") != "1" else "lite"
    if mode == "lite":
        ctx.warn("Blender not found; chunks baked with the built-in lite baker (no textures, procedural vegetation stays instanced)",
                 code="lite_bake")
    version = BAKER_VERSION if mode == "lite" else "blender-1"
    todo, status = [], {}
    for sp in specs:
        key = hashlib.sha256((stable_json(sp) + version).encode()).hexdigest()
        kp = out_dir / ".keys" / f"c{sp['id']}.txt"
        files = [f"c{sp['id']}_lod{l}.glb" for l in range(3)]
        if kp.exists() and kp.read_text() == key and all((out_dir / f).exists() for f in files):
            status[sp["id"]] = "baked"
            continue
        ip = out_dir / ".inputs" / f"c{sp['id']}.json"
        ip.write_text(json.dumps(sp, separators=(",", ":")))
        todo.append((sp, key))
        status[sp["id"]] = "pending"
    ctx.write_json("chunks/status.json", {"chunks": status})
    write_index(ctx, specs, status, version, mode)
    from .validate import write_partial_manifest
    write_partial_manifest(ctx)
    workers = max(1, min(ctx.options.workers, len(todo), os.cpu_count() or 1))
    done = 0
    # Test hook: simulate the build being killed after N chunks (tests/test_pipeline.py::test_resume)
    kill_after = int(os.environ.get("GPX2COURSE_KILL_AFTER_CHUNKS", "0"))

    def check_kill():
        if kill_after and done >= kill_after:
            raise KeyboardInterrupt(f"simulated kill after {done} chunks")

    keys = {sp["id"]: key for sp, key in todo}
    args = [(str(out_dir / ".inputs" / f"c{sp['id']}.json"), str(out_dir), mode) for sp, _ in todo]  # ride order
    if todo:
        if workers > 1:
            import multiprocessing as mp
            with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("fork")) as ex:
                futs = [ex.submit(_bake_one, a) for a in args]
                for f in as_completed(futs):
                    cid, _ = f.result()
                    (out_dir / ".keys" / f"c{cid}.txt").write_text(keys[cid])
                    status[cid] = "baked"
                    done += 1
                    ctx.write_json("chunks/status.json", {"chunks": status})
                    write_index(ctx, specs, status, version, mode)
                    ctx.progress_frac(done / len(todo), f"chunk {cid}")
                    if kill_after and done >= kill_after:
                        for f2 in futs:
                            f2.cancel()
                        check_kill()
        else:
            for a in args:
                cid, _ = _bake_one(a)
                (out_dir / ".keys" / f"c{cid}.txt").write_text(keys[cid])
                status[cid] = "baked"
                done += 1
                ctx.write_json("chunks/status.json", {"chunks": status})
                write_index(ctx, specs, status, version, mode)
                ctx.progress_frac(done / len(todo), f"chunk {cid}")
                check_kill()
    # Far field terrain
    import rasterio
    idx = ctx.read_json("corridor/index.json")
    with rasterio.open(ctx.path("corridor/dem_far.tif")) as ds:
        zf = ds.read(1).astype(np.float64)
    ctx.write_bytes("far_terrain.glb", bake_far_terrain(zf, idx["far"]["bounds"], (0, 0, 0)))
    chunks = write_index(ctx, specs, status, version, mode)
    outs = ["chunks/index.json", "far_terrain.glb"] + [f for c in chunks for f in c["lod"]]
    return outs
