"""RidePrep course-builder API (spec §13). Holds no pipeline logic: it stores uploads, queues builds and serves packages."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse

from gpx2course import PIPELINE_VERSION

from . import jobs

app = FastAPI(title="RidePrep course builder", version=PIPELINE_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])

ID_RE = re.compile(r"^[0-9a-f_c]{6,40}$")
MAX_UPLOAD = 50 * 1024 * 1024


def _course_dir(course_id: str) -> Path:
    if not ID_RE.match(course_id):
        raise HTTPException(400, "bad id")
    # Accept a build id (input hash prefix) and resolve it to its course via the pointer file
    p = jobs.COURSES_DIR / course_id
    if not p.exists():
        ptr = jobs.COURSES_DIR / ".work" / f"{course_id}.json"
        if ptr.exists():
            p = jobs.COURSES_DIR / json.loads(ptr.read_text())["courseId"]
        else:
            wd = jobs.COURSES_DIR / ".work" / course_id
            if wd.exists():
                p = wd
    if not p.exists():
        raise HTTPException(404, "unknown course")
    return p


@app.get("/health")
def health():
    return {"ok": True, "pipelineVersion": PIPELINE_VERSION, "queue": "rq" if jobs.REDIS_URL else "thread"}


@app.get("/courses")
def list_courses():
    out = []
    if jobs.COURSES_DIR.exists():
        for d in sorted(jobs.COURSES_DIR.iterdir()):
            m = d / "manifest.json"
            partial = d / "manifest.partial.json"
            if d.name.startswith("c_") and (m.exists() or partial.exists()):
                j = json.loads((m if m.exists() else partial).read_text())
                out.append({"courseId": j["courseId"], "name": j["name"], "stats": j["stats"], "tier": j["tier"], "eventStart": j.get("eventStart"),
                            "climbs": len(j["segments"]["climbs"]), "building": not m.exists()})
    return out


@app.post("/courses")
async def upload(file: UploadFile = File(...), name: str | None = Form(None), event_start: str | None = Form(None), tier: str = Form("full"),
                 targets: str = Form("web,unreal"), weather: str = Form("climatology"), rider: str | None = Form(None)):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file too large")
    suffix = Path(file.filename or "course.gpx").suffix.lower()
    if suffix not in (".gpx", ".tcx", ".fit"):
        raise HTTPException(400, "expected .gpx, .tcx or .fit")
    h = hashlib.sha256(data).hexdigest()
    build_id = h[:20]
    jobs.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    path = jobs.UPLOADS_DIR / f"{build_id}{suffix}"
    if not path.exists():
        path.write_bytes(data)
    ptr = jobs.COURSES_DIR / ".work" / f"{build_id}.json"
    if ptr.exists():
        cid = json.loads(ptr.read_text())["courseId"]
        if (jobs.COURSES_DIR / cid / "manifest.json").exists():
            return {"buildId": build_id, "courseId": cid, "status": "ready", "deduplicated": True}
    opts = {"name": name or Path(file.filename or "").stem or None, "event_start": event_start, "tier": tier, "targets": targets.split(","),
            "weather": weather, "rider": json.loads(rider) if rider else None}
    jobs.enqueue(build_id, str(path), opts)
    return JSONResponse({"buildId": build_id, "courseId": None, "status": "queued"}, status_code=202)


@app.get("/courses/{cid}/events")
async def events(cid: str, request: Request):
    """Server-sent events with stage progress, timings and errors (replays history, then streams live)."""

    async def gen():
        i = 0
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return
            batch = jobs.BUS.replay(cid, i)
            for ev in batch:
                i += 1
                yield f"event: {ev.get('event', 'message')}\ndata: {json.dumps(ev, default=str)}\n\n"
                if ev.get("event") == "closed":
                    return
            if not batch:
                idle += 0.25
                if idle > 15:
                    idle = 0
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.25)
            else:
                idle = 0

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/courses/{cid}/manifest")
def manifest(cid: str):
    d = _course_dir(cid)
    m = d / "manifest.json"
    if not m.exists():
        if (d / "manifest.partial.json").exists():
            return FileResponse(d / "manifest.partial.json", media_type="application/json", headers={"X-RidePrep-Partial": "1"})
        raise HTTPException(409, "build still running")
    return FileResponse(m, media_type="application/json")


@app.get("/courses/{cid}/files/{path:path}")
def files(cid: str, path: str):
    d = _course_dir(cid)
    target = (d / path).resolve()
    if d.resolve() not in target.parents or any(part.startswith(".") for part in Path(path).parts):
        raise HTTPException(400, "bad path")
    if os.environ.get("STORAGE") == "minio" and (d / "manifest.json").exists():
        from .storage import signed_url
        return RedirectResponse(signed_url(d.name, path))
    if not target.exists() and path == "manifest.json" and (d / "manifest.partial.json").exists():
        # Progressive streaming: ride the Quick tier while the full bake continues
        return FileResponse(d / "manifest.partial.json", media_type="application/json", headers={"Cache-Control": "no-cache", "X-RidePrep-Partial": "1"})
    if not target.exists():
        raise HTTPException(404, "not found")
    immutable = path not in ("weather.json", "chunks/status.json", "chunks/index.json", "manifest.json")
    return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache"})


@app.post("/courses/{cid}/weather")
async def refresh_weather(cid: str, request: Request):
    """Refresh forecast or set a historical date / manual scenario; returns the new weather.json without a rebuild."""
    from gpx2course.cli import main as cli

    d = _course_dir(cid)
    body = await request.json()
    mode = body.get("weather", "forecast")
    args = ["weather", str(d), "--weather", mode]
    if mode.startswith("manual"):
        mp = d / ".manual_weather.json"
        mp.write_text(json.dumps(body.get("manual", {})))
        args[-1] = f"manual:{mp}"
    if body.get("eventStart"):
        args += ["--event-start", body["eventStart"]]
    if os.environ.get("GPX2COURSE_OFFLINE") == "1":
        args.append("--offline")
    await asyncio.to_thread(cli, args)
    return FileResponse(d / "weather.json", media_type="application/json")
