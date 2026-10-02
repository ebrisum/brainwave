"""Build a kit's texture set and engine-neutral material table (step 1 of the kit; Blender builds the meshes).

Output (<out>/):
  textures/<material>_albedo.(jpg|png), <material>_normal.png
  materials.json  — {materialId: {albedo, normal, tileM, roughness, metallic, alpha, alphaCutoff, emissive}}
Deterministic: the same kit JSON always yields byte-identical textures.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import load_kit
from . import textures as tx

TEX_PX = 1024


def _seed(*k) -> int:
    return int.from_bytes(hashlib.sha256(json.dumps(k).encode()).digest()[:4], "little")


def build_textures(kit: dict, out: Path, px: int = TEX_PX) -> dict:
    tdir = out / "textures"
    mats: dict[str, dict] = {}

    def put(mid, spec, rgb=None, h=None, rough=None, strength=4.0):
        files = tx.save(tdir, mid, rgb, h, strength) if rgb is not None else {}
        m = {"tileM": spec.get("tileM"), "roughness": spec.get("roughness", rough if rough is not None else 0.9),
             "metallic": spec.get("metallic", 0.0)}
        if "color" in spec and rgb is None:
            m["color"] = spec["color"]
        for k in ("alpha", "alphaCutoff", "emissive"):
            if k in spec:
                m[k] = spec[k]
        m.update(files)
        mats[mid] = m

    for mid, spec in kit["materials"].items():
        g, seed = spec["gen"], _seed(kit["name"], mid)
        if g == "flat":
            put(mid, spec)
        elif g == "asphalt":
            rgb, h, r = tx.asphalt(px, seed, spec["base"], spec.get("worn", 0))
            put(mid, spec, rgb, h, r, 6.0)
        elif g == "stucco":
            rgb, h, r = tx.stucco(px // 2, seed, spec["color"])
            put(mid, spec, rgb, h, r, 3.0)
        elif g == "setts":
            rgb, h, r = tx.setts(px, seed, spec["color"])
            put(mid, spec, rgb, h, r, 5.0)
        elif g == "ground":
            rgb, h, r = tx.ground(px, seed, [(a, tx.hexrgb(c)) for a, c in spec["stops"]], spec.get("detail", 4) * px / 512,
                                  spec.get("roughness", 0.95), spec.get("rows", 0), spec.get("rowDark", 0.75))
            put(mid, spec, rgb, h, r, 3.0)
        elif g == "water":
            rgb, h, r = tx.water(px // 2, seed, spec["color"], spec["shallow"])
            put(mid, spec, rgb, h, r, 1.5)
        elif g == "bricks":
            rgb, h, r = tx.bricks(px, seed, spec["color"], spec.get("mortar", "#cfc3ad"))
            put(mid, spec, rgb, h, r, 5.0)
        elif g == "coppi":
            rgb, h, r = tx.coppi(px, seed, spec["color"])
            put(mid, spec, rgb, h, r, 8.0)
        elif g == "bark":
            rgb, h, r = tx.bark(px // 2, seed, spec["color"])
            put(mid, spec, rgb, h, r, 6.0)
        elif g == "leaf":
            put(mid, spec, tx.leaf_card(px // 2, seed, spec["color"], spec["kind"]))
        elif g == "foliage":
            rgb, h, r = tx.foliage_dense(px // 2, seed, spec["color"])
            put(mid, spec, rgb, h, r, 4.0)
        elif g == "signs":
            put(mid, spec, tx.sign_atlas(px, kit.get("towns", [])))
        else:
            raise ValueError(f"unknown texture generator {g!r} for {mid}")
    # Regional facades: plain stucco, window bays and ground-floor bays per wall colour
    pal = kit["palette"]
    bay_w, bay_h = kit.get("facades", {}).get("bayM", [4, 3])
    for cname, col in pal["wall"].items():
        seed = _seed(kit["name"], "wall", cname)
        rgb, h, r = tx.stucco(px // 2, seed, col)
        put(f"stucco_{cname}", {"tileM": 3, "roughness": 0.9}, rgb, h, r, 3.0)
        rgb, h, r = tx.facade_bay(px // 2, seed, col, pal["shutter"], pal["frame"])
        put(f"facade_{cname}", {"tileM": [bay_w, bay_h], "roughness": 0.85}, rgb, h, r, 6.0)
        rgb, h, r = tx.facade_bay(px // 2, seed + 1, col, pal["shutter"], pal["frame"], ground=True)
        put(f"facade_{cname}_ground", {"tileM": [bay_w, bay_h], "roughness": 0.85}, rgb, h, r, 6.0)
    return mats


def build(kit_name: str, out: Path, px: int = TEX_PX) -> Path:
    kit = load_kit(kit_name)
    out.mkdir(parents=True, exist_ok=True)
    mats = build_textures(kit, out, px)
    doc = {"kit": kit["name"], "version": kit["version"], "label": kit["label"], "materials": mats,
           "wallColours": list(kit["palette"]["wall"].keys()), "wallWeights": kit["palette"]["wallWeights"]}
    (out / "materials.json").write_text(json.dumps(doc, indent=1))
    (out / "kit.json").write_text(json.dumps(kit, indent=1))
    return out


if __name__ == "__main__":
    import sys

    print(build(sys.argv[1], Path(sys.argv[2])))
