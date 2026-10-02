# RidePrep — Unreal Engine target (UE 5.8, pinned)

Unreal is a **view** of the ride. Physics, Bluetooth and recording run in `apps/ride-core`, which streams
MessagePack state at 50 Hz over `ws://127.0.0.1:8765` (schema: `packages/course-format/src/stream.ts`).

## Runtime mode (default)

One packaged app loads any course package at runtime — no editor work per course. Plugin: `Plugins/RidePrepRuntime`.

| Piece | Class / file |
|---|---|
| Package loader (manifest, route.bin, instances.bin, terrain tiles) | `URidePrepCourse` |
| Ride-core client (WebSocket + MessagePack, interpolation) | `URidePrepStreamClient`, `RidePrepMsgPack.h` |
| Terrain (procedural mesh per 3 km tile, async), road ribbon, HISM vegetation, glTF chunk streaming, sun/fog/wind MPC | `ARidePrepWorld` |
| Rider (Control Rig pedal IK from `CrankAngle`, lean, standing, tuck; cameras) | `ARidePrepRider` |
| UMG HUD base | `URidePrepHudWidget` |
| Shared maths, identical to the web client (`poseAt`, ENU↔UE) | `RidePrepCourseMath.h` |

`RidePrepCourseMath.h` and `RidePrepMsgPack.h` are engine-independent and are compiled with g++ in CI
(`apps/unreal/Tests`) — the cross-renderer test checks that the same `s` gives the same position as the web client.

### Project setup (once per project)

1. Install UE 5.8. Optionally add **glTFRuntime** (MIT, github.com/rdeioris/glTFRuntime) and **Cesium for Unreal** under
   `Plugins/` — `RidePrepRuntime.Build.cs` detects them (`WITH_GLTFRUNTIME`, `WITH_CESIUM`).
2. Create a `URidePrepAssetMap` data asset: map instance keys (`tree_deciduous`, `tree_conifer_1`, `hedge`, `prop_0`, …)
   to your Nanite foliage meshes (1 m tall, pivot at the base) and material ids from `materials.json` to material
   instances. Assign a terrain material that uses vertex colour, and an `MPC_Environment` with
   `WindDirX, WindDirY, WindStrength, Gust, Wetness, CloudCover` (foliage sway, wet roads).
3. Map `Ride`: Sky Atmosphere, Volumetric Clouds, a Directional Light and Exponential Height Fog; place an
   `ARidePrepWorld` and assign the asset map, rider class (a BP of `ARidePrepRider` with your rigged cyclist), Sun and Fog.
4. Lumen GI, Nanite and Virtual Shadow Maps are enabled in `Config/DefaultEngine.ini`.

### Ride

```
pnpm --filter @rideprep/ride-core start -- --package ./courses/c_xxx --virtual   # or with a trainer: drop --virtual
# then launch the packaged RidePrep app; it loads the package path from the ride core's hello message
```

Coordinates: `UE.X = E·100, UE.Y = −N·100, UE.Z = U·100` (cm, left-handed, Z-up); one conversion function
(`EnuToUe`) everywhere. glTF chunks use the package's glTF convention (X east, Y up, Z south); `glTFRuntime`
is configured with `TransformBaseType = YForward` — verify the basis once on the target engine version.

## Photoreal mode (real world) and cockpit

Tick **Photoreal** on `RidePrepWorld` and launch with `-GoogleTilesKey=<key>` (Map Tiles API). Google Photorealistic 3D
Tiles stream through Cesium for Unreal; the georeference is re-anchored at the rider every 750 m (origin = rider lat/lon,
actor yawed by −grid convergence) and height-calibrated with line traces at the road. Generated terrain/vegetation/chunks
are hidden; road ribbon, markers and rider stay. The rider switches to **Cockpit** (camera at eye height, cockpit mesh +
bike-computer widget attached to the camera, pedalling bob, corner roll). `TilesetUrlOverride` accepts any tileset — e.g. a
package's `devtiles/tileset.json` (`gpx2course dev-tileset`) to test without a key.

Regional style: colours from the package's `materials.json` tint the road material (`BaseColor` parameter).

## Editor mode ("hero courses")

`Scripts/import_course.py` builds a World Partition level from `unreal/` (16-bit heightmaps 505×505 at 8 m, weight maps,
`road_spline.json`, instance lists via PCG) and saves it; cook it to a pak with BuildCookRun. Budget ≤ 30 min for 180 km.
The script targets the UE 5.8 Python API and must be verified on the workstation (not runnable in CI).

## Render project hand-off (no C++)

`python3 tools/unreal_bundle.py <course package> --out <dir> --zip` packs a Blueprint-only render project
(`RenderProject/`: Python, Editor Scripting, PCG, Movie Render Queue; Lumen/Nanite/VSM/virtual textures on), the scripts,
the built course, the rider and the step-by-step guide (`docs/UNREAL_GUIDE.md`). In the editor:
*Tools → Execute Python Script → Scripts/build_level.py* builds the level; without the RidePrepRuntime plugin the
instances go into HISM components added from Python, and camera rails along the riding line are created for Sequencer.

## Game-art hero level (hybrid pipeline)

`gpx2course game <package>` (see `docs/GAME_ART.md`) bakes textured terrain/roads/buildings per 500 m chunk with a
regional Blender art kit, plus kit instance lists and land-use masks. `Scripts/import_game_level.py` turns that into a
World Partition level:

```
UnrealEditor-Cmd RidePrep.uproject -run=pythonscript \
    -script="Scripts/import_game_level.py --package /data/courses/c_xxx --overrides Config/RidePrepAssetOverrides.json"
```

| Step | Result |
|---|---|
| Kit | `M_RidePrepKit` / `M_RidePrepKit_Masked` (created once), textures, `MI_<material id>` (UVScale = 1/tileM, Tint, Roughness, Metallic) with PhysMats `PM_Asphalt/Setts/Gravel/Grass/Soil/Water/Metal` (surface types in `Config/DefaultEngine.ini`), kit meshes with `<asset>__lod1` as LOD1 |
| Chunks | static mesh actors per chunk mesh at `EnuToUe(origin)`; complex-as-simple collision on terrain, roads and buildings; Nanite on opaque meshes; far field |
| Instances | `ARidePrepInstanceActor` per chunk (HISM per asset, cull distances, collision only for solid props); `--overrides` swaps kit meshes for high-quality assets by asset id |
| PCG | `PCGVolume` per chunk over the land-use mask (graph parameters `LanduseMask`, `LanduseBoundsMinCm/MaxCm`); `ARidePrepRoadSpline` per chunk along the course road (tag `RidePrepRoad`) for exclusion and edge sampling |
| Sun | directional light from the event start (NOAA solar position) |
| Hero road | chunks built with `gpx2course game --hero …`: `h<id>.glb` replaces the chunk's `road_/markings_/defects_/shoulder_` meshes (Nanite, complex collision); pebbles as HISM (`pebble_a/b/c`, culled at 60 m) |
| RVT | `RVT_RoadBlend` + volume over the corridor; roadside meshes draw into it, `M_RidePrepKit_Terrain` blends the terrain toward it with the `RoadMask` vertex colour |
| Rider | `rider_road/tt.glb` (tools/rider) → `/Game/RidePrep/Rider/<bike>`: skeletal mesh + `pedal`, `stand`, `coast` (+ `_drops`) clips |

### Photoreal road (Nanite micro-detail, PCG rules, RVT, PhysMats)

What the brief asked for, and where it lives:

| Brief | Implementation |
|---|---|
| Nanite micro-detail — potholes and gravel as real geometry | `gpx2course game --hero km:44-46.5` (or chunk ranges, or `all`) bakes `game/unreal/hero/h<id>.glb` (`services/course-builder/blender/game/bake_hero_road.py`): the carriageway on a 24 × ~12 cm lattice refined to ~3 × 1.5 cm wherever a defect is — pothole bowls with steep ragged walls and a rough bottom, raised repair patches, bitumen-sealed and open cracks, crumbled edges; the gravel shoulders on a 5 cm lattice with stone relief; loose stones as instances. ~1 M triangles / 25–30 MB per 500 m. Defects are deterministic per course (`gamekit/roadside.py`, densities per surface in the kit's `rules`) |
| PCG rules — trees ≥ 5 m from the edge, gravel on the shoulders | evaluated once in the pipeline (`gamekit/roadside.py`, kit `rules`): tree setback from the road **edge** (`treeSetbackM` 5, hedges 1.5), gravel shoulders by road class, guardrail runs on drops ≥ 1.5 m, bridges and water within 4 m. Every client gets the same world; the UE PCG graph only adds ground detail (below) |
| RVT edge blending | `RVT_RoadBlend` (BaseColor/Normal/Roughness, 4096 × 256 px tiles ≈ 3 cm/texel over 30 km, adaptive) over the corridor; `M_RidePrepKit` writes into it, the roadside meshes draw into it, and the terrain MIs (`MI_<id>_Terrain`, parent `M_RidePrepKit_Terrain`) lerp toward it with `RoadMask` (vertex colour R baked by the chunk bake: 1 at the verge → 0 four metres out) broken up by world-space noise. Without RVT (`--no-rvt`) the same mask blends toward the kit gravel |
| Complex collision | complex-as-simple on terrain, roads, hero road, shoulders, verges and buildings, so the tyre traces hit the real pothole floor |
| Physical materials (asphalt 0.8, gravel 0.4, dust) | `PM_Asphalt` 0.8, `PM_Gravel` 0.4 (+ setts 0.7, grass 0.35, soil 0.45, water 0.1, metal 0.5); patches/sealed cracks are asphalt, potholes/stones/shoulders gravel. `URidePrepSurfaceFeedback` on the rider traces both wheels and turns the surface type into vibration (with jolts from 3 cm height steps), a looping rolling sound per surface (`RollingSounds`), and dust: any FX component tagged `Dust` gets the float parameter `SpawnRate` (gravel 40/s, dirt 25/s at 10 m/s) — e.g. a Niagara sprite emitter with spawn rate bound to the user parameter |
| Chaos vehicle + PID controller | not used for riding (speed belongs to the power-based physics that also drives the trainer). The presentation layer is `RidePrep::LaneKeeper` (`RidePrepLaneKeeper.h`): a critically damped (PD) controller holding a realistic line inside the road (keep right ~1 m from the edge, or the racing line with `bRacingLine`) with lateral speed/acceleration limits, the matching yaw and lean, and a pedal-synchronous weave on slow climbs. It is the same code path as the web client (cross-tested to 1e-6) |

**Rider.** `ARidePrepRider` loads `/Game/RidePrep/Rider/<Bike>` when its Blueprint has no mesh, turns the model to face
the road from its wheel bones, and plays the baked clips by crank angle (`HandPosition` = hoods or drops). The mesh hangs
under a scene root at the tyre contact, so leaning pivots on the road.

Rider speed stays with the physics model (ride-core); the bike is posed kinematically along the route with lean
`atan(v²/(g·R))` plus the lane keeper's line, yaw and lean.

### PCG_GroundDetail (author once in `/Game/RidePrep/PCG/`)
Graph parameters: `LanduseMask` (Texture2D), `LanduseBoundsMinCm`, `LanduseBoundsMaxCm` (Vector).
1. **Get Actor Data** (tag `g*_terrain`, merge) → **Surface Sampler** (points per m² by detail density).
2. **Get Texture Data** (texture = `LanduseMask`, transform from the bounds parameters) → **Sample Texture** on the
   points → attribute `$Density`/`Class` (value × 255 = index into `landuseClasses` in `game/index.json`).
3. **Difference** with **Get Spline Data** (actors tagged `RidePrepRoad`, the course road) widened by the road
   half-width + shoulder, and **Get Actor Data** of `g*_sideroads` (exclusion), then **Distance** to the spline to
   split: < 1.5 m → shoulder weeds/stones (the hero road already has the gravel); > 1.5 m → per-class **Attribute Filter**.
4. Per class: **Static Mesh Spawner** — grass_dry/grass_green: grass clumps + wild flowers; stubble: straw; soil_ploughed:
   clods; vineyard_soil: inter-row grass; saltpan_water: none (salt crust at the edges); urban_ground: weeds at walls.
