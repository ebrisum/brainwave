# Emilia-Romagna 70.3 bike course in Unreal Engine — step by step

This folder is a ready-to-open Unreal project with the IRONMAN 70.3 Emilia-Romagna bike course inside (90.5 km, 270 m
of climbing, Cervia → Bertinoro → Cervia). One script builds the level; you light it, swap in photoreal assets where you
want, put the rider on the road and render with Movie Render Queue.

The course was built from the official GPX and open map data by RidePrep's pipeline (`gpx2course`). Unreal does
the rendering: Lumen, Nanite, Megascans materials, Sequencer, Movie Render Queue. The pipeline did the parts Unreal
can't do from a GPX: real terrain and roads, buildings, land use, trees, guardrails, road defects, and the rigged rider.

> The import script has not been run in a real Unreal Editor yet: it was written against the UE 5.4–5.8 Python API and
> logs and continues when something differs. If a step fails, copy the Output Log lines starting with `[RidePrep]`.

## What's in the folder

| Path | What it is |
|---|---|
| `RidePrepRender.uproject` | the project (Blueprint-only: **no Visual Studio needed**) |
| `Config/` | renderer settings (Lumen, Nanite, Virtual Shadow Maps, virtual textures for RVT), surface types, `RidePrepAssetOverrides.example.json` |
| `Scripts/build_level.py` | **the one-click import** (calls `import_game_level.py`) |
| `Course/` | the course: 182 chunks of 500 m (terrain, road, shoulders, verges, buildings, side roads, road defects), far terrain, ~62 000 trees and props, 3.7 km of guardrail, land-use masks, art-kit textures and meshes |
| `Course/game/unreal/hero/` | the **high-detail road** for km 43–44 (Nanite: real potholes, cracks, patches, gravel stones — ~1 M triangles per 500 m) — from the `_hero` zip |
| `Rider/` | `rider_road.glb`, `rider_tt.glb`: rider + bike, one skeleton, with pedalling clips |
| `ATTRIBUTION.txt` | data credits (keep the OpenStreetMap/Overture credit with published renders) |

## What you need

- **Unreal Engine 5.4 or newer** (5.6+ recommended) from the Epic Games Launcher. No C++ compiler.
- A GPU with Nanite/Lumen support (RTX 2070 / RX 6700 class or better), 32 GB RAM, ~15 GB free disk after import.

## Step 1 — Unzip

1. Put all zips in one place, e.g. `D:\RidePrep` (a **short path** — Windows dislikes long ones).
2. Unzip **every** zip there — `…_part1of3`, `…_part2of3`, `…_part3of3` and `…_hero` — choosing "extract here" so they
   all fill the same `RidePrep_EmiliaRomagna703` folder (the parts only split the files for transfer; the `_hero` zip
   fills `Course/game/unreal/hero/`). Overwrite if asked.

## Step 2 — Open the project

1. Open `RidePrepRender.uproject` — easiest from the **Epic Games Launcher**: *Unreal Engine → Library → Launch* your
   engine, then in the Project Browser click **Browse…** and pick the file. Double-clicking also works once Windows
   knows the file type: if it asks "How do you want to open this file?", choose
   `C:\Program Files (x86)\Epic Games\Launcher\Engine\Binaries\Win64\UnrealVersionSelector.exe` (*More apps →
   Look for another app on this PC*, tick *Always*) — it then asks which engine version to use. If Unreal says the
   project was made with a different engine version, choose *More Options → Convert in-place* (safe: the project has
   no content yet; this only records your version).
2. The first start compiles shaders: 10–30 minutes. Let it finish.
3. Check *Edit → Plugins* — these must be on (they are listed in the project; enable them and restart if not):
   **Python Editor Script Plugin**, **Editor Scripting Utilities**, **PCG**, **Movie Render Queue**.

Already set in `Config/DefaultEngine.ini`: Lumen global illumination and reflections, Virtual Shadow Maps, Nanite,
TSR anti-aliasing, **Virtual Texture support** (needed for the road-edge blending), and the surface types Asphalt,
Setts, Gravel, Grass, Soil, Water, Metal.

## Step 3 — Build the level (one script)

1. *Tools → Execute Python Script…* → choose `Scripts/build_level.py`.
2. Wait. The whole course takes roughly 20–60 minutes; a progress dialog stays up meanwhile.
   **Try a few chunks first** (2–3 minutes): *Window → Output Log*, and in the command box (`Cmd`) type the full path
   with the chunks you want, e.g.
   `py "D:/RidePrep/RidePrep_EmiliaRomagna703/Scripts/build_level.py" --chunks 84,85,86,87,88`
   (a chunk is 500 m: chunk 86 = km 43.0–43.5; 88–92 = the Bertinoro climb). Running it again without `--chunks`
   builds everything; delete the test level first (or pass `--level MyTest` for the test).
3. When it is done, open the level in the Content Browser: `Content/RidePrep/Courses/c_28f22c31632ed08b1ba7_game/`.

What the script built:

| Outliner folder / asset | Content |
|---|---|
| `RidePrep/Chunks/gNNN/` | per chunk: `gN_terrain`, `gN_road`, `gN_markings`, `gN_shoulder`, `gN_verge`, `gN_defects`, `gN_sideroads`, `gN_buildings`, `gN_instances` (trees, hedges, vines, reeds, guardrails, signs as instanced meshes) |
| `hero_road_86/87`, `hero_shoulder_86/87` | the Nanite road at km 43–44 (replaces that stretch's simple road) |
| `RidePrep/Rails/RideLine_*` | camera rails along the riding line (keep right, ~1 m from the edge): `start` (km 0–2), `climb1` (Bertinoro, km 44.0–46.6), `hero_km43.0-44.0` |
| `RidePrep_RoadBlend_RVT` | the Runtime Virtual Texture volume: the terrain blends into the roadside, no "sticker" edges |
| Directional Light | already turned to the sun position of race morning (20 Sep, 08:45) |
| `Content/RidePrep/Rider/road`, `/tt` | rider skeletal meshes and clips |
| `Content/RidePrep/PhysMats` | `PM_Asphalt` (friction 0.8), `PM_Gravel` (0.4), … on the road materials |

It is a **World Partition** level: *Window → World Partition → World Partition Editor*, drag a box around the area you
want, right-click → **Load Region from Selection**. Unloaded areas are not shown.

## Step 4 — Make it look real

The level uses RidePrep's procedural art kit: correct layout everywhere (every tree, field, house and guardrail is where
the map says), simple game-style models. For photoreal frames:

1. **Light and sky** — the OpenWorld template already has Sky Atmosphere, Sky Light, Volumetric Clouds and Exponential
   Height Fog. Turn on *Volumetric Fog* on the height fog for morning haze; keep *Real Time Capture* on the Sky Light.
2. **Post Process Volume** (place one, tick *Infinite Extent (Unbound)*): set exposure *Min EV100* = *Max EV100* so
   brightness doesn't pump during a shot (adjust the value by eye), *Lumen Final Gather Quality* 2, *Lumen Reflections
   Quality* 2, bloom and vignette low.
3. **Swap the trees and props for photoreal ones** — get trees from **Fab** (Quixel Megascans, free with Unreal): stone
   pine (*Pinus pinea*), cypress, Lombardy poplar, olive, oak, broadleaf, fruit trees, reeds, a W-beam guardrail.
   Copy `Config/RidePrepAssetOverrides.example.json` to `Config/RidePrepAssetOverrides.json`, put your asset paths in
   it (right-click an asset → *Copy Reference*, keep the `/Game/...` part), and run Step 3 again — every kit tree is
   replaced at its exact position. Kit asset ids: `tree_broadleaf`, `tree_oak`, `tree_fruit`, `tree_stone_pine`,
   `tree_poplar`, `tree_cypress`, `tree_olive`, `tree_palm`, `hedge_4m`, `vine_row_5m`, `reeds`, `guardrail_4m`,
   `delineator`, `streetlight`, `race_barrier_2m`, `flamingo`, `campanile`, `sign_*`, `town_sign_*`, `km_marker`.
   Use `yawDeg` and `scale` in the JSON if an asset is authored turned or at another size.
4. **Road and ground materials** — `Content/RidePrep/Kits/emilia-romagna/Materials/` has one material instance per
   surface (`MI_asphalt`, `MI_asphalt_worn`, `MI_asphalt_patch`, `MI_tar_seal`, `MI_pothole`, `MI_shoulder_gravel`,
   `MI_grass_dry`, `MI_stubble`, …). Replace their *BaseColor* and *Normal* textures with Megascans surfaces and keep
   *UVScale* (= 1 / tile size in metres). Terrain surfaces have a `…_Terrain` twin with the road-edge blend.
5. **Ground detail (optional)** — grass clumps and flowers with PCG: see "PCG_GroundDetail" in
   `apps/unreal/README.md` of the RidePrep repository (each chunk already has a PCG volume and a land-use mask).

## Step 5 — Put the rider on the road (Sequencer)

1. *Cinematics* (clapperboard on the toolbar) → **Add Level Sequence**, name it e.g. `Ride_Bertinoro`.
2. **The path**: in the Outliner pick a rail, e.g. `RidePrep/Rails/RideLine_climb1`, drag it into Sequencer, add the
   track **Current Position on Rail**: key `0` on the first frame and `1` on the last.
   Length in frames = rail length ÷ speed × frame rate. Bertinoro climb (2.64 km) at 15 km/h (4.17 m/s), 30 fps:
   2640 / 4.17 × 30 ≈ 19 000 frames (10.5 min). Render a part of it or move the keys to film a stretch.
3. **The rider**: drag `Content/RidePrep/Rider/road/rider_road` (the skeletal mesh) into the level, then in the Outliner
   drag it **onto the rail** — it attaches to the rail mount. Set its location and rotation to 0 (Details panel). If it
   faces sideways, set rotation Z to 90 or −90.
4. **Pedalling**: drag the rider into Sequencer → *+ Track → Animation* → pick a `_rolling` clip (the wheels turn with
   the cranks) and stretch the section over the whole shot (it loops). Right-click the section → *Properties* →
   **Play Rate** so the wheels match the rail speed:

   | Clip | When | Play Rate for speed v (km/h) | Cadence |
   |---|---|---|---|
   | `pedal_rolling` | flat, seated (hoods) | v / 11.35 | 30 × rate rpm |
   | `pedal_drops_rolling` | flat, in the drops | v / 11.35 | 30 × rate |
   | `climb_rolling` | seated climbing | v / 7.57 | 30 × rate |
   | `stand_rolling` | out of the saddle, steep (> 8 %) | v / 3.78 | 30 × rate |
   | `coast_rolling` | freewheeling | v / 3.78 | — |

   Examples: flat at 34 km/h → `pedal_rolling` rate 3.0 (90 rpm); Bertinoro at 15 km/h → `climb_rolling` rate 2.0
   (60 rpm); the 13 % ramp at 9 km/h → `stand_rolling` rate 2.4 (71 rpm). TT bike: `rider_tt` with the same clip names
   (aero position).
   Cut between clips at a section boundary (or overlap two sections a few frames for a blend).
5. **Cameras**: in Sequencer click the camera button (*Create Camera*) — it adds a Cine Camera Actor and a Camera Cut
   track. For a chase shot attach the camera to the same rail and offset it (X −550 cm, Z 200 cm, pitch −8°); for a
   side shot Y 500 cm, yaw −90°. Or animate a free drone camera.
6. Lens: 24–35 mm, aperture f/2.8–5.6 with focus tracking on the rider for depth of field.

## Step 6 — Render

1. *Window → Cinematics → **Movie Render Queue*** → *+ Render* → your sequence.
2. Settings (click *Unsaved Config*):
   - *Output*: resolution 3840 × 2160 (or 1920 × 1080), frame rate of the sequence, file name format.
   - *Anti-aliasing*: Spatial Sample Count 1, Temporal Sample Count 8–16 (motion blur and clean edges);
     **Render Warm Up Frames** 32 and *Use Camera Cut for Warm Up* on (lets Lumen, TSR and streaming settle).
   - *Game Overrides*: Cinematic quality on.
   - *Console Variables* (optional): `r.Lumen.ScreenProbeGather.ScreenTraces.HZBTraversal.FullResDepth 1`,
     `r.Shadow.Virtual.SMRT.RayCountDirectional 16`.
   - Output type: PNG or EXR image sequence (compose in an editor) or Apple ProRes.
3. *Render (Local)*. Expect seconds per frame at 4K with temporal samples.

## More of the course in high detail

The bundle has the Nanite road for km 43–44. Any other stretch can be generated (`gpx2course game <course> --hero
km:44-46.5` in the RidePrep repository, ~25–30 MB per 500 m; the whole course is ~5 GB). Unzip the extra
`Course/game/unreal/hero/` files into the same folder and run Step 3 again.

## Good to know

- **Scale and axes**: 1 Unreal unit = 1 cm. X = east, Y = south, Z = up (course origin in Cervia, 44.2502 N,
  12.3654 E). Chunk actors sit at their chunk origin; the course spans ~20 × 13 km.
- **Collision**: complex-as-simple on terrain, roads and the hero road, so traces hit the real pothole floor.
- **Live riding with a smart trainer in Unreal** needs the full RidePrep project (`apps/unreal` in the repository) with
  its C++ plugin and Visual Studio 2022 — not needed for rendering.

## If something goes wrong

| Symptom | Fix |
|---|---|
| "Missing Project Settings! Shader Model 6 (SM6) is required…" | *Project Settings → Platforms → Windows*: Default RHI **DirectX 12**, *D3D12 Targeted Shader Formats* tick **SM6**, restart the editor (Nanite and Virtual Shadow Maps need it) |
| No *Execute Python Script* menu | enable *Python Editor Script Plugin*, restart |
| Import stops with an error | the Output Log has `[RidePrep]` lines; most steps warn and continue — send the log |
| Everything grey/checkered | shaders still compiling (bottom-right counter) |
| Trees missing | load the World Partition region; check `gN_instances` in the Outliner (small props — reeds, vines, hedges, delineators — are culled beyond 250–600 m; trees are not) |
| Hard edge where terrain meets the verge | *Project Settings → Rendering → Virtual Textures → Enable virtual texture support* must be on (restart) |
| Rider faces sideways on the rail | rotation Z ± 90 on the rider |
| Editor slow | load fewer World Partition cells; `t.MaxFPS 30` in the console while editing |
