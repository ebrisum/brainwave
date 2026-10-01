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
