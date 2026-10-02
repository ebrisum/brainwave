# Decisions

One line each: what was decided and why. Newest at the bottom of each section.

## Repository and tooling
- RidePrep lives in `rideprep/` inside the existing `brainwave` repo — the repo already holds an unrelated Vite site that should not be overwritten; the monorepo is self-contained.
- Owner inputs (spec §0) were left empty → spec defaults: personal/non-commercial, no Google key (Photoreal off), Chrome/Edge + Android, Docker Compose on one Linux box, web first then Unreal, metric with imperial toggle, title RidePrep.
- pnpm workspaces (`apps/*`, `packages/*`, `tools/*`) with TypeScript 7.0, Vitest 5, Vite 8, React 19, three.js r186 — latest stable at build time, pinned exactly in package.json + lockfile.
- Workspace packages are consumed as TypeScript sources (no build step); the ride core is bundled with esbuild for distribution.
- Python 3.12 in Docker/CI; the package declares `>=3.11` because the build container had 3.11.
- `ride-core` and `ble-emulator` declare noble/bleno as optional dependencies — native BLE stacks fail to build on machines without Bluetooth; everything else must install everywhere.

## Pipeline (`gpx2course`)
- Fixtures are synthetic but placed in real geography (Flevoland, Ardennes, Ghent, Limburg) with OSM-tagged sidecar GeoJSON — the build environment could not reach OSM, routing engines or Open-Meteo; replace with real recorded GPX when possible.
- A `sidecar` OSM provider reads `<course>.features.geojson` — makes every stage run offline and deterministically on the fixtures (tests, CI).
- The stage cache key = hash(stage name, stage version, pipeline version, dependency keys, stage params, options fingerprint, config fingerprint) — chaining keys avoids rehashing big files and still invalidates downstream stages.
- The work dir is renamed to its content-addressed home (`courses/<courseId>`) as soon as the `profile` stage fixes the course id — later stages and progressive streaming then use the final path; a pointer file maps input hash → course id for `--resume`.
- `manifest.json` is written last (atomic); `manifest.partial.json` is written after `quick` and at bake start so a rider can start on the Quick tier.
- Map matching resamples to 5 m inside `match` (attributes are stored per resampled point) — spec lists resampling under `profile`; `profile` re-resamples after snapping so both hold.
- Nearest-way matcher splits ways into ≤32-vertex pieces — linear referencing is O(vertices) and fixture/OSM ways can be long.
- Route geometry snaps to the matched way where matched, Gaussian-smoothed GPS elsewhere — curvature from raw GPS jitter is meaningless at ±10 m.
- Input-file elevation is used along the track, not by spatial nearest neighbour — a course that crosses itself at different heights would otherwise mix passes.
- Copernicus GLO-30 (a DSM) gets a 50 m running-median prefilter before the Gaussian smoothing — removes tree/building spikes beside the road; a proper DTM provider (AHN etc.) is the real fix (follow-up).
- Local frame = transverse Mercator at the origin (k=1, WGS84), z orthometric — matches ENU horizontally to <0.1 % within 10 km but does not curve the terrain away (game engines want a flat world); an exact inverse is implemented in TS for exports.
- Corridor rasters are 3 km tiles at 10 m (DEM float32, land cover uint8) plus a 90 m far-field DEM — bounded memory for 180 km loops whose bbox can be 200×200 km.
- GeoJSON instead of GeoPackage for corridor vectors — avoids a GDAL/OGR vector dependency; small enough per course.
- Quick-tier terrain is delivered as local-frame tiles (`dem/{i}_{j}.png`, terrarium, 301×301 vertices) instead of Web-Mercator `{z}/{x}/{y}` — renderers need no projection code and tiles align with the corridor rasters; the road corridor is flattened into the tiles.
- Wind layers are computed in parallel blocks of 250 samples with forked worker processes; obstacles are rasterised at 4 m per block and rays are marched through the raster — vectorises well and bounds memory.
- Shelter: strongest shelter along each ray, then **averaged over the 5 rays** of the ±15° fan (spec says min over all hits) — a single grazing ray hitting a building corner otherwise shelters a whole street from every direction (measured 0.08×U10 everywhere in the urban fixture).
- Weather never blocks a build: forecast/archive failures fall back to climatology, climatology failure to documented generic mid-latitude defaults, each with a report warning.
- No event date → simulated start tomorrow at ~10:00 local solar time — rides and briefings default to daylight.
- Bake: headless Blender when available, otherwise a built-in Python "lite" baker producing the same chunk structure — the build never fails for lack of Blender; the report says which baker ran.
- Blender chunk bake bakes AO only into buildings; flat ground keeps white AO — large ribbon triangles showed blotches.
- glTF material factors are written in linear space (catalogue colours are sRGB) — glTF requires linear `baseColorFactor`.
- `files.json` (per-file sha256) + `contentHash` exclude weather, logs, partial manifests and status files — determinism test compares geometry/data only, as the spec requires.
- Unreal heightmaps: 505×505 px at 8 m — a recommended Landscape size; 1009-px tiles at 4 m would quadruple package size for a 30 m source DEM.

## Physics and wind
- Wind direction is the meteorological FROM direction everywhere; `w_head = U·cos(dir_from − heading)`, `w_cross = U·sin(dir_from − heading)` — the spec's `−180°` form assumes a TO direction; with FROM it gives a tailwind for wind on the nose.
- Heading in `route.bin` is a compass bearing (radians clockwise from north).
- Optimiser: separable Lagrangian on per-segment steady-state times, calibrated per segment against the full predictor, tabulated on a 65-point power grid, bisection on the NP multiplier; final plan verified with the full predictor — 180 km in ~0.4 s.
- FTMS wind resistance coefficient sent = ρ·CdA (kg/m) — FTMS definition (frontal area × drag coefficient × air density); 0.51 ≈ 1.225 × 0.416.
- Gust multiplier: OU process with exact discretisation, σ from turbulence intensity of the z0 implied by the fRough layer, capped at gust10/U10.

## Clients
- Physics runs in a Web Worker on a wall-clock accumulator with fixed 20 ms steps; the renderer extrapolates ≤50 ms from the latest state.
- Rendering uses per-tile/per-chunk local vertex data with JS-double object transforms — camera-relative float32 precision without explicit origin shifting.
- Virtual device uses real elapsed time for crank events — timers lag under load and cadence must follow wall time.
- Ride-core stream schema lives in `packages/course-format/src/stream.ts`; Unreal decodes it with a small engine-independent MessagePack reader that is tested natively against the TS encoder.
- UE 5.8 pinned (current release; last UE5 line before UE6). glTFRuntime (MIT) and Cesium for Unreal are optional plugins detected at build time.
- Blender 5.2 LTS pinned in the worker image; the bake script was exercised with the `bpy` 5.0.1 Python module (same API) in CI-less testing.
- Docker Compose images use pinned tags except Valhalla (`valhalla-scripted:latest`, pin a digest in production) — no verified version tag was reachable from the build environment.

## Real-world view
- Photoreal = Google Photorealistic 3D Tiles streamed at runtime (3DTilesRendererJS in the web client, Cesium for Unreal) — the only source of real 3D imagery of an arbitrary course that may legally be shown live; Street View cannot be used to build a riding view under its terms.
- Tiles are anchored at the rider (affine ECEF → course frame from the exact inverse projection's Jacobian) and re-anchored every 750 m — curvature error stays < 5 cm near the rider instead of hundreds of metres at the far end of a 180 km course.
- Height is calibrated by raycasting the tiles at the road (median of road − surface over ±60 m) rather than trusting a geoid model — absorbs geoid undulation and photogrammetry bias; roofs/trees over the road are outvoted by the median.
- In photoreal mode our road ribbon stays on top (polygon offset) — photogrammetric road surfaces are blurry and often contain parked cars; the exact road width/surface matters for race prep.
- A dev stand-in tileset (`gpx2course dev-tileset`) built from package data with a fake 46.5 m geoid offset tests the full photoreal path without an API key.
- Video mode maps recorded rides to course distance (forward-only matching, earliest pass on loops); the video file never leaves the rider's device — avoids hosting large files and footage rights issues.
- Cockpit bars are pulled into the lower third of the frame (real eye-to-bar geometry falls outside a 60° field of view), as other cycling sims do.
- Regional style profiles are chosen from coarse country bounding boxes (smallest first) or "alpine" above 1200 m; borders are approximate, so `style = "<code>"` in the config overrides.

## Game-art path and Emilia-Romagna 70.3
- Overture Maps (GeoParquet on S3) is a first-class OSM-style provider: it is reachable where OSM/Overpass are not,
  needs no rate-limited API, and a bbox read touches only the row groups whose bbox statistics overlap (≈1 min for
  roads + buildings + water + land use of a 90 km course). Rows are converted to OSM-style tags so stages are unchanged.
- Sparse planner GPX files are snapped to the road network (HMM: σ 15 m emissions, β 60 m transitions, Dijkstra
  between candidates) before resampling. The official 70.3 file went from 30 % unmatched to 100 % routed (0.35 km
  unmatched) and 90.5 km — close to the published 90 km.
- Game art is split between Python (all GIS: land-use classification, vineyard row orientation, scatter, blocking) and
  Blender (mesh building, UVs, roofs, export). Blender stays a pure geometry/material step, so the same specs can drive
  an Unreal/PCG importer later.
- Chunk glTFs reference kit materials by name instead of embedding textures (182 chunks would otherwise duplicate the
  kit 182×); instance lists ship as JSON so engines use their own instancing (InstancedMesh / HISM / PCG).
- Terrain under the course road is lowered 25 cm and capped under every road leg within half-width + 2.5 m — fixes
  the next hairpin leg's terrain covering the road on the Bertinoro climb.
- Bikes are not physics-simulated vehicles: speed comes from the validated power model (spec §5); the visual bike is
  posed kinematically (lean from speed and curvature).
- Superelevation (`bankDeg` in route.bin, + = right edge lower) follows the Italian norm's shape: crowned 2.5 % on
  straights, single slope 2.5–7 % in bends from the class design speed's lateral demand, none in towns, roundabouts or
  turns under 30 m; 15 m run-off smoothing. Applied by the web ribbon, the game bake and the Unreal road spline.
- Hybrid Unreal path (after testing the GPX → Geometry Nodes → Chaos proposal): `import_game_level.py` builds a World
  Partition level from the game chunks (complex collision, Nanite, PhysMats per kit material, HISM per chunk via
  `ARidePrepInstanceActor`, PCG volumes over land-use masks); kit asset ids can be overridden with high-quality assets.
- Web game mode: chunk meshes keep metre UVs (gltfpack `-kv -vtf`), kit textures bound by material name; foliage uses
  outward crown normals (kit) with Lambert shading and no back-face normal flip; calm water gets a subdued specular;
  chunks stream spatially (terrain bbox within 2.5 km, nearest first) because out-and-back legs share land.

## Ride experience (start screen, devices, HUD)
- One start screen (Home) replaces Library → Briefing → Pairing for riding: course strip with a hero render, rider
  profile, devices with live readouts, conditions (race-day field, climatology presets, or custom wind speed/direction,
  temperature, sky, rain, start time in course-local time), ride mode, trainer difficulty, start position (any climb).
  Course analysis and video mode stay one click away.
- Conditions are applied to the ride physics itself (a constant WeatherField replaces the package field), so the
  trainer feels the chosen wind through the FTMS simulation parameters (wind, grade, Crr, Cw = ρ·CdA).
- The Web Bluetooth path is tested end to end with a GATT-level emulator (`apps/client/e2e/webbluetooth-mock.js`):
  FTMS trainer with control-point indications and a resistance model, HRS strap, CPS power meter with crank data.
- Streamed game chunks are shader-compiled with `compileAsync` before they enter the scene: the main thread also feeds
  sensor power to the physics worker, whose 3 s dropout hold must never be triggered by rendering hitches.
