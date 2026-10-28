# Verdio: ground-floor blocking for Blender

This folder holds a parametric conceptual massing of the Verdio poshtel ground floor, plus a lighting, camera and plaster workflow guide. The design sits in the friction between salt, sweat and performance on one side and heavy, dark, traditional interiors on the other. It is not tropical minimalism.

| File | What it is |
|---|---|
| `verdio_ground_floor.py` | One script. It builds the 400 m² plate, walls, openings, the steel Kamer en suite, oak panelling, blocking props, materials (including a procedural Rotband plaster), sun, sky, light portals, practical lights, cameras and Cycles settings. |
| `previews/` | Low-sample Cycles renders (64 spp, CPU) straight out of the script, with no manual edits. |

The script was tested headless on Blender 4.2 LTS. API names that changed in 4.x (Principled inputs, displacement method) are handled. If you're on 5.x and the Nishita sky type has been renamed, the world falls back to a flat sky. Use an HDRI there anyway (see §3).

```
Scripting workspace → Open → verdio_ground_floor.py → Run Script
# or
blender -b -P verdio_ground_floor.py
```

Re-running rebuilds the `VERDIO` collection in place. Edit the parameters at the top of the script, such as wall centre-lines, en suite dimensions, sun bearing and site rotation, then run it again.

---

## 1. The plan

Plate: 25.0 × 16.0 m = 400 m² gross. Coast is south (−Y). Exterior walls are 350 mm, internal walls 200 mm masonry, and the clear height is 3.60 m, which is generous and 1930s.

```
    N  y=16.00
    +-------------------------------------------------+
    |  LIBRARY / COWORK      #  ENDURANCE      | WET  |
    |  dark oak, panelled    #  KICKR + BJJ    | CORE |
    |  80.6 m2               #  58.5 m2        |20.7  |
    +------------------+-----#-----------+-----+------+  y=8.75
    |  CULINARY CORE   |  LOUNGE         | MUDROOM    |
    |  grill + table   |  dark oak       | terracotta |
    |  75.1 m2         |  73.0 m2        | 50.2 m2    |
    +-------------------------------------------------+  y=0
    x=0               9.5   12.5        18.5  21.5   25
                  ~~~~~~~~~  COAST / SEA  ~~~~~~~~~
    #  = steel-and-glass Kamer en suite (x = 12.5)
```

The total net area is 358 m². The rest is walls and the 600 mm partition.

**Why this arrangement**

- **Wet-to-dry sequence.** Beach → Space Blue double door → mudroom (terracotta, recessed coir mat, linear drain, boot bench) → a 2.6 m cased opening lined in matte black steel → lounge (dark oak). The terracotta-to-oak change sits exactly on the wall centre-line, under a flush 25 mm black steel T-strip. There's no step and no ramp. Athletes can also go mudroom → wet core (showers) → endurance and never cross the oak.
- **North-facing rear band.** The endurance room and the library both face north. The climate-controlled room gets no solar gain, and screens in the cowork get no glare. The low coastal sun goes to the rooms that should glow: culinary, lounge and mudroom.
- **The culinary core** is a terracotta-clad masonry grill hearth with an open charcoal well and a plastered hood. A 5.4 × 1.2 m oak table with a 100 mm slab top and trestles runs parallel to it, with benches. The back kitchen sits on the west wall with its service door. Two steel-framed glazed doors open onto a south terrace.
- **The lounge** is an English country-house room: chimney breast, oak mantel and terracotta hearth on the north wall, oak dado panelling (1.10 m), deep oak window seats in the south windows, and two oxblood chesterfields on a wool rug.
- **The library** has oak panelling to 2.40 m with skirting, mid rail, cap rail and stiles. A full-wall bookcase runs along the south wall, an oak refectory cowork table runs on the camera axis toward the en suite, and two reading chairs face the glass.

## 2. The structural anchor: the steel Kamer en suite

The classic 1930s Dutch en suite partition is a deep wall with built-in cabinets either side of a wide pair of sliding doors, and a glazed *bovenlicht* above a timber rail (the *kalf*). The script keeps that anatomy and swaps the timber for matte black steel:

```
 PLAN (600 mm deep)          library | vitrine | pocket | vitrine | endurance
                                     |  200    |  200   |  200    |
                                                ^      ^
                                    skin A track   skin B track  (100 mm acoustic cavity)

 ELEVATION   plaster pier | vitrine 1.3 | opening 3.2 m: 2 skins × 2 pocket leaves | vitrine 1.3 | pier
             steel kalf at 2.75 m · double-glazed bovenlicht to 3.30 m · plaster bulkhead to 3.60 m
```

- **Two independent glass skins.** Each skin has two Crittall-style leaves on 2 × 5 divided lights, with a 16 mm laminated pane, a 50 mm steel frame and a 150 mm kick rail. The skins sit 100 mm apart. That double skin is what keeps the acoustic and climate isolation honest while the sightlines stay open.
- **Pockets.** The leaves slide into a 200 mm cavity behind the oak pocket walls of the vitrines. When closed they lap 30 mm into the steel jambs.
- **Vitrines.** Each side has oak drawer bases to 850 mm and steel-framed glazed display doors with oak shelves above. The library faces books and objects; the endurance room faces trophies and kit.
- **Animate it.** Select `EnSuite_CONTROL`, go to Object Properties → Custom Properties, and drag `open` from 0 to 1. All four leaves are driven from that one value, each travelling 1.6 m.

Real-world notes to carry into the next design stage:
- Specify acoustic laminated glass on both skins and drop seals at the threshold plate. Seal the endurance skin tighter than the library skin, so warm, humid gym air can't get into the cavity and condense.
- Put the endurance room on its own HVAC zone at slight negative pressure relative to the library, so any air that leaks goes from the library to the gym and not the other way.

## 3. Lighting and camera

### HDRI choice

You want sky fill that you can rotate, plus a separately controllable sun:

1. **Use a "pure sky" HDRI.** It should be partly cloudy, with the sun 10–25° above the horizon and no ground plate. Poly Haven publishes many in `_puresky` variants; filter by *Sky* and *Unclipped*. Partly cloudy beats clear blue because the cloud breaks the sky into soft, directional fill. That fill models plaster better than an evenly blue sky, which flattens it.
2. **Keep the sun out of the HDRI.** Either pick an HDRI whose sun is clipped or soft, or use one that is fully unclipped but turn it down. Then let the **Sun lamp** carry the direct light. The script does this: Sun at bearing 235° (south-west), 16° elevation, 4.5 W/m², 0.6° angular size, warm 1.0/0.86/0.72. You get crisp, rotatable, art-directable shadows. An HDRI sun can't be moved without moving the whole sky.
3. **Align them.** Set `HDRI_PATH`, then rotate `HDRI_ROTATION_DEG` until the HDRI's bright quadrant matches `SUN_AZIMUTH_DEG`. Coastal skies are blue-heavy, which gives a cool fill against warm sun. That warm/cool split makes dark oak look rich and not muddy.
4. **Real site.** If Verdio sits on the Dutch North Sea coast, the sea is to the west. Set `SITE_ROTATION_DEG = -90` and keep the sun at a western bearing (250–270°) for golden hour over the water.

### Why low, raking sun

- **Dark oak** has an albedo of about 0.05–0.10, so it reads through **sheen and grain**, not brightness. Low sun across the floor gives long specular streaks along the boards and warm pools of light. A high sun produces small, dull patches.
- **Rotband plaster** reads only at **grazing light**, roughly 5–20° to the wall surface. Frame shots so the sun or window light skims the side walls, which run perpendicular to the glazing. Don't face the lit wall head-on, where the texture flattens, and don't face straight into the windows, where everything turns to silhouette.

### Settings the script applies (and why)

| Setting | Value | Reason |
|---|---|---|
| Engine | Cycles | Interior bounce light in dark rooms, and true displacement. |
| Light portals | An area light flagged as a portal in every exterior window | Much less noise from sky light entering small openings. |
| Glass | Mix by *Is Shadow Ray* with Transparent BSDF | Sunlight passes through window glass instead of casting black shadows. |
| Caustics | Off, with *Filter Glossy* at 1.0 | Interiors don't need them, and they cause fireflies. |
| Bounces | Diffuse 6, transmission 12 | Dark oak rooms depend on bounce light, and the en suite stacks four or more layers of glass. |
| Clamp indirect | 10 | Kills fireflies from the polished concrete. |
| View transform | AgX, Medium High Contrast | Holds the sun patches without crushing the oak. |
| Practicals | 2700 K pendants, desk lamps, fire and embers; 4000 K linear lights in the gym | Warm heavy rooms against a cool performance room, seen through the glass. |

Exposure: interiors usually need about +1 to +2 EV relative to the outside. The script sets `EXPOSURE = 1.5` (Color Management → Exposure). Raise that, not the sky strength, because raising sky strength flattens the contrast between sun and fill.

Albedo discipline: keep plaster around sRGB 190–220 (linear about 0.5–0.7), not white, and oak at no less than about sRGB 25. Values darker than that lose grain under any tonemapper.

### Cameras (all built by the script)

| Camera | Shot |
|---|---|
| `CAM_01_Library_EnSuite` | The hero shot. Looks down the refectory table into the steel en suite, with the trainers lit cool behind the glass. 24 mm. |
| `CAM_02_Mudroom_Threshold` | Terracotta in the foreground, the steel portal, then oak and the lounge beyond. 21 mm. |
| `CAM_03_Culinary_Hearth` | From the terrace doors toward the grill hearth and the table. 24 mm. |
| `CAM_04_Endurance_to_Library` | The reverse view: from the mat through two glass skins into the warm library. |
| `CAM_00_Plan_Ortho` | A top-down check. Hide `Ceiling_Slab` from render first; it is already hidden in the viewport. |

Camera rules for this brief:
- **Two-point perspective.** Keep the camera dead level and use **Shift Y** to reframe, never tilt. Heavy panelled rooms look wrong when their verticals converge.
- **Lens and height.** Use 21–28 mm on a 36 mm sensor for rooms, and 35–50 mm for material vignettes such as the steel jamb against the plaster pier, or the T-strip on the floor seam. Shoot from 1.2–1.5 m.
- **Depth of field.** Barely any; at most f/8 equivalent. For detail shots, use f/2.8 focused on the material.
- **Atmosphere (optional).** Add a very low-density Volume Scatter cube, density 0.002–0.004, **in the endurance room only**. Sun shafts through its windows give a hint of humid air. Keep the library air dry and clear; that difference is the story.

## 4. Procedural Knauf Rotband plaster

Rotband is a hand-floated gypsum base coat. Left raw, it is a warm pinkish putty with cloudy drying marks. What makes it "tactile" is three overlapping scales of relief:

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
- **Burnished laps.** Where trowel strokes overlap, the plaster is compressed and slightly glossier. That is why the ridge mask also drives roughness and lightens the colour a little.
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
4. Add **Shade Auto Smooth** (Smooth by Angle, 30°) and keep the shader's bump nodes for the grain.

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

## 5. What's deliberately not here yet

- **Vertical circulation.** A poshtel needs a stair and lift core to the rooms above. The obvious slot is the lounge's west half, or the mudroom/lounge junction, so arriving guests go up without crossing the culinary core.
- **Charcoal grill services.** The hood is massing only. An open charcoal grill needs a commercial extract, make-up air and fire separation. Size the hood early, because it will shape the culinary core's ceiling.
- **Structure.** There's no grid yet. The 600 mm en suite and the 200 mm internal walls could carry the loads, but check the spans: the culinary core and the library are about 9 m deep.
- **Ceiling detail.** English country-house cornices and exposed oak beams in the culinary core would be the next pass. The ceiling is a flat plastered slab for now.
