# RidePrep

Upload a GPX/TCX/FIT of a real bike course; RidePrep turns it into a rideable 3D version with real terrain, surfaces,
corners and wind that behaves the way it would on race day — then you ride it indoors on a smart trainer. The goal is
race preparation: where the course hurts, which stretches are exposed or sheltered, and how long each part takes at a
given power.

## Layout

| Path | What |
|---|---|
| `services/course-builder` | **`gpx2course`** — the core pipeline (Python): one command turns any GPX into a course package. FastAPI API + RQ worker. Headless Blender bake script. |
| `packages/physics` | Rider physics, air density, cornering, wind model with gusts, predictor, pacing optimiser, scenarios |
| `packages/ble` | BLE adapter interface, Web Bluetooth + virtual adapters, FTMS/CPS/HRS/CSC parsers, FTMS encoders, trainer controller, reconnect, calibration check |
| `packages/course-format` | Package types + JSON Schema, binary decoders, `poseAt`, local-frame ↔ WGS84, ride-core stream schema |
| `packages/metrics` | NP/IF/TSS/VI, W′ balance, zones, decoupling, FIT/TCX/GPX writers |
| `apps/client` | Web client (Vite + React + Zustand; three.js engine classes outside React; physics in a Web Worker) |
| `apps/ride-core` | Headless ride engine for Unreal: physics, noble BLE, recording, MessagePack WebSocket at 50 Hz |
| `apps/unreal` | UE 5.8 project + `RidePrepRuntime` plugin (runtime mode) + editor import script |
| `tools/ble-emulator` | bleno peripheral: FTMS trainer + CPS + HRS with a scripted rider |
| `fixtures` | Synthetic test courses (polder 58 km, forest climb 42 km, urban cobbles 17 km/2 laps, 180 km perf) |
| `docs` | DECISIONS, SOURCES, MILESTONES, LICENSES, PHYSICS, WIND_MODEL |

## Quick start

```bash
# Pipeline
pip install -e "services/course-builder[api,dev]"
python -m gpx2course build fixtures/forest_climb_40k.gpx --out ./courses --event-start 2026-06-14T09:00:00+02:00
python -m gpx2course inspect <courseId> --out ./courses        # climbs, corners, surfaces, exposure
python -m gpx2course validate <courseId> --out ./courses

# Backend + web client
docker compose up                       # api, worker (Blender), redis, minio, valhalla
#   or, without Docker:  cd services/course-builder && RIDEPREP_COURSES_DIR=../../courses uvicorn api.app:app --port 8000
pnpm install && pnpm dev                # http://localhost:5173 (Chrome/Edge for Web Bluetooth)

# Tests
pnpm -r test                            # TS packages, incl. native C++ cross-renderer checks (needs g++ and python3)
cd services/course-builder && GPX2COURSE_OFFLINE=1 pytest
```

`gpx2course build --help` lists every option (`--tier`, `--targets`, `--weather forecast|historical:<date>|climatology|manual:<file>`,
`--resume`, `--from-stage`, `--only-stage`, `--dry-run`, `--progress json`, `--workers`, `--config`).

## Real-world view

Photoreal (Google 3D Tiles, as in Google Earth), video mode (real footage at your speed), cockpit view, street-level
photos and per-country styling: see `docs/REAL_WORLD_VIEW.md` — including how to build and run the Unreal version.

## Status

See `docs/MILESTONES.md` for what is done, measured budgets and what still needs real hardware (Bluetooth trainer,
Unreal Engine build, real-GPU frame rates). Data sources and licences: `docs/LICENSES.md`.
