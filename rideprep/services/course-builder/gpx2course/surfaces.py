"""OSM surface/smoothness → rolling-resistance multiplier and surface codes (PHYSICS.md, spec §4.6)."""
from __future__ import annotations

SURFACE_CODES = {
    "asphalt": 1, "asphalt_rough": 2, "concrete": 3, "paving_stones": 4, "sett": 5, "compacted": 6, "gravel": 7,
    "dirt": 8, "unknown": 0, "bridge_deck": 9,
}

_ROUGH_SMOOTHNESS = {"intermediate", "bad", "very_bad", "horrible", "very_horrible", "impassable"}


def classify(surface: str | None, smoothness: str | None, highway: str | None) -> tuple[str, float]:
    """Return (surface class, Crr multiplier on the rider's tyre base Crr)."""
    s = (surface or "").lower()
    sm = (smoothness or "").lower()
    if not s:
        hw = (highway or "").lower()
        if hw in ("track", "path", "bridleway"):
            return "compacted", 2.0
        if hw:
            return ("asphalt_rough", 1.25) if sm in _ROUGH_SMOOTHNESS else ("asphalt", 1.0)
        return "unknown", 1.0
    if s in ("asphalt", "paved"):
        return ("asphalt_rough", 1.25) if sm in _ROUGH_SMOOTHNESS else ("asphalt", 1.0)
    if s in ("chipseal",):
        return "asphalt_rough", 1.25
    if s in ("concrete", "concrete:plates", "concrete:lanes"):
        return "concrete", 1.10
    if s in ("paving_stones", "bricks", "brick", "metal", "wood"):
        return "paving_stones", 1.60
    if s in ("sett", "cobblestone", "unhewn_cobblestone", "cobblestone:flattened"):
        return "sett", 2.50
    if s in ("compacted", "fine_gravel"):
        return "compacted", 2.00
    if s in ("gravel", "unpaved", "dirt", "ground", "earth", "grass", "mud", "sand", "pebblestone"):
        return ("gravel" if s in ("gravel", "pebblestone") else "dirt"), 3.00
    return "unknown", 1.0


def width_m(tags: dict) -> float:
    w = tags.get("width")
    try:
        if w is not None:
            return max(1.5, min(float(str(w).split()[0].replace(",", ".")), 30.0))
    except ValueError:
        pass
    lanes = tags.get("lanes")
    try:
        if lanes is not None:
            return 3.0 * float(lanes)
    except ValueError:
        pass
    hw = (tags.get("highway") or "").lower()
    return {"motorway": 11, "trunk": 9, "primary": 7.5, "secondary": 6.5, "tertiary": 5.5, "unclassified": 4.5,
            "residential": 5.5, "service": 3.5, "cycleway": 2.5, "track": 3.0, "path": 1.5}.get(hw, 4.0)
