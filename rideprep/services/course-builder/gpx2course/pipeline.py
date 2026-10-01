"""Stage runner: cache keys, atomic outputs, resume, progress, build log."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import PIPELINE_VERSION
from .config import Config
from .progress import Progress


def sha256_file(p: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


@dataclass
class BuildOptions:
    name: str | None = None
    event_start: datetime | None = None
    tier: str = "full"
    targets: tuple[str, ...] = ("web", "unreal")
    weather: str = "climatology"
    rider: dict = field(default_factory=dict)
    workers: int = os.cpu_count() or 4
    resume: bool = False
    from_stage: str | None = None
    only_stage: str | None = None
    dry_run: bool = False
    force: bool = False

    def fingerprint(self) -> dict:
        """Options that affect the geometry/data of the package (weather excluded on purpose)."""
        return {"name": self.name, "tier": self.tier, "targets": sorted(self.targets),
                "event_month_day": self.event_start.strftime("%m-%d") if self.event_start else None}


class StageSkipped(Exception):
    pass


@dataclass
class Stage:
    name: str
    version: str
    deps: list[str]
    run: Callable[["BuildContext"], list[str]]
    params: Callable[["BuildContext"], dict] = lambda ctx: {}
    deterministic: bool = True
    tiers: tuple[str, ...] = ("quick", "full")
    needs_target: str | None = None


class BuildContext:
    """Everything a stage needs: paths, options, config, providers, warnings and sources."""

    def __init__(self, input_path: Path, out_root: Path, options: BuildOptions, config: Config, progress: Progress):
        self.input_path = Path(input_path)
        self.out_root = Path(out_root)
        self.options = options
        self.config = config
        self.progress = progress
        self.input_hash = sha256_file(self.input_path)
        self.work_dir = self.out_root / ".work" / self.input_hash[:20]
        self.pointer = self.out_root / ".work" / f"{self.input_hash[:20]}.json"
        self.dir = self.work_dir
        self.course_id: str | None = None
        self.state: dict = {"stages": {}, "warnings": {}, "sources": {}}
        self.current_stage: str | None = None
        self._frame = None
        self.cache: dict[str, Any] = {}

    # ----- paths and atomic writes -------------------------------------------------------------------------
    def path(self, rel: str) -> Path:
        return self.dir / rel

    def write_bytes(self, rel: str, data: bytes) -> Path:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, p)
        return p

    def write_json(self, rel: str, obj: Any, indent: int | None = None) -> Path:
        return self.write_bytes(rel, json.dumps(obj, indent=indent, sort_keys=False, default=str).encode())

    def read_json(self, rel: str) -> Any:
        return json.loads(self.path(rel).read_text())

    # ----- warnings / sources ------------------------------------------------------------------------------
    def warn(self, message: str, code: str = "warning", **data) -> None:
        stage = self.current_stage or "pipeline"
        self.state["warnings"].setdefault(stage, []).append({"code": code, "message": message, **data})
        self.progress.emit("warning", stage=stage, code=code, message=message)

    def source(self, kind: str, info) -> None:
        stage = self.current_stage or "pipeline"
        self.state["sources"].setdefault(stage, {})[kind] = {"name": info.name, "license": info.license, "attribution": info.attribution,
                                                             "resolution_m": info.resolution_m}

    def progress_frac(self, fraction: float, note: str = "") -> None:
        self.progress.stage_progress(self.current_stage or "", fraction, note)

    # ----- state ------------------------------------------------------------------------------------------
    def state_path(self) -> Path:
        return self.dir / ".state.json"

    def load_state(self) -> None:
        p = self.state_path()
        if p.exists():
            self.state = json.loads(p.read_text())
            self.course_id = self.state.get("courseId")

    def save_state(self) -> None:
        self.write_json(".state.json", self.state, indent=1)

    @property
    def frame(self):
        if self._frame is None:
            from .geo import LocalFrame

            o = self.read_json("origin.json")
            self._frame = LocalFrame(o["lat"], o["lon"])
        return self._frame

    def adopt_course_id(self, course_id: str) -> None:
        """Move the work directory to its content-addressed home once the course id is known."""
        self.course_id = course_id
        self.state["courseId"] = course_id
        final = self.out_root / course_id
        if self.dir != final:
            if final.exists():
                shutil.rmtree(final)
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(self.dir, final)
            self.dir = final
        self.pointer.parent.mkdir(parents=True, exist_ok=True)
        self.pointer.write_text(json.dumps({"courseId": course_id}))


class Pipeline:
    def __init__(self, stages: list[Stage]):
        self.stages = stages
        self.by_name = {s.name: s for s in stages}

    def stage_key(self, ctx: BuildContext, st: Stage) -> str:
        deps = {d: ctx.state["stages"].get(d, {}).get("key") for d in st.deps}
        payload = {"stage": st.name, "version": st.version, "pipeline": PIPELINE_VERSION, "deps": deps, "params": st.params(ctx),
                   "options": ctx.options.fingerprint(), "config": ctx.config.fingerprint()}
        if not st.deps:
            payload["input"] = ctx.input_hash
        return hashlib.sha256(stable_json(payload).encode()).hexdigest()

    def applicable(self, ctx: BuildContext, st: Stage) -> bool:
        if ctx.options.tier not in st.tiers:
            return False
        if st.needs_target and st.needs_target not in ctx.options.targets:
            return False
        return True

    def run(self, ctx: BuildContext) -> BuildContext:
        opts = ctx.options
        # Resume: find an existing work dir or a course dir via the pointer
        if ctx.pointer.exists():
            cid = json.loads(ctx.pointer.read_text())["courseId"]
            if (ctx.out_root / cid).exists():
                ctx.dir = ctx.out_root / cid
                ctx.course_id = cid
        ctx.dir.mkdir(parents=True, exist_ok=True)
        ctx.load_state()
        ctx.state.setdefault("stages", {})
        ctx.state.setdefault("warnings", {})
        ctx.state.setdefault("sources", {})
        ctx.state["started"] = datetime.now().isoformat()
        names = [s.name for s in self.stages]
        invalid_from = names.index(opts.from_stage) if opts.from_stage else None
        if opts.from_stage and opts.from_stage not in names:
            raise ValueError(f"unknown stage {opts.from_stage}")
        if opts.only_stage and opts.only_stage not in names:
            raise ValueError(f"unknown stage {opts.only_stage}")
        if opts.force and not opts.resume:
            invalid_from = 0 if invalid_from is None else invalid_from
        for i, st in enumerate(self.stages):
            if opts.only_stage and st.name != opts.only_stage:
                continue
            if not self.applicable(ctx, st):
                ctx.state["stages"].pop(st.name, None)
                continue
            key = self.stage_key(ctx, st)
            rec = ctx.state["stages"].get(st.name)
            forced = (invalid_from is not None and i >= invalid_from) or opts.only_stage == st.name
            if not forced and rec and rec.get("key") == key and rec.get("status") == "done" and all(ctx.path(o).exists() for o in rec.get("outputs", [])):
                ctx.progress.emit("stage_start", stage=st.name, index=i, total=len(self.stages))
                ctx.progress.emit("stage_end", stage=st.name, status="cached", duration_s=0.0)
                continue
            ctx.current_stage = st.name
            ctx.state["warnings"].pop(st.name, None)
            ctx.state["sources"].pop(st.name, None)
            ctx.progress.emit("stage_start", stage=st.name, index=i, total=len(self.stages))
            t0 = time.perf_counter()
            try:
                outputs = st.run(ctx)
                status = "done"
            except StageSkipped as ex:
                outputs, status = [], "skipped"
                ctx.warn(str(ex), code="stage_skipped")
            except Exception as ex:
                ctx.state["stages"][st.name] = {"key": None, "status": "failed", "error": str(ex), "trace": traceback.format_exc()}
                ctx.save_state()
                ctx.progress.emit("error", stage=st.name, message=f"{st.name}: {ex}")
                raise
            dur = time.perf_counter() - t0
            # Key may change if the stage altered state the key depends on (e.g. course id); recompute.
            ctx.state["stages"][st.name] = {"key": self.stage_key(ctx, st), "status": status, "outputs": outputs, "duration_s": round(dur, 3),
                                            "finished": datetime.now().isoformat()}
            ctx.save_state()
            ctx.progress.emit("stage_end", stage=st.name, status=status, duration_s=round(dur, 3))
            ctx.current_stage = None
        ctx.progress.emit("done", courseId=ctx.course_id, path=str(ctx.dir))
        return ctx
