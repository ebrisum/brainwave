"""Game-art path ("art kits"): a regional kit (textures, materials, meshes built in Blender) plus per-chunk level
data (terrain, roads, buildings with UVs and kit material ids; kit instance lists) for the web client and Unreal.

  gpx2course game <package> --kit emilia-romagna [--render]

See docs/GAME_ART.md.
"""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

KITS_DIR = Path(__file__).with_name("kits")


def available_kits() -> list[str]:
    return sorted(p.stem.replace("_", "-") for p in KITS_DIR.glob("*.json"))


def load_kit(name: str) -> dict:
    p = KITS_DIR / (name.replace("-", "_") + ".json")
    if not p.exists():
        raise FileNotFoundError(f"unknown kit {name!r}; available: {', '.join(available_kits())}")
    return json.loads(p.read_text())


def default_kit_for(style: dict, origin: tuple[float, float]) -> str | None:
    """Pick a kit for a course: by bounding region first, then the country style."""
    lat, lon = origin
    if 43.7 <= lat <= 45.2 and 9.2 <= lon <= 12.8:  # Emilia-Romagna
        return "emilia-romagna"
    return None


__all__ = ["available_kits", "load_kit", "default_kit_for", "resources"]
