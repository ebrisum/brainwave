"""Stage 10 — export-web: meshopt-compressed chunks (gltfpack, if installed) and the web streaming manifest."""
from __future__ import annotations

import shutil
import subprocess

from ..pipeline import BuildContext


def run(ctx: BuildContext) -> list[str]:
    idx = ctx.read_json("chunks/index.json")
    gltfpack = shutil.which("gltfpack")
    if not gltfpack:
        ctx.warn("gltfpack not installed; web chunks are uncompressed glTF (install meshoptimizer's gltfpack for meshopt/KTX2)",
                 code="no_gltfpack")
    outs = []
    chunks = []
    for c in idx["chunks"]:
        lods = []
        for f in c["lod"]:
            if gltfpack:
                dst = "web/" + f.replace(".glb", ".meshopt.glb")
                ctx.path(dst).parent.mkdir(parents=True, exist_ok=True)
                cmd = [gltfpack, "-i", str(ctx.path(f)), "-o", str(ctx.path(dst)), "-cc", "-kn", "-km"]
                if shutil.which("toktx") or shutil.which("basisu"):
                    cmd.append("-tc")
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    lods.append(dst)
                    outs.append(dst)
                    continue
                ctx.warn(f"gltfpack failed on {f}: {res.stderr.strip()[:200]}", code="gltfpack_failed")
            lods.append(f)
        chunks.append({**c, "lod": lods})
    web = {"version": 1, "compression": "meshopt" if gltfpack else "none", "textures": "ktx2" if gltfpack and (shutil.which("toktx") or shutil.which("basisu")) else "none",
           "streaming": {"aheadM": 3000, "behindM": 500}, "chunks": chunks, "farField": "far_terrain.glb", "terrain": "terrain.json",
           "instances": "instances.bin", "quick": {"buildings": "quick/buildings.json", "roads": "quick/roads.json", "water": "quick/water.json"}}
    ctx.write_json("web/manifest.json", web)
    return ["web/manifest.json"] + outs
