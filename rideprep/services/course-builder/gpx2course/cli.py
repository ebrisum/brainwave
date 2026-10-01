"""gpx2course command-line interface (spec §2.1)."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import PIPELINE_VERSION
from .config import Config
from .pipeline import BuildContext, BuildOptions
from .progress import Progress


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    from .stages.registry import STAGE_NAMES

    p = argparse.ArgumentParser(prog="gpx2course", description="Turn any GPX/TCX/FIT course into a rideable RidePrep course package.")
    p.add_argument("--version", action="version", version=f"gpx2course {PIPELINE_VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build a course package")
    b.add_argument("input", help="course.gpx | .tcx | .fit")
    b.add_argument("--name")
    b.add_argument("--event-start", help="planned start, ISO 8601 (drives weather, climatology, foliage season, sun)")
    b.add_argument("--tier", choices=["quick", "full"], default="full")
    b.add_argument("--targets", default="web,unreal", help="comma list of web,unreal")
    b.add_argument("--weather", default="climatology", help="forecast | historical:<YYYY-MM-DD> | climatology | manual:<file.json>")
    b.add_argument("--rider", help="rider.json (defaults for the predictor)")
    b.add_argument("--out", default="./courses")
    b.add_argument("--workers", type=int, default=None)
    b.add_argument("--config")
    b.add_argument("--resume", action="store_true")
    b.add_argument("--force", action="store_true", help="rebuild even if the package exists")
    g = b.add_mutually_exclusive_group()
    g.add_argument("--from-stage", choices=STAGE_NAMES)
    g.add_argument("--only-stage", choices=STAGE_NAMES)
    b.add_argument("--dry-run", action="store_true")
    b.add_argument("--progress", choices=["text", "json", "none"], default="text")
    b.add_argument("--offline", action="store_true", help="never touch the network (fixtures, CI)")

    w = sub.add_parser("weather", help="refresh weather/scenarios without rebuilding")
    w.add_argument("course_id")
    w.add_argument("--weather", default="forecast")
    w.add_argument("--event-start")
    w.add_argument("--out", default="./courses")
    w.add_argument("--config")
    w.add_argument("--offline", action="store_true")

    v = sub.add_parser("validate", help="schema, integrity and target-export checks")
    v.add_argument("course_id")
    v.add_argument("--out", default="./courses")

    i = sub.add_parser("inspect", help="stats, climbs, corners and exposure summary")
    i.add_argument("course_id")
    i.add_argument("--out", default="./courses")

    vs = sub.add_parser("video", help="sync a recorded ride (with its video) to the course for video mode")
    vs.add_argument("course_id")
    vs.add_argument("track", help="GPX/TCX/FIT with timestamps recorded during the filmed ride")
    vs.add_argument("--name")
    vs.add_argument("--video-offset", type=float, default=0.0, help="video time (s) at the track's first timestamp")
    vs.add_argument("--out", default="./courses")

    dt = sub.add_parser("dev-tileset", help="write a local ECEF 3D Tiles stand-in for photoreal mode (no API key needed)")
    dt.add_argument("course_id")
    dt.add_argument("--out", default="./courses")

    c = sub.add_parser("cache", help="manage regional dataset caches")
    csub = c.add_subparsers(dest="cache_cmd", required=True)
    cw = csub.add_parser("warm", help="prefetch DEM and land-cover tiles")
    gg = cw.add_mutually_exclusive_group(required=True)
    gg.add_argument("--region", help="named region (see gpx2course/data/regions.json)")
    gg.add_argument("--bbox", help="w,s,e,n in degrees")
    cw.add_argument("--config")
    return p


def _resolve_pkg(out: str, cid: str) -> Path:
    p = Path(cid)
    if p.is_dir() and (p / "manifest.json").exists():
        return p
    d = Path(out) / cid
    if not d.exists():
        sys.exit(f"no package {cid} under {out}")
    return d


def cmd_build(a) -> int:
    cfg = Config.load(a.config)
    if a.offline:
        cfg.offline = True
    opts = BuildOptions(name=a.name, event_start=_parse_dt(a.event_start), tier=a.tier, targets=tuple(t for t in a.targets.split(",") if t),
                        weather=a.weather, rider=json.loads(Path(a.rider).read_text()) if a.rider else {},
                        resume=a.resume, from_stage=a.from_stage, only_stage=a.only_stage, dry_run=a.dry_run, force=a.force)
    if a.workers:
        opts.workers = a.workers
    prog = Progress(a.progress)
    if a.dry_run:
        from .dryrun import dry_run
        res = dry_run(Path(a.input), cfg, opts)
        if a.progress == "json":
            prog.emit("dry_run", **res)
        else:
            print(json.dumps(res, indent=2))
        return 0
    from .stages.registry import pipeline
    ctx = BuildContext(Path(a.input), Path(a.out), opts, cfg, prog)
    try:
        pipeline().run(ctx)
    except Exception as ex:  # noqa: BLE001
        finalize(ctx, failed=str(ex))
        if a.progress != "json":
            print(f"build failed: {ex}", file=sys.stderr)
        return 1
    finalize(ctx)
    return 0


def finalize(ctx: BuildContext, failed: str | None = None) -> None:
    """build_log.json: per-stage duration, inputs, sources and warnings (not part of the content hash)."""
    if not ctx.dir.exists():
        return
    log = {"courseId": ctx.course_id, "pipelineVersion": PIPELINE_VERSION, "input": str(ctx.input_path), "inputSha256": ctx.input_hash,
           "options": {**ctx.options.fingerprint(), "weather": ctx.options.weather, "workers": ctx.options.workers},
           "finished": datetime.now().isoformat(), "failed": failed,
           "stages": [{"name": k, **{kk: vv for kk, vv in v.items() if kk != "trace"}} for k, v in ctx.state.get("stages", {}).items()],
           "sources": ctx.state.get("sources", {}), "warnings": ctx.state.get("warnings", {})}
    ctx.write_json("build_log.json", log, indent=1)


def cmd_weather(a) -> int:
    from .pipeline import Stage  # noqa: F401
    from .stages import weather

    cfg = Config.load(a.config)
    if a.offline:
        cfg.offline = True
    d = _resolve_pkg(a.out, a.course_id)
    m = json.loads((d / "manifest.json").read_text())
    opts = BuildOptions(event_start=_parse_dt(a.event_start or m.get("eventStart")), weather=a.weather)
    ctx = BuildContext.__new__(BuildContext)
    ctx.dir, ctx.options, ctx.config, ctx.progress = d, opts, cfg, Progress("text")
    ctx.state, ctx.cache, ctx._frame, ctx.current_stage, ctx.course_id = {"warnings": {}, "sources": {}}, {}, None, "weather", m["courseId"]
    weather.run(ctx)
    for w in ctx.state["warnings"].get("weather", []):
        print("⚠", w["message"])
    print(f"weather.json updated ({json.loads((d / 'weather.json').read_text())['mode']})")
    return 0


def cmd_validate(a) -> int:
    from .stages.validate import validate_package

    d = _resolve_pkg(a.out, a.course_id)
    errs = validate_package(d)
    for e in errs:
        print("✖", e)
    if not errs:
        print(f"✔ {d.name} is valid")
    return 1 if errs else 0


def cmd_inspect(a) -> int:
    import numpy as np

    d = _resolve_pkg(a.out, a.course_id)
    m = json.loads((d / "manifest.json").read_text())
    st = m["stats"]
    seg = m["segments"]
    print(f"{m['name']}  ({m['courseId']})")
    print(f"  {st['distanceM'] / 1000:.1f} km · +{st['ascentM']:.0f} m / −{st['descentM']:.0f} m · max {st['maxGradePct']:.1f} % · laps {st['laps']}")
    print(f"  Climbs ({len(seg['climbs'])}):")
    for c in seg["climbs"]:
        print(f"    km {c['sStart'] / 1000:6.2f}  {c['lengthM'] / 1000:5.2f} km @ {c['avgGradePct']:4.1f} % (max {c['maxGradePct']:4.1f} %)  +{c['gainM']:.0f} m  cat {c['category']}")
    tech = [c for c in seg["corners"] if c["vMaxDryKmh"] < 35]
    print(f"  Technical corners: {len(seg['corners'])} (≤35 km/h: {len(tech)}, hairpins: {sum(c['hairpin'] for c in seg['corners'])})")
    surf = {}
    for r in seg["surfaceRuns"]:
        surf[r["surface"]] = surf.get(r["surface"], 0) + r["sEnd"] - r["sStart"]
    print("  Surfaces: " + ", ".join(f"{k} {v / 1000:.1f} km" for k, v in sorted(surf.items(), key=lambda kv: -kv[1])))
    w = m["wind"]
    data = np.frombuffer((d / "wind.bin").read_bytes(), np.uint8).reshape(len(w["layers"]), w["count"], w["directionBins"]) / 100
    total = data[0] * data[1] * data[2] * data[3]
    print("  Exposure (U_rider/U10 by wind FROM direction):")
    for k in range(0, 16, 2):
        print(f"    {k * 22.5:5.1f}°  mean {total[:, k].mean():.2f}  sheltered(<0.6 shelter) {np.mean(data[1, :, k] < 0.6):4.0%}")
    if m["warnings"]:
        print(f"  Warnings: {len(m['warnings'])} (see report.html)")
    return 0


def cmd_cache(a) -> int:
    from .cachewarm import warm

    cfg = Config.load(a.config)
    if a.bbox:
        bbox = tuple(float(v) for v in a.bbox.split(","))
    else:
        regions = json.loads((Path(__file__).parent / "data" / "regions.json").read_text())
        if a.region not in regions:
            sys.exit(f"unknown region {a.region}; known: {', '.join(regions)}")
        bbox = tuple(regions[a.region])
    warm(cfg, bbox)
    return 0


def cmd_video(a) -> int:
    from .videosync import map_track

    r = map_track(_resolve_pkg(a.out, a.course_id), Path(a.track), a.name, a.video_offset)
    print(f"video/{r['name']}.json: {r['sStart'] / 1000:.2f}–{r['sEnd'] / 1000:.2f} km ({r['coverage']:.0%} of the course), "
          f"{len(r['points'])} sync points, median {r['medianSpeedMs'] * 3.6:.1f} km/h")
    return 0


def cmd_dev_tileset(a) -> int:
    from .devtileset import build

    print(build(_resolve_pkg(a.out, a.course_id)))
    return 0


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    return {"dev-tileset": cmd_dev_tileset, "video": cmd_video, "build": cmd_build, "weather": cmd_weather, "validate": cmd_validate, "inspect": cmd_inspect, "cache": cmd_cache}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
