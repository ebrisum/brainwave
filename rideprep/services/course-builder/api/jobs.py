"""Build jobs: the worker runs the gpx2course library and publishes its JSON progress events.

With REDIS_URL set, jobs go to an RQ queue and events travel over Redis (list for replay + pub/sub for live). Without
Redis (local dev, tests) jobs run in a background thread and events live in memory. The API never contains pipeline logic.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

COURSES_DIR = Path(os.environ.get("RIDEPREP_COURSES_DIR", "./courses")).resolve()
UPLOADS_DIR = Path(os.environ.get("RIDEPREP_UPLOADS_DIR", COURSES_DIR / ".uploads")).resolve()
REDIS_URL = os.environ.get("REDIS_URL")


class EventBus:
    def publish(self, build_id: str, event: dict) -> None: ...
    def replay(self, build_id: str, start: int) -> list[dict]: ...


class MemoryBus(EventBus):
    def __init__(self):
        self.events: dict[str, list[dict]] = defaultdict(list)
        self.cv = threading.Condition()

    def publish(self, build_id, event):
        with self.cv:
            self.events[build_id].append(event)
            self.cv.notify_all()

    def replay(self, build_id, start):
        with self.cv:
            return list(self.events.get(build_id, [])[start:])

    def wait(self, timeout: float):
        with self.cv:
            self.cv.wait(timeout)


class RedisBus(EventBus):
    def __init__(self, url: str):
        import redis

        self.r = redis.Redis.from_url(url)

    def publish(self, build_id, event):
        self.r.rpush(f"build:{build_id}:events", json.dumps(event, default=str))
        self.r.expire(f"build:{build_id}:events", 7 * 24 * 3600)

    def replay(self, build_id, start):
        return [json.loads(x) for x in self.r.lrange(f"build:{build_id}:events", start, -1)]

    def wait(self, timeout: float):
        time.sleep(min(timeout, 0.5))


BUS: EventBus = RedisBus(REDIS_URL) if REDIS_URL else MemoryBus()


def run_build(build_id: str, input_path: str, options: dict) -> None:
    """Job body (also the RQ entry point)."""
    from gpx2course.cli import finalize
    from gpx2course.config import Config
    from gpx2course.pipeline import BuildContext, BuildOptions
    from gpx2course.progress import Progress
    from gpx2course.stages.registry import pipeline

    bus = BUS if not REDIS_URL else RedisBus(REDIS_URL)
    cfg = Config.load(os.environ.get("GPX2COURSE_CONFIG"))
    ev = options.get("event_start")
    opts = BuildOptions(name=options.get("name"), event_start=datetime.fromisoformat(ev) if ev else None, tier=options.get("tier", "full"),
                        targets=tuple(options.get("targets", ["web", "unreal"])), weather=options.get("weather", "climatology"),
                        rider=options.get("rider") or {}, resume=True)
    if os.environ.get("GPX2COURSE_WORKERS"):
        opts.workers = int(os.environ["GPX2COURSE_WORKERS"])
    prog = Progress(mode="none")
    prog.listeners.append(lambda rec: bus.publish(build_id, rec))
    ctx = BuildContext(Path(input_path), COURSES_DIR, opts, cfg, prog)
    # Tell clients the course id as soon as the profile stage fixes it, so they can stream the quick tier early.
    prog.listeners.append(lambda rec: rec.get("event") == "stage_end" and rec.get("stage") == "profile" and ctx.course_id
                          and bus.publish(build_id, {"event": "course_id", "courseId": ctx.course_id}))
    try:
        pipeline().run(ctx)
        finalize(ctx)
        _upload_to_object_store(ctx.dir)
    except Exception as ex:  # noqa: BLE001
        finalize(ctx, failed=str(ex))
        bus.publish(build_id, {"event": "error", "message": str(ex)})
    finally:
        bus.publish(build_id, {"event": "closed", "courseId": ctx.course_id, "t": time.time()})


def _upload_to_object_store(pkg: Path) -> None:
    """Optional: mirror the finished package to MinIO/S3 (STORAGE=minio)."""
    if os.environ.get("STORAGE") != "minio":
        return
    from .storage import minio_client

    c, bucket = minio_client()
    for p in pkg.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            c.fput_object(bucket, f"{pkg.name}/{p.relative_to(pkg).as_posix()}", str(p))


def enqueue(build_id: str, input_path: str, options: dict) -> None:
    if REDIS_URL:
        import redis
        from rq import Queue

        Queue("builds", connection=redis.Redis.from_url(REDIS_URL)).enqueue(run_build, build_id, input_path, options, job_timeout=3600,
                                                                           job_id=f"build-{build_id}-{int(time.time())}")
    else:
        threading.Thread(target=run_build, args=(build_id, input_path, options), daemon=True).start()
    BUS.publish(build_id, {"event": "queued", "buildId": build_id, "t": datetime.now(timezone.utc).isoformat()})
