"""`gpx2course game <package> --kit <name>`: kit (cached) → chunk specs → parallel Blender bake → meshopt → package.

Package layout added:
  game/index.json            kit, chunk list (glb + instances), far field, attribution
  game/kit/                  kit.glb, kit.blend, materials.json, assets.json, kit.json, textures/
  game/chunks/g<id>.glb      terrain/road/side roads/buildings (no images; material names = kit material ids)
  game/chunks/g<id>.inst.json  kit asset → [[x, y, z, rotZ, scale]] (chunk-local ENU metres)
  game/far.glb               textured far field
  game/shots/*.jpg           optional Cycles preview shots (--render)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import KITS_DIR, default_kit_for, load_kit
from .build_kit import build as build_textures

HERE = Path(__file__).resolve()
BLENDER_DIR = HERE.parents[2] / "blender" / "game"
GEN_SOURCES = [HERE.with_name("textures.py"), HERE.with_name("build_kit.py"), BLENDER_DIR / "build_kit_meshes.py", BLENDER_DIR / "kitlib.py"]

# Default preview shots: (name, s fraction or metres, mode, extra args)
DEFAULT_SHOTS = [("start", 260.0, "chase", [])]


def blender_bin() -> str | None:
    return os.environ.get("BLENDER_BIN") or shutil.which("blender")


def run_blender(script: Path, args: list[str], log: Path | None = None) -> None:
    b = blender_bin()
    if not b:
        raise RuntimeError("Blender not found (set BLENDER_BIN or put blender on PATH); the game-art path needs Blender 4.2+")
    cmd = [b, "-b", "--factory-startup", "--python", str(script), "--", *args]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if log:
        log.write_text(res.stdout[-200_000:] + "\n--- stderr ---\n" + res.stderr[-50_000:])
    if res.returncode != 0:
        raise RuntimeError(f"blender {script.name} failed: {res.stderr[-1500:] or res.stdout[-1500:]}")


def kit_hash(name: str) -> str:
    h = hashlib.sha256((KITS_DIR / (name.replace("-", "_") + ".json")).read_bytes())
    for p in GEN_SOURCES:
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def ensure_kit(name: str, cache_dir: Path, log=print) -> Path:
    d = cache_dir / "kits" / f"{name}-{kit_hash(name)}"
    if (d / "kit.glb").exists() and (d / "materials.json").exists():
        return d
    tmp = d.with_suffix(".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"kit {name}: generating textures")
    build_textures(name, tmp)
    log(f"kit {name}: building meshes in Blender")
    run_blender(BLENDER_DIR / "build_kit_meshes.py", ["--kit", str(tmp)], tmp / "blender.log")
    shutil.rmtree(d, ignore_errors=True)
    tmp.rename(d)
    return d


def gltfpack_bin() -> str | None:
    return os.environ.get("GLTFPACK") or shutil.which("gltfpack")


def compress(glb: Path) -> bool:
    gp = gltfpack_bin()
    if not gp:
        return False
    tmp = glb.with_suffix(".pack.glb")
    # -kv: keep UVs although chunk materials carry no images (engines bind kit textures); -vtf: float UVs (metre-scale
    # UVs would swim if quantised); -vp 16: ~1 cm positions; keep names, materials and extras
    res = subprocess.run([gp, "-i", str(glb), "-o", str(tmp), "-cc", "-kn", "-km", "-kv", "-ke", "-vtf", "-vp", "16"], capture_output=True, text=True)
    if res.returncode != 0 or not tmp.exists():
        return False
    tmp.replace(glb)
    return True


def build_game(pkg: Path, kit_name: str | None = None, workers: int = 4, cache_dir: Path | None = None, shots: list | None = None,
               chunk_ids: list[int] | None = None, log=print, unreal: bool | None = None) -> dict:
    from .prep import prepare

    t0 = time.time()
    pkg = Path(pkg)
    man = json.loads((pkg / "manifest.json").read_text())
    kit_name = kit_name or default_kit_for(man.get("style", {}), (man["origin"]["lat"], man["origin"]["lon"]))
    if not kit_name:
        raise SystemExit("no kit matches this course's region; pass --kit (available: " + ", ".join(p.stem for p in KITS_DIR.glob("*.json")) + ")")
    kit = load_kit(kit_name)
    if unreal is None:
        unreal = (pkg / "unreal").exists()
    cache_dir = Path(cache_dir or os.environ.get("GPX2COURSE_CACHE", Path.home() / ".cache" / "gpx2course"))
    kdir = ensure_kit(kit_name, cache_dir, log)
    game = pkg / "game"
    chunks_dir = game / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    # Kit copy inside the package (self-contained for web/Unreal)
    kout = game / "kit"
    if kout.exists():
        shutil.rmtree(kout)
    shutil.copytree(kdir, kout, ignore=shutil.ignore_patterns("blender.log", "*.blend1"))
    specs = cache_dir / "game_specs" / man["courseId"]
    log(f"game: preparing chunk specs ({kit_name})")
    doc = prepare(pkg, kit, specs, chunk_ids=chunk_ids)
    ids = [c["id"] for c in doc["chunks"]]
    log(f"game: baking {len(ids)} chunks in Blender ({workers} workers)")
    groups = [ids[w::workers] for w in range(workers) if ids[w::workers]]

    def bake(gi_ids):
        gi, part = gi_ids
        extra = ["--far"] if gi == 0 else []
        run_blender(BLENDER_DIR / "bake_game_chunk.py", ["--kit", str(kdir), "--specs", str(specs), "--out", str(chunks_dir),
                                                          "--ids", ",".join(map(str, part)), *extra], specs / f"bake_{gi}.log")

    with ThreadPoolExecutor(len(groups)) as ex:
        list(ex.map(bake, enumerate(groups)))
    if (chunks_dir / "far.glb").exists():
        (chunks_dir / "far.glb").replace(game / "far.glb")
    # Unreal's glTF importer reads neither meshopt nor quantised attributes: keep uncompressed copies for the editor import
    ue = game / "unreal"
    if unreal:
        ue.mkdir(exist_ok=True)
        for i in ids:
            shutil.copyfile(chunks_dir / f"g{i}.glb", ue / f"g{i}.glb")
        if (game / "far.glb").exists():
            shutil.copyfile(game / "far.glb", ue / "far.glb")
    lu = game / "landuse"
    lu.mkdir(exist_ok=True)
    for i in ids:
        if (specs / f"lu{i}.png").exists():
            shutil.copyfile(specs / f"lu{i}.png", lu / f"g{i}.png")
    packed = 0
    with ThreadPoolExecutor(workers) as ex:
        packed = sum(ex.map(compress, [chunks_dir / f"g{i}.glb" for i in ids] + [game / "far.glb"]))
    chunks = []
    for c in doc["chunks"]:
        spec = json.loads((specs / f"g{c['id']}.json").read_text())
        (chunks_dir / f"g{c['id']}.inst.json").write_text(json.dumps({"origin": spec["origin"], "instances": spec["instances"]},
                                                                     separators=(",", ":")))
        entry = {**c, "glb": f"game/chunks/g{c['id']}.glb", "instances": f"game/chunks/g{c['id']}.inst.json"}
        if unreal:
            entry["glbUnreal"] = f"game/unreal/g{c['id']}.glb"
        if c.get("landuseBounds"):
            entry["landuse"] = f"game/landuse/g{c['id']}.png"
        chunks.append(entry)
    index = {"version": 1, "kit": {"name": kit["name"], "label": kit["label"], "version": kit["version"], "dir": "game/kit",
                                   "glb": "game/kit/kit.glb", "materials": "game/kit/materials.json", "assets": "game/kit/assets.json"},
             "chunkM": doc["chunkM"], "gridM": doc["gridM"], "halfWidthM": doc["halfWidthM"], "far": "game/far.glb",
             "compression": "meshopt" if packed else "none", "uv": "metres; texture repeat = 1/tileM (materials.json)",
             "landuseClasses": doc["landuseClasses"], "farUnreal": "game/unreal/far.glb" if unreal else None,
             "chunks": chunks, "attribution": ["© OpenStreetMap contributors, Overture Maps Foundation (ODbL)",
                                               "Copernicus DEM GLO-30 © DLR/Airbus, provided under COPERNICUS by the EU and ESA",
                                               "ESA WorldCover 2021 (CC BY 4.0)", "Procedural art kit: RidePrep (CC0)"]}
    if shots:
        index["shots"] = [f"game/shots/{name}.jpg" for name, *_ in shots]
    (game / "index.json").write_text(json.dumps(index, indent=1))
    man["game"] = {"index": "game/index.json", "kit": kit["name"]}
    (pkg / "manifest.json").write_text(json.dumps(man, indent=1))
    if shots:
        sdir = game / "shots"
        sdir.mkdir(exist_ok=True)
        for name, s, mode, extra in shots:
            log(f"game: rendering {name} ({mode} at {s / 1000:.1f} km)")
            run_blender(BLENDER_DIR / "render_course.py", ["--kit", str(kdir), "--specs", str(specs), "--s", str(s), "--mode", mode,
                                                           "--out", str(sdir / f"{name}.jpg"), *extra], specs / f"render_{name}.log")
    log(f"game: done in {time.time() - t0:.0f} s → {game}")
    return index


def parse_shots(spec: str | None, length_m: float) -> list:
    """'name:s_km:mode[:back]' comma list, or 'default'."""
    if not spec:
        return []
    if spec == "default":
        return DEFAULT_SHOTS
    out = []
    for item in spec.split(","):
        parts = item.split(":")
        name, s_km, mode = parts[0], float(parts[1]), parts[2] if len(parts) > 2 else "cockpit"
        extra = ["--look-back"] if len(parts) > 3 and parts[3] == "back" else []
        out.append((name, min(s_km * 1000, length_m - 1), mode, extra))
    return out


if __name__ == "__main__":
    build_game(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None)
