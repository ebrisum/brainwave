"""The ordered stage list (spec §2.2)."""
from __future__ import annotations

from ..pipeline import Pipeline, Stage
from . import bake, corridor, export_unreal, export_web, ingest, match, profile, quick, structure, validate, weather, wind


def _event_params(ctx):
    ev = ctx.options.event_start
    return {"month": ev.month if ev else None, "day": ev.day if ev else None}


STAGES = [
    Stage("ingest", "1", [], ingest.run),
    Stage("match", "2", ["ingest"], match.run),
    Stage("profile", "2", ["match"], profile.run),
    Stage("corridor", "1", ["profile"], corridor.run),
    Stage("structure", "2", ["profile", "corridor"], structure.run),
    Stage("wind", "2", ["profile", "corridor"], wind.run, params=_event_params),
    Stage("weather", "1", ["profile"], weather.run, params=lambda ctx: {"mode": ctx.options.weather,
                                                                          "start": ctx.options.event_start.isoformat() if ctx.options.event_start else None},
          deterministic=False),
    Stage("quick", "1", ["profile", "corridor", "structure"], quick.run, params=_event_params),
    Stage("bake", "1", ["quick", "structure"], bake.run, tiers=("full",)),
    Stage("export-web", "2", ["bake"], export_web.run, tiers=("full",), needs_target="web"),
    Stage("export-unreal", "1", ["quick", "corridor", "profile", "bake"], export_unreal.run, needs_target="unreal"),
    Stage("validate", "2", ["profile", "corridor", "structure", "wind", "weather", "quick", "bake", "export-web", "export-unreal"], validate.run),
]

STAGE_NAMES = [s.name for s in STAGES]


def pipeline() -> Pipeline:
    return Pipeline(STAGES)
