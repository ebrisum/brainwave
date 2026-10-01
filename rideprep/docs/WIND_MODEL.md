# Wind model

Wind at the rider = weather-model 10 m wind × upwind roughness × obstacle shelter × topography × street channelling ×
gusts. All direction-dependent factors are precomputed by the `wind` stage for every 10 m route sample and 16
FROM-direction bins (22.5°), stored in `wind.bin` as `uint8(value·100)`, layer-major
(`offset = (layer·count + sample)·16 + bin`). At runtime (`packages/physics/src/wind`) factors are interpolated
linearly between the two nearest bins and samples.

Directions are **meteorological FROM directions** throughout. With compass heading h:
`w_head = U·cos(dir − h)` (positive = headwind), `w_cross = U·sin(dir − h)` (positive = from the right).

## 1. Weather (`weather` stage, `WeatherField`)
Open-Meteo forecast / ERA5 archive / 15-year climatology (month-day ±15 days, ±2 h) / manual; sampled every 5 km and
hourly; interpolated in s and in time (direction as a vector) using the rider's simulated clock. Failures fall back
to climatology, then to generic mid-latitude defaults, each with a warning.

## 2. Upwind roughness `fRough(dir)`
Reference: the 10 m wind is open grassland (z0_ref = 0.03 m). Up to a 60 m blending height, back down with the
upwind effective roughness:
```
U60 = U10·ln(60/z0_ref)/ln(10/z0_ref)
z0_eff = exp(Σ wᵢ ln z0ᵢ / Σ wᵢ), wᵢ = exp(−dᵢ/500 m), WorldCover pixels in the sector ±30°, 300–2000 m upwind
z0_eff ≤ 0.30
fRough = (U60/U10)·ln(z_r/z0_eff)/ln(60/z0_eff),  z_r = 1.2 m
```
Implementation samples 7 rays (−30…+30° step 10°) × 18 distances (300…2000 m step 100 m). z0 table: water 0.0002,
snow 0.001, bare 0.005, moss 0.01, grass 0.03, wetland 0.05, cropland 0.05 (Jan)–0.15 (Jul, cosine by month),
shrub 0.20, built-up 0.70, trees/mangroves 1.0. Vectors (§16.3): U10 = 10 → 6.35 (z0 0.03), 9.0 (0.0002), 3.4 (0.30).

## 3. Obstacle shelter `shelter(dir)`
Obstacles (buildings with heights, forests, tree rows, single trees, hedges) are rasterised at 4 m (height, optical
porosity). Five rays across ±15° of the bin centre are marched in 4 m steps up to `min(25·H_max, 400 m)`. For each cell
hit at distance x with height H and porosity φ:
```
u_min = 0.15 + 0.85φ;  L = (12 + 20φ)·H
f = 0.7 + 0.1·x/H          (x/H < 3)
  = 1 − (x − 3H)/(L − 3H)   (3H ≤ x < L)
  = 0                       (x ≥ L)
R = 1 − (1 − u_min)·clamp(f, 0, 1)
```
**Deviation:** shelter = mean over the 5 rays of (min R along the ray). The spec's "min over all hits" let one grazing
ray hitting a building corner shelter a street from every direction; averaging the fan keeps "strongest shelter
along a line of sight" while weighting how much of the upwind sector is blocked.
Porosity: buildings/walls 0.0; conifers and forest edges 0.3; deciduous 0.3 leaf-on / 0.6 leaf-off; mixed 0.3/0.45;
hedge 0.4; single tree 0.5 (0.7 leaf-off). Leaf season: leaf-on ~15 Apr–1 Nov at 52°N, shifted ~1 week per 2° of
latitude, mirrored in the southern hemisphere, always on below 23°. The event date drives the season, so the same lane
is windier in winter.

## 4. Topography and channelling
- `topo(dir)` (bounded heuristic, [0.7, 1.2]): TPI = z − mean(z on a 500 m ring, 16 points), normalised by 30 m.
  Crests: `1 + 0.12·TPI_n + 0.08·clamp(windward slope/0.1)`. Valleys: aligned within ±30° of the wind
  `1 + 0.10·|TPI_n|`, otherwise down to `1 − 0.30·|TPI_n|` when perpendicular. Valley axis = direction of the lowest
  ring point.
- `channel(dir)` = 1.10 when buildings stand on both sides within 6–25 m of the centreline and the wind is within
  ±30° of the street axis, else 1.0.

## 5. Runtime
```
U_rider(s,t) = U10(s,t)·fRough·shelter·topo·channel·gust(t)
dir_rider    = dir10(s,t) + δ(t)
```
Gusts: Ornstein-Uhlenbeck multiplier, mean 1, τ = 6 s, σ = 1/ln(z_r/z0) clamped to [0.08, 0.35] (z0 recovered from the
fRough layer), capped so U10·gust ≤ the gust value. Direction wobble δ: OU, σ = 8°, τ = 10 s. Seeded per ride
(mulberry32 + Box-Muller), exact discretisation → reproducible rides.

## Sanity check (§16.5, `packages/physics/test/wind.test.ts`)
U10 = 8 m/s from 270°, heading north: dike with open water ≈ 7.2 m/s > open polder ≈ 5.1 > tree row in January >
same row in summer > street with continuous buildings (lowest). Pipeline check: polder fixture median exposure from
the west exceeds the urban fixture's, with exposed stretches > 0.6·U10 and tree-row shelter < 0.8.
