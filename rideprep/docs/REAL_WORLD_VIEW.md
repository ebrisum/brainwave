# Riding through the real world

RidePrep has three ways to show a course. You can switch per ride.

| Mode | What you see | Needs | Works in |
|---|---|---|---|
| **Photoreal** | Google Photorealistic 3D Tiles — the photogrammetry behind Google Earth — of the exact course, with our crisp road surface, course banners and your bike's cockpit on top | Google Maps Platform API key (Map Tiles API) | Web client, Unreal (via Cesium for Unreal) |
| **Video** | Real footage of the course, played at *your* virtual speed | A video of the course + the GPX/FIT recorded while filming | Web client |
| **Generated** | Our own world from open data, styled per country/terrain (Dutch red cycle paths and brick, Flemish cobbles, French limestone, alpine rock…) | Nothing | Web client, Unreal |

The cockpit view (camera key **2**) shows drop bars, hoods, gloves and a live bike computer; it is the default in photoreal mode.

## Photoreal (Google 3D Tiles)

1. Google Cloud console → create a project → enable **Map Tiles API** → billing on → create an API key and **restrict** it
   (HTTP referrer = your RidePrep address; API = Map Tiles API).
2. Web: Settings → Real-world view → *Google Photorealistic 3D Tiles* → paste the key. Start a ride.
   Unreal: launch with `-GoogleTilesKey=<key>` (or set `GoogleApiKey` on the `RidePrepWorld` actor; never commit it).
3. Check current pricing and quotas on Google's Map Tiles API pricing page before riding a lot — tiles are billed per
   session/request.

How it lines up: tiles are in Earth-centred coordinates; the course is a flat local map. RidePrep anchors the tiles at
the rider (re-anchored every 750 m so Earth curvature never shows) and calibrates the height by casting rays at the road
(median of road height − tile surface; it absorbs the geoid offset). Tested against a stand-in tileset with a deliberate
46.5 m height error: calibrated to < 0.25 m.

Limits, honestly:
- Photogrammetry is strongest in towns and from a few metres up. At rider eye height, tree canopies are blobs, walls
  smear and parked cars are melted into the road. Rural coverage varies by country.
- Light and shadows are baked in from the capture day; our sun and weather effects only partly apply.
- Terms: runtime streaming only — no caching, offline use or baking into our own assets; the Google logo and data
  attribution stay visible (shown bottom right). Put Google's official logo file at `apps/client/public/google-logo.png`
  (from Google's brand resources); until then a "Google" wordmark is shown.
- No key yet? `gpx2course dev-tileset <courseId>` writes a local stand-in tileset from the package; choose
  *Dev stand-in* in Settings (or `?photoreal=dev` in the URL) to try the mode.

## Video mode

1. Film the course (e.g. GoPro on the bars, 1080p or better, stabilisation on) while recording the ride on a head unit
   or the camera's GPS.
2. Note the video time at the moment the GPS track starts (or sync a clap/beep). That is the *video offset*.
3. Pairing screen → *Video mode* → *Add a synced ride*: upload the GPX/TCX/FIT and the offset (or
   `gpx2course video <courseId> ride.fit --video-offset 4.2`). The video file itself stays on your device.
4. Pick the video file and the synced ride, start. Playback speed = your virtual speed ÷ the speed when filmed; if you
   stop, the video stops; where the footage doesn't cover the course, you ride in the 3D world.

Footage from other people is only usable with their permission (and not from YouTube or Street View).

## Street-level photos in the briefing

Mapillary (open, CC BY-SA) photos at climb starts, technical corners and aid stations. Get a free client token at
mapillary.com/dashboard/developers and paste it in Settings. Google Street View cannot be used this way under its terms.

## Running the Unreal version (on your PC)

This repository contains the Unreal project and plugin, but it has to be built on a machine with Unreal Engine — the
build environment used here has no engine or GPU.

1. Install **Unreal Engine 5.8** (Epic Games Launcher) and Visual Studio 2022 with *Game development with C++*.
2. Install **Cesium for Unreal** (Fab / Epic launcher → *Install to Engine*, or clone it into `apps/unreal/Plugins/`).
   Optional: **glTFRuntime** into `apps/unreal/Plugins/` for baked chunks.
3. Right-click `apps/unreal/RidePrep.uproject` → *Generate Visual Studio project files* → open and build
   *Development Editor*.
4. In the editor create once: an `ARidePrepRider` Blueprint with your cyclist mesh and a cockpit mesh (bars + hands) and
   a bike-computer widget; a `URidePrepAssetMap` (foliage meshes, materials, `MPC_Environment`); a `Ride` map with Sky
   Atmosphere, Volumetric Clouds, Directional Light, Exponential Height Fog and a `RidePrepWorld` actor
   (tick *Photoreal* for the real world). Details in `apps/unreal/README.md`.
5. Start the ride engine, then press Play:
   ```
   pnpm --filter @rideprep/ride-core start -- --package ./courses/<courseId> --virtual
   ```
   Package the game (*Platforms → Windows → Package Project*) for a standalone app.
