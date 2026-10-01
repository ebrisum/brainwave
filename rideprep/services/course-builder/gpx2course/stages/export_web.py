"""Stage 10 — export-web: meshopt-compressed chunks (gltfpack, if installed) and the web streaming manifest."""
from __future__ import annotations

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor

from ..pipeline import BuildContext


def run(ctx: BuildContext) -> list[str]:
    idx = ctx.read_json("chunks/index.json")
    gltfpack = shutil.which("gltfpack")
    if not gltfpack:
        ctx.warn("gltfpack not installed; web chunks are uncompressed glTF (install meshoptimizer's gltfpack for meshopt/KTX2)",
                 code="no_gltfpack")
    outs = []
    packed: dict[str, str] = {}
    if gltfpack:
        ktx = bool(shutil.which("toktx") or shutil.which("basisu"))
        ctx.path("web/chunks").mkdir(parents=True, exist_ok=True)

        def pack(f: str):
            dst = "web/" + f.replace(".glb", ".meshopt.glb")
            cmd = [gltfpack, "-i", str(ctx.path(f)), "-o", str(ctx.path(dst)), "-cc", "-kn", "-km"] + (["-tc"] if ktx else [])
            res = subprocess.run(cmd, capture_output=True, text=True)
            return f, dst, res

        files = [f for c in idx["chunks"] for f in c["lod"]]
        with ThreadPoolExecutor(max_workers=max(1, ctx.options.workers)) as ex:
            for k, (f, dst, res) in enumerate(ex.map(pack, files)):
                if res.returncode == 0:
                    packed[f] = dst
                    outs.append(dst)
                else:
                    ctx.warn(f"gltfpack failed on {f}: {res.stderr.strip()[:200]}", code="gltfpack_failed")
                if k % 30 == 0:
                    ctx.progress_frac(k / len(files), "meshopt")
    chunks = [{**c, "lod": [packed.get(f, f) for f in c["lod"]]} for c in idx["chunks"]]
    web = {"version": 1, "compression": "meshopt" if gltfpack else "none", "textures": "ktx2" if gltfpack and (shutil.which("toktx") or shutil.which("basisu")) else "none",
           "streaming": {"aheadM": 3000, "behindM": 500}, "chunks": chunks, "farField": "far_terrain.glb", "terrain": "terrain.json",
           "instances": "instances.bin", "quick": {"buildings": "quick/buildings.json", "roads": "quick/roads.json", "water": "quick/water.json"}}
    ctx.write_json("web/manifest.json", web)
    return ["web/manifest.json"] + outs
