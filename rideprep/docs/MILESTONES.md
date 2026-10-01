# Milestones

Status of spec §15 in this build, with demo notes and measured numbers. Measurements: 4 vCPU build container,
offline fixtures unless noted.

| # | Milestone | Status |
|---|---|---|
| M0 | Scaffold | Done — monorepo, CI workflow (`.github/workflows/rideprep.yml`), compose file, `gpx2course --help`, API ↔ client. Compose images not built here (no Docker daemon in the build container). |
| M1 | `gpx2course` data stages | Done — stages 1–7 + 12, caching, `--resume`, `--dry-run`, JSON progress, `build_log.json`, `report.html`, `validate`; §16.8 tests pass. |
| M2 | Physics and wind runtime | Done — §16.1–16.3 and §16.5 pass; wind layers, gusts, predictor, four scenarios. |
| M3 | Quick tier + web ride | Done — stage 8; web client rides fixtures with the virtual device on the Quick-tier world, HUD, briefing. 60 fps reported in headless SwiftShader at 1600×900. |
| M4 | Full-tier bake | Done with caveats — parallel per-chunk bake (Blender or lite), 3 LODs, meshopt via gltfpack, progressive streaming replacing Quick chunks. Blender path exercised with the `bpy` 5.0.1 module; KTX2 not exercised (no textures yet). |
| M5 | Ride core + Bluetooth | Done in software — ride core (noble adapter, WebSocket MessagePack 50 Hz), Web Bluetooth adapter, parsers (§16.4), trainer controller (§9.4), reconnect, BLE emulator core. The hardware end-to-end test (ride core ↔ bleno emulator over real BLE) needs a machine with Bluetooth. |
| M6 | Unreal runtime target | Code complete, not compiled — `RidePrepRuntime` plugin, stage 11 exports. Engine-independent maths and MessagePack are compiled and tested natively; ENU↔UE round trip and cross-renderer position tests pass. Needs UE 5.8 to build and visually verify. |
| M7 | Graphics polish | Partial — true-sun sky, soft shadows near the rider, fog from visibility, rain particles, wet road, wind-driven vegetation sway shader, rider with cadence/lean/standing/tuck, five cameras incl. flyover, quality presets with auto-detect and dynamic resolution. Missing: bloom/SSAO, flags, wheel spray, licensed rider asset. |
| M8 | Preparation and analysis | Done — optimiser + scenario comparison, target band in HUD, ERG on a course, trainer calibration check (§9.4), post-ride analysis, FIT/TCX/GPX export, ghost rider. |
| M9 | Extras | Mostly done — **Photoreal mode** (Google 3D Tiles) in the web client (verified with an ECEF stand-in tileset: anchoring + height calibration) and in Unreal via Cesium (code, not compiled here); **cockpit view**; **video mode** (sync recorded rides, play at virtual speed — verified in the browser); Mapillary street photos in the briefing; regional style profiles; Unreal editor import script (untested). Not started: Electron app. |

## Demo notes

### Build a course (offline fixture)
```
pip install -e "services/course-builder[api,dev]"
python -m gpx2course build fixtures/forest_climb_40k.gpx --out ./courses --offline --event-start 2026-06-14T09:00:00+02:00
python -m gpx2course inspect <courseId> --out ./courses
open courses/<courseId>/report.html
```
Online (Copernicus DEM + WorldCover over S3): drop `--offline`. Open-Meteo, Overpass and Valhalla were not reachable
from the build container, so those paths fell back with warnings.

### Web ride
```
RIDEPREP_COURSES_DIR=./courses uvicorn api.app:app --port 8000   # in services/course-builder (or docker compose up)
pnpm install && pnpm dev                                          # http://localhost:5173
```
Library → course → Briefing (scenarios, wind rose, pacing plan) → Ride → pair “Demo rider” → Start.
Keys: space/P pause, 1–5 cameras.

### Ride core (for Unreal)
```
pnpm --filter @rideprep/ride-core start -- --package ./courses/<courseId> --virtual
```

## Measured budgets (spec §16.7)
| Measure | Budget | Measured |
|---|---|---|
| Data package stages 1–8, 180 km (offline, 4 vCPU) | ≤ 2 min for 100 km | ~30 s for 180 km (corridor 15 s, quick 10 s, wind 3.5 s) |
| Full build incl. bake + exports, 180 km, lite baker, 4 vCPU | ≤ 10 min | 49 s |
| Blender bake, 17 km urban (35 chunks), 4 workers | — | 9.5 s (~1 s/chunk/worker) → 180 km ≈ 90 s on 4, ≈ 25 s on 16 |
| Online polder build (Copernicus + WorldCover), 58 km | — | 18 s |
| Predictor, 180 km (Node) | ≤ 1 s | 73 ms |
| Optimiser, 180 km | ≤ 10 s | 0.39 s |
| `--dry-run`, 180 km | ≤ 20 s, estimate ±30 % | < 1 s, within ±30 % (test) |
| Ride core → renderer latency (localhost, p95) | ≤ 20 ms | ≤ 20 ms (test asserts) |
| ENU → UE → ENU round trip, 180 km | < 1 mm | < 1 µm |
| Cross-renderer position (TS vs C++) | ± 2 cm | < 1 mm |
| Frame rate | ≥ 60 fps (RTX 3060, High) | 60 fps reported under headless SwiftShader, urban + forest fixtures (real-GPU numbers still to measure) |
