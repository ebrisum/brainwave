"""Unreal hand-off bundle: a ready-to-open render project with a built course inside.

    python3 tools/unreal_bundle.py <course package dir> --out <dir> [--name RidePrep_EmiliaRomagna] [--zip]

The package must have been built with `gpx2course game` (Unreal copies in game/unreal/, optionally the hero road from
`--hero`). The bundle:

  <name>/RidePrepRender.uproject      Blueprint-only project (Python, Editor Scripting, PCG, Movie Render Queue)
  <name>/Config/                      renderer settings (Lumen, Nanite, VSM, virtual textures), surface types,
                                      RidePrepAssetOverrides.example.json (swap kit trees/props for Fab assets)
  <name>/Scripts/                     build_level.py (one click) + import_game_level.py
  <name>/Course/                      the course: manifest, route, game/index.json, kit, Unreal chunk GLBs, hero road,
                                      instances, land-use masks
  <name>/Rider/                       rider_road.glb, rider_tt.glb (+ .blend sources when given --rider-blend)
  <name>/README.md                    the step-by-step guide (docs/UNREAL_GUIDE.md)
  <name>/ATTRIBUTION.txt              data credits

--zip writes <name>.zip and, when the course has hero road chunks, <name>_hero.zip (unzip both into one folder).
"""
from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UNREAL = REPO / "apps" / "unreal"


def copy(src: Path, dst: Path) -> int:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return src.stat().st_size


def bundle(pkg: Path, out: Path, name: str, rider_blend: Path | None = None) -> Path:
    pkg = Path(pkg)
    index = json.loads((pkg / "game" / "index.json").read_text())
    root = Path(out) / name
    if root.exists():
        shutil.rmtree(root)
    size = 0
    # Project
    size += copy(UNREAL / "RenderProject" / "RidePrepRender.uproject", root / "RidePrepRender.uproject")
    for f in (UNREAL / "RenderProject" / "Config").iterdir():
        size += copy(f, root / "Config" / f.name)
    size += copy(UNREAL / "Config" / "RidePrepAssetOverrides.example.json", root / "Config" / "RidePrepAssetOverrides.example.json")
    for f in ("build_level.py", "import_game_level.py"):
        size += copy(UNREAL / "Scripts" / f, root / "Scripts" / f)
    # Course: what the import reads, nothing the web client alone needs
    course = root / "Course"
    for rel in ("manifest.json", "route.bin", "origin.json", "game/index.json"):
        if (pkg / rel).exists():
            size += copy(pkg / rel, course / rel)
    kit = pkg / index["kit"]["dir"]
    for f in kit.rglob("*"):
        if f.is_file() and not f.name.endswith((".log", ".blend1")):
            size += copy(f, course / index["kit"]["dir"] / f.relative_to(kit))
    for c in index["chunks"]:
        for key in ("glbUnreal", "instances", "landuse", "hero", "heroPebbles"):
            rel = c.get(key)
            if rel and (pkg / rel).exists():
                size += copy(pkg / rel, course / rel)
    for rel in (index.get("farUnreal"), (index.get("hero") or {}).get("pebbles"), (index.get("hero") or {}).get("index")):
        if rel and (pkg / rel).exists():
            size += copy(pkg / rel, course / rel)
    # Rider
    for bike in ("road", "tt"):
        size += copy(REPO / "apps" / "client" / "public" / "models" / f"rider_{bike}.glb", root / "Rider" / f"rider_{bike}.glb")
        if rider_blend and (Path(rider_blend) / f"rider_{bike}.blend").exists():
            size += copy(Path(rider_blend) / f"rider_{bike}.blend", root / "Rider" / f"rider_{bike}.blend")
    # Guide and credits
    size += copy(REPO / "docs" / "UNREAL_GUIDE.md", root / "README.md")
    credits = list(index.get("attribution", [])) + [
        "Rider body: MakeHuman bundled assets (CC0 1.0); rider kit, bike and art kit: RidePrep (procedural, CC0)",
        "OpenStreetMap / Overture data: ODbL — keep '© OpenStreetMap contributors, Overture Maps Foundation' with renders you publish",
    ]
    (root / "ATTRIBUTION.txt").write_text("\n".join(credits) + "\n")
    man = json.loads((pkg / "manifest.json").read_text())
    print(f"bundle {root}: {man['name']}, {len(index['chunks'])} chunks, {size / 1e6:.0f} MB")
    return root


def zip_bundle(root: Path) -> list[Path]:
    """<name>.zip (everything but the hero road) and <name>_hero.zip (Course/game/unreal/hero), same relative paths."""
    outs = []
    hero = root / "Course" / "game" / "unreal" / "hero"
    files = [f for f in root.rglob("*") if f.is_file()]
    main = [f for f in files if hero not in f.parents]
    rest = [f for f in files if hero in f.parents]
    for suffix, part in (("", main), ("_hero", rest)):
        if not part:
            continue
        z = root.parent / f"{root.name}{suffix}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for f in sorted(part):
                zf.write(f, Path(root.name) / f.relative_to(root))
        print(f"  {z.name}: {z.stat().st_size / 1e6:.0f} MB")
        outs.append(z)
    return outs


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("package")
    p.add_argument("--out", required=True)
    p.add_argument("--name", default=None)
    p.add_argument("--rider-blend", default=None, help="folder with rider_road.blend / rider_tt.blend (tools/rider output)")
    p.add_argument("--zip", action="store_true")
    a = p.parse_args()
    man = json.loads((Path(a.package) / "manifest.json").read_text())
    name = a.name or "RidePrep_" + "".join(ch for ch in man["name"].title() if ch.isalnum())
    root = bundle(Path(a.package), Path(a.out), name, Path(a.rider_blend) if a.rider_blend else None)
    if a.zip:
        zip_bundle(root)


if __name__ == "__main__":
    main()
