# Verdio: ground-floor blocking for Blender

This folder holds a parametric conceptual massing of the Verdio poshtel ground floor, in its landscape, plus a lighting, camera and plaster workflow guide.

**Direction: a dune house, not a modern box.** Verdio is a Dutch coastal farmhouse (hand-moulded brick, red pantiles, an exposed oak beam ceiling) crossed with an English country house (panelling, hearths, window seats). It sits low in the dunes. Its coast side is a deep veranda where most of daily life happens half outdoors.

**The garden is laid out like a hillside resort,** such as Shanti Natural Panorama View in north Bali, but on a temperate coast:
- **Terraces to the sea.** The house terrace sits 4.6 m above the sea. In front of the veranda, a natural swimming pond overflows toward the view. Terraces step down from there: a wildflower meadow, then tulip strips that echo the bulb fields behind the Dutch dunes, then a boardwalk to the beach.
- **Garden pavilions.** Four reed-thatched pavilions sit in dense planting on the dunes either side, each with an open-air living veranda and an outdoor soaking tub. Boardwalks link them to the house.

The friction is still there, between salt, sweat and athletic performance on one side and heavy, dark, traditional interiors on the other. There's nothing in it that reads as contemporary.

| File | What it is |
|---|---|
| `verdio_ground_floor.py` | One script. It builds the 400 m² plate, walls, brick facade, the Kamer en suite, oak French doors and shutters, the veranda with its vine pergola and outdoor kitchen, an oak beam ceiling, panelling and blocking props. It also builds the terraced garden with its pond, reed bed, meadow and tulip strips; the four thatched pavilions; boardwalks; the dunes, beach and sea; grass, shrubs, pines and oaks; a training yard; and a placeholder upper floor with a pantile roof. On top of that it sets up materials (including a procedural Rotband plaster), sun, sky, light portals, practical lights, cameras and Cycles settings. It can also pull CC0 scanned assets from Poly Haven (see §6). |
| `previews/` | Low-sample Cycles renders (40 spp, CPU, 960 × 640, procedural stand-ins, Poly Haven offline) straight out of the script, with no manual edits. |

The script was tested headless on Blender 4.2 LTS. API names that changed in 4.x (Principled inputs, displacement method, particle settings) are handled. If you're on 5.x and the Nishita sky type has been renamed, the world falls back to a flat sky. Use an HDRI there anyway (see §4).

```
Scripting workspace → Open → verdio_ground_floor.py → Run Script
# or
blender -b -P verdio_ground_floor.py
```

Re-running rebuilds the `VERDIO` collection in place. Edit the parameters at the top of the script and run it again. Useful parameters:

| Parameter | Default | What it does |
|---|---|---|
| `FACADE_OPEN` | `1.0` | Swings all French doors open and folds the shutters back against the brick. |
| `ES_OPEN` | `0.0` | Slides the en suite leaves into their pockets. |
| `ENSUITE_FRAME` | `"iron"` | Choose `"iron"` (hand-forged, blackened) or `"oak"` for the en suite framing. |
| `PERGOLA_TO_X` | `9.5` | How much of the veranda is open vine pergola rather than tiled roof. |
| `SITE_ROTATION_DEG` | `0` | Set to `-90` if the coast faces west, as on the Dutch North Sea coast. |
| `QUALITY` | `"preview"` | `"preview"` is 128 spp at half resolution. `"final"` is 1024 spp at full 3000 × 2000, with remeshed and displaced plaster. |
| `USE_POLYHAVEN` | `True` | Downloads and uses scanned textures, plants and an HDRI when Poly Haven is reachable. Otherwise the procedural stand-ins are used. |
| `PAVILIONS` | 4 sites | Position and rotation of each garden pavilion. Add or remove entries. |
| `TERRACE_STEPS`, `POND` | – | Levels of the garden terraces and the pond's footprint. |
| `GRASS_COUNT` | `9000` | Marram tussock count. Lower it for a faster viewport. |
| `BUILD_LANDSCAPE`, `BUILD_UPPER` | `True` | Turn these off for fast interior-only work. |

---

## 1. Living between inside and outside

Seven moves make the house feel like it's part of the dunes, not placed on them:

1. **One floor, inside and out.** The culinary core's Frisian terracotta runs straight out under the veranda at the same level. There's a flush brass strip at the door line and no step. You don't notice going outside to cook.
2. **One ceiling rhythm, inside and out.** The dark oak joists sit on a 0.75 m grid under limewashed boards. The veranda rafters use the same grid, so the ceiling seems to carry on through the facade.
3. **A facade that opens.** The coast side is a run of oak French doors with fixed fanlights between brick piers: two to the culinary core, three to the lounge. They swing out fully onto the veranda. The endurance room has two pairs that open onto a sand training yard. The library, mudroom and west windows get Space Blue *luiken*, traditional Dutch shutters that fold flat against the brick.
4. **The veranda is a room.** It is 3.6 m deep and runs 25 m on oak posts that stand on the facade piers.
   - Over the outdoor kitchen there's an open **vine pergola**: wood-fired oven, long silvered-oak table and benches, and dappled light through the leaves.
   - Over the lounge and the porch it has a **pantile lean-to**: linen daybeds facing the sea, the beach entrance, a board rack and an outdoor shower.
5. **Views into nature from every room.** The south foredune is kept below eye height, so the sea stays in view from the lounge. The library's north windows have 500 mm sills with linen-cushioned window seats looking onto grass and pines. The endurance room trains facing the yard and the dunes.
6. **Nature indoors.** Potted olive and fig trees sit in the lounge, culinary core, library and gym. Every material is natural: lime plaster, oak, terracotta, bluestone, brass, linen, wool and leather.
7. **Arriving from the beach.** A silvered-oak boardwalk crosses the foredune to the porch. Sand gets rinsed at the outdoor shower first. Then you come in through the mudroom (terracotta, coir mat, oak boot bench), through an oak-cased opening onto dark oak.

**What was removed to lose the modern look:**

| Removed | Replaced with |
|---|---|
| Polished concrete in the wet core and gym | Bluestone flags in the wet core; an oak floor in the gym, like an old gymnasium, with natural tatami |
| A flat white ceiling | Exposed oak joists, an oak girder and limewashed boards |
| Powder-coated steel windows and doors | Oak frames with divided lights, brass knobs and hand-forged iron |
| LED strips in the gym | Forged-iron lanterns, with daylight from the yard doors |
| A flat, plastered facade | Hand-moulded Waal-format brick with lime joints, a brick sill to every window, and a steep pantile roof with a chimney stack |

**One tension to resolve.** The brief makes the endurance room climate-controlled, and the new direction opens it to the yard.
- In the model, the yard doors open in mild weather and close for conditioning. The en suite stays sealed either way, so the library is never affected.
- If the yard doors are open most of the time, put the endurance room's conditioning on presence and door sensors.

## 2. The plan

Plate: 25.0 × 16.0 m = 400 m² gross. The coast is south (−Y). Exterior walls are 350 mm, internal walls 200 mm masonry, and the clear height is 3.60 m. The veranda adds 90 m² covered outdoors.

```
                    TRAINING YARD (sand, pull-up rig)
                          ^ doors ^
    N  y=16.00
    +-------------------------------------------------+
    |  LIBRARY / COWORK      #  ENDURANCE      | WET  |
    |  dark oak, panelled    #  KICKR + BJJ    | CORE |
    |  80.6 m2               #  58.5 m2        |20.7  |
    +------------------+-----#-----------+-----+------+  y=8.75
    |  CULINARY CORE   |  LOUNGE         | MUDROOM    |
    |  grill + table   |  dark oak       | terracotta |
    |  75.1 m2         |  73.0 m2        | 50.2 m2    |
    +==||====||========+==||===||===||===+===||=======+  y=0   || = French doors
    :  VERANDA 3.6 m: terracotta runs straight through     :
    :  oven, long table  |  daybeds          |  porch, shower:  y=-3.6
    :  vine pergola      |  pantile lean-to roof             :
    x=0               9.5   12.5        18.5  21.5   25
                                            | boardwalk
                  ~~~~~~  foredune, beach, sea  ~~~~~~
    #  = Kamer en suite partition (x = 12.5)
```

The total net area is 358 m². The rest is walls and the 600 mm partition.

**Why this arrangement**

- **Wet-to-dry sequence.** Beach → boardwalk → outdoor shower on the porch → Space Blue double door → mudroom → a 2.6 m oak-cased opening → lounge. The terracotta-to-oak change sits exactly on the wall centre-line, under a flush brass strip. Athletes can also go mudroom → wet core → endurance room and never cross the oak.
- **North-facing rear band.** The endurance room gets no solar gain and screens in the library get no glare. The low coastal sun goes to the culinary core, lounge and mudroom. The veranda roof shades them from high summer sun but lets the low autumn and winter sun in: at 16° elevation, the sun reaches about 10 m into the house under the 2.85 m eave.
- **The culinary core** has a brick grill hearth with an open charcoal well and a plastered hood. A 5.4 × 1.2 m oak table with a 100 mm slab top runs parallel to it. The core continues outside to the wood-fired oven and the long outdoor table under the vines.
- **The lounge** has a chimney breast, oak mantel and terracotta hearth, an oak dado, oxblood chesterfields and a wool rug. Three pairs of French doors open onto the daybeds.
- **The library** has oak panelling to 2.40 m, a full-wall bookcase, an oak refectory table on the camera axis, and window seats onto the dune.

## 3. The structural anchor: the Kamer en suite

The classic 1930s Dutch en suite partition is a deep wall with built-in cabinets either side of a wide pair of sliding doors, and a glazed *bovenlicht* above a rail called the *kalf*. The model keeps that anatomy. The framing is **hand-forged, blackened iron**, which keeps the original brief's "matte black frame with glass" but in a smith's finish, satin with faint hammer marks, not powder coat. If you want no metal at all, set `ENSUITE_FRAME = "oak"`.

```
 PLAN (600 mm deep)          library | vitrine | pocket | vitrine | endurance
                                     |  200    |  200   |  200    |
                                                ^      ^
                                    skin A track   skin B track  (100 mm acoustic cavity)

 ELEVATION   plaster pier | vitrine 1.3 | opening 3.2 m: 2 skins × 2 pocket leaves | vitrine 1.3 | pier
             kalf at 2.75 m · double-glazed bovenlicht to 3.30 m · plaster bulkhead to 3.60 m
```

- **Two independent glass skins.** Each skin has two leaves on 2 × 5 divided lights, with a 16 mm laminated pane. The skins sit 100 mm apart. That double skin keeps the rooms acoustically and climatically separate while the sightlines stay open.
- **Pockets and vitrines.** The leaves slide into a 200 mm cavity behind the oak pocket walls of the vitrines. Each vitrine has an oak drawer base and glazed display doors with oak shelves above.
- **Animate it.** Drag `open` on `EnSuite_CONTROL` from 0 to 1 and all four leaves slide 1.6 m into their pockets.
- **Real-world notes.**
  - Specify acoustic laminated glass and drop seals.
  - Seal the endurance skin tighter than the library skin, so humid gym air can't condense in the cavity.
  - Keep the gym at slight negative pressure relative to the library.

## 4. Lighting and camera

### HDRI choice

The ground, the sea and the vegetation are now modelled, so the sky only has to be sky:

1. **Use a "pure sky" HDRI.** It should be partly cloudy, with the sun 10–25° above the horizon. Poly Haven has many in `_puresky` variants; filter by *Sky* and *Unclipped*. A pure sky won't fight the modelled dunes the way an HDRI with its own ground plate would. Partly cloudy gives soft, directional fill and a sky with character.
2. **Let the Sun lamp carry the direct light.** The script places it at bearing 235° (south-west), 16° elevation, 4.5 W/m², 0.6° angular size, warm 1.0/0.86/0.72. Rotate `HDRI_ROTATION_DEG` until the HDRI's bright quadrant matches `SUN_AZIMUTH_DEG`.
3. **The "being in nature" light** is golden hour with haze. Keep the sun at 10–20°. The procedural fallback sky already uses `dust_density = 2.5` for salt haze off the water. For hero exteriors, add a very thin world Volume Scatter (density 0.0005–0.001). That softens the far dunes and the sea into the sky, the way coastal air does.
4. **Real site.** On the Dutch North Sea coast the sea is to the west. Set `SITE_ROTATION_DEG = -90` and put the sun at 250–270° for golden hour over the water.

### What sells the indoor/outdoor feeling

- **Dappled light.** The vine pergola is a single plane whose shader cuts out leaf clusters, so it throws moving pools of sun across the outdoor table and in through the culinary doors. For a breeze, switch the vine shader's cluster Noise to 4D and drive its W input with `#frame/200`.
- **Sun reaching deep inside.** Low sun passes under the veranda eave and across the terracotta and oak floors, so inside and outside share the same light.
- **Seeing out.** Frame interiors so an open door or window shows grass, dune or sea in the frame. That's what `CAM_06_Culinary_Out_To_Sea` and `CAM_01_Library_EnSuite` do.
- **Wind.** Marram grass is hair. Add a Wind force field from the south-west with strength 1–2 and turbulence, and enable *Hair Dynamics* to bend it. Even in a still image, slightly combed grass reads as weather.

### Settings the script applies (and why)

| Setting | Value | Reason |
|---|---|---|
| Engine | Cycles | Bounce light in dark rooms, hair, and true displacement. |
| Light portals | An area light flagged as a portal in every exterior window and door | Much less noise from sky light entering small openings. |
| Glass | Mix by *Is Shadow Ray* with Transparent BSDF | Sunlight passes through window glass instead of casting black shadows. |
| Caustics | Off, with *Filter Glossy* at 1.0 | Interiors don't need them, and they cause fireflies. |
| Bounces | Diffuse 6, transmission 12, transparent 24 | For the dark oak rooms, the en suite glass layers and the vine cut-outs. |
| Clamp indirect | 10 | Kills fireflies from glossy oak and brass. |
| View transform | AgX, Medium High Contrast, exposure +1.5 | Holds the sun patches without crushing the oak. Raise exposure, not sky strength. |
| Practicals | 2700 K iron pendants, lanterns, desk lamps, fire, oven and grill embers | Warm light only; there are no cool LEDs anywhere. |

Albedo discipline: keep plaster around sRGB 190–220 (linear about 0.5–0.7), not white, and oak at no less than about sRGB 25. Values darker than that lose grain under any tonemapper.

### Cameras (all built by the script)

| Camera | Shot |
|---|---|
| `CAM_05_Beach_to_House` | From the beach, up the terraces to the house, with the thatched pavilions on the dunes either side. Shot level with shift. |
| `CAM_07_Veranda_Pond_Panorama` | From the veranda over the pond and reed bed, past the overflow edge, to the sea. This is the "panorama" shot. |
| `CAM_08_Garden_Pavilion` | From a pavilion's front lawn into its open-air living veranda under the thatch. |
| `CAM_06_Culinary_Out_To_Sea` | From the culinary core, down the table, through open French doors and the vine pergola to the sea. |
| `CAM_01_Library_EnSuite` | Down the refectory table into the en suite, with the endurance room and its yard doors beyond. |
| `CAM_04_Endurance_to_Library` | The reverse view: from the mat through two glass skins into the library. |
| `CAM_02_Mudroom_Threshold` | Terracotta, the oak-cased threshold, then the lounge. |
| `CAM_03_Culinary_Hearth` | From the terrace doors toward the grill hearth and the table. |
| `CAM_00_Plan_Ortho` | Top-down. Hide `Ceiling_*`, `Veranda_Structure`, `Veranda_Vine_Pergola`, `Pavilion_Roof_Thatch*` and the `VRD_10_UpperMassing` collection first. |

Each camera has an `exposure_ev` custom property. The script installs a handler that applies it whenever that camera becomes active or a render starts: +1.5 EV for interiors, 0 for exteriors. A handler only lives for the current Blender session, so after reopening the .blend, run the script again or set Color Management → Exposure by hand.

Camera rules for this brief:
- **Two-point perspective.** Keep the camera level and reframe with **Shift Y**, never tilt. The exterior camera already does this.
- **Lens and height.** Use 21–28 mm on a 36 mm sensor for rooms, 28–35 mm for exteriors, and 50 mm for material vignettes: the brass strip on the floor seam, a shutter hinge on the brick, vine shadows on plaster. Shoot from 1.2–1.6 m.
- **Foreground nature.** In exteriors, put grass in the bottom of the frame. In interiors, let a potted olive or an open door edge into the frame.

## 5. Procedural Knauf Rotband plaster

Rotband is a hand-floated gypsum base coat. Left raw, it is a warm pinkish putty with cloudy drying marks. It is the one material carried through every room, and it is what makes the house feel hand-made. Its tactile quality comes from three overlapping scales of relief:

| Scale | Real size | Node | Where it goes |
|---|---|---|---|
| Macro undulation of the float coat | 0.8–1.5 m wavelength, ±1–3 mm | Noise, scale 0.8, detail 3 | **Material Output → Displacement** (Displacement node, scale 0.004, midlevel 0.5) |
| Trowel pads and lap ridges | 200–400 mm pads with burnished edges | Domain-warped Voronoi: *Smooth F1* for the pads, *Distance to Edge* for the ridges | Bump 1 (strength 0.2, distance 2 mm) |
| Grain / tooth | < 1 mm | Noise, scale 600, detail 8 | Bump 2 (strength 0.12, distance 0.4 mm), chained after Bump 1 |

The script builds this as `VRD_Plaster_Rotband`:

```
TexCoord.Object ─┬─ Noise(0.8) ── macro ──────────────────────┬─► Displacement ─► Output.Displacement
                 │                                            └─► tone ─► ColorRamp ─► Base Color
                 ├─ Noise(1.5).Color ×0.6 + Object  (domain warp: turns cells into trowel sweeps)
                 │     └─ Mapping (scale Z 1.5: strokes run horizontal)
                 │           ├─ Voronoi Smooth F1 ── pads ──┐
                 │           └─ Voronoi Dist-to-Edge ─ MapRange(0–0.035 → 1–0) = ridges
                 │                                           ├─► Bump 1 ─► Bump 2 ─► Normal
                 └─ Noise(600) ── grain ───────────────────────────────┘
ridges ─► MapRange → Roughness 0.92 (matte) … 0.82 (burnished laps)
Sheen 0.15 (dusty grazing-angle sheen)
```

Key points:
- **One noise per frequency, one destination each.** Macro goes only to displacement, and fine detail goes only to the BSDF normal, so nothing is counted twice. In *Bump Only* mode, Cycles turns the displacement output into bump automatically. Switch to real geometry and the same noise moves real vertices.
- **Domain warping** is what turns Voronoi cells, which look like crystals, into curved trowel sweeps. The warp amount (0.6) and the Mapping Z scale are the two values to tune.
- **Keep the laps subtle.** If the ridge mask drives colour or bump too hard, the wall reads as crazy-paving flagstones and not plaster. The first preview pass did exactly that. Leave its colour weight at about 0.05 and let the grazing light do the work.
- **Object coordinates** keep the texture locked to real metres. If you scale a wall object, apply the scale (Ctrl+A → Scale) or the texture will stretch.
- **Colour.** The raw Rotband ramp runs from `#C2B19F` to `#DDD2C4`. For a limewashed finish, change it to `#E4DCCD` → `#EFE8DC` and drop sheen to 0.05.

### Modifier stacks: from bump to real geometry

The walls are built as separate cuboids (piers, aprons, lintels). That's ideal for blocking, but don't bevel them or subdivide them directly: every joint would show as a groove. Unify the walls first:

**A. Hero renders in Cycles** (`HERO_PLASTER = True` in the script)
1. **Remesh** (Voxel, 0.03–0.04 m, Smooth Shading). This fuses all the wall pieces into one watertight skin with even quads. It also softens every arris slightly, which is exactly how a hand-plastered corner looks.
2. Set the material to **Displacement and Bump** (Material Properties → Settings → Surface → Displacement). The macro noise now physically moves the wall surface, and the trowel and grain stay as bump. That's one source of truth.
3. Optional extra density for close-ups: add a **Subdivision Surface** modifier (Simple) after Remesh and enable **Adaptive Subdivision**. In Blender 4.x that needs Render → Feature Set → *Experimental*; newer versions have been moving it out of experimental, so check yours. Use a dicing rate of 1 px.

**B. EEVEE or viewport** (no shader displacement)
1. Apply **Remesh** (Voxel, 0.04 m).
2. Add a **Displace** modifier: a new *Clouds* texture with size 0.8 and depth 2, Coordinates *Global*, Direction *Normal*, strength 0.003–0.004, midlevel 0.5.
3. Add a second **Displace** with a *Voronoi* texture (size 0.3, Intensity 1), strength 0.0012, for the trowel pads.
4. Add **Smooth by Angle** (30°) and keep the shader's bump nodes for the grain.

**C. Geometry Nodes** (a non-destructive version of B, with an exportable attribute)
```
Group Input ─► Mesh to Volume (voxel 0.03, interior band 0.1)
            ─► Volume to Mesh (voxel 0.03, threshold 0.1, adaptivity 0)      ← unify and soften arrises
            ─► Set Position  Offset = Normal × (Noise(Position, 0.8).Fac − 0.5) × 0.004
            ─► Store Named Attribute "trowel" (Float, Point) = Voronoi Distance to Edge(Position, 3.2)
            ─► Set Shade Smooth ─► Group Output
```
In the shader, read the edge mask with an **Attribute** node (`trowel`) in place of the Voronoi node. Then the viewport, EEVEE, Cycles and any bake all agree on where the lap ridges are.

**Scanned textures.** For close-up hero shots you can layer a scanned plaster texture from ambientCG or Poly Haven on top. Use an Image Texture with **Box** projection (blend 0.2) on Object coordinates, and mix it into the bump at about 30%. Keep the procedural macro layer, because scans tile visibly at room scale.

## 6. Making it photoreal: Poly Haven assets

The geometry is blocking, and so are the proxies: blob trees, box furniture and procedural textures. Real photorealism comes from scanned assets. The script can fetch CC0 assets from [Poly Haven](https://polyhaven.com) by itself:

1. **Allow the domains.** `api.polyhaven.com` and `dl.polyhaven.org` must be reachable. In a Claude Code cloud environment, add them under the environment's network settings, then start a new session, because running sessions keep the policy they started with. On your own machine this works out of the box.
2. **Run the script** with `USE_POLYHAVEN = True`, which is the default. It caches everything under `~/.cache/verdio_polyhaven`, so only the first run downloads. The console prints which asset filled each role.
3. **What gets replaced.**

   | Role | Replaces |
   |---|---|
   | Textures (2k, box-projected at real-world size) | Oak floor (stained darker to the brand's dark oak), terracotta, brick, pantile, bluestone, thatch, deck, soil, shell gravel, sand |
   | Models (1k) | Potted plants indoors and on the pavilions; shrubs, trees and pines on the dunes; ferns around the pavilions; grass clumps on the lawn (scattered with Geometry Nodes) |
   | HDRI (4k) | The partly-cloudy pure sky, in place of the procedural fallback |

   The Rotband plaster stays procedural on purpose (see §5).
4. **Pin what you like.** Each role lists preferred asset IDs first (`PH_TEXTURES`, `PH_MODEL_ROLES`, `PH_HDRI` in the script). If an ID doesn't exist, the script falls back to the best keyword match on Poly Haven. After the first run, look at the renders and put the IDs you want at the front of each list.
5. **Align the sky.** A Poly Haven sky has its own sun, and so does the script's Sun lamp. Rotate `HDRI_ROTATION_DEG` until the HDRI's sun sits at `SUN_AZIMUTH_DEG`. Alternatively, keep the lamp and lower `HDRI_STRENGTH` to about 0.6 so the HDRI acts only as sky fill.

**Final render.** Set `QUALITY = "final"` and render on a GPU (Preferences → System → Cycles Render Devices). Then add the details that sell realism:
- Depth of field at f/4–f/5.6 on the 50 mm detail shots.
- Volume Scatter haze for the exteriors (§4).
- Hair Dynamics with a Wind force for the grass and reeds.

### The procedural stand-ins (offline)

- **Terrain.** A 145 × 145 m height field on a 1 m grid, so the terrace walls fall on grid lines.
  - The house terrace and the terraces below it are flat ground boxes. Each pavilion gets its own flat pad blended into the dunes.
  - The dune shader shifts from wet sand at the waterline, to dry sand, to grey-green dune crust inland.
- **Marram grass.** A hair system: 9,000 tussocks with 30 blades each. Density comes from a `marram` vertex group: none on the beach, the terraces, the pads or the paths.
- **Garden planting.**
  - The lawn and the meadow grass are hair.
  - Wildflowers and tulips are Geometry Nodes scatters of small proxies. The meadow flowers take random colours per instance; the tulip strips each take one colour.
  - The reeds in the pond are hair.
- **Shrubs, pines and oaks.** Linked duplicates of one proxy mesh each, planted densely around the sides and backs of the pavilions. The sea-facing front of each pavilion is left open.

## 7. What's deliberately not here yet

- **Vertical circulation.** A poshtel needs a stair and lift core to the rooms above. The upper floor and roof are placeholder massing only, there for the exterior silhouette.
- **Grill and oven services.** The hoods are massing only. An open charcoal grill and a wood-fired oven both need extract, make-up air and fire separation.
- **Structure.** There's no grid yet. The oak girder and joists are visual intent, not engineering; check the spans, since the coast band is 8.3 m deep.
- **Planting design.** The vegetation is generic. A landscape architect should specify local dune species, the pond's planting and filtration, and how the dune is stabilised around the boardwalks and pavilions.
- **Pavilion interiors.** Each pavilion is one room with a bed, plus its veranda. Bathrooms and services aren't designed.
