# Sources

External facts this build relies on, where they were checked, and what still needs checking on a networked machine.

## Verified during the build
| Fact | Source |
|---|---|
| FTMS wind resistance coefficient (kg/m) = frontal area × drag coefficient × air density | US patent text on FTMS simulation parameters (search: "Set Indoor Bike Simulation Parameters" wind resistance coefficient) |
| Open-Meteo: free API non-commercial only, data CC BY 4.0; archive endpoint `archive-api.open-meteo.com/v1/archive` | https://open-meteo.com/en/terms |
| Unreal Engine 5.8 is the current release (UE6 announced for 2027) | https://www.unrealengine.com/news/state-of-unreal-2026-top-news-from-the-show |
| glTFRuntime: MIT licence, UE4.25+/UE5 | https://github.com/rdeioris/glTFRuntime |
| Blender 5.2 LTS (July 2026, supported to July 2028) | https://www.blender.org/releases/5-2/ |
| Garmin FIT JavaScript SDK: npm `@garmin/fitsdk` (21.217.0), `Encoder`, `addDeveloperField` | package README in node_modules; https://developer.garmin.com/fit |
| Copernicus DEM GLO-30 COGs on AWS: `copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_<N..>_00_<E...>_00_DEM/...tif` | fetched live during the build |
| ESA WorldCover 2021 v200 COGs: `esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_<N..E...>_Map.tif` | fetched live during the build |
| `gltfpack` (meshoptimizer) is published on npm (1.3.0, WASM build) | npm registry; used in the build |
| Bluetooth SIG UUIDs (FTMS 0x1826, CPS 0x1818, HRS 0x180D, CSC 0x1816, UDS 0x181C; chars 0x2AD2, 0x2AD9, 0x2A63, 0x2A37, 0x2A5B, …) and field layouts | Bluetooth SIG GATT specifications (FTMS 1.0, CPS 1.1, HRS 1.0, CSCS 1.0); encoded in `packages/ble/src` and covered by spec §16.4 vectors |
| Package versions (TypeScript 7.0.2, Vite 8.3.2, React 19.3, three 0.186.1, numpy 2.4, FastAPI 0.142, …) | npm / PyPI registries at build time; pinned in lockfiles |

| Map Tiles API: no caching/offline, logo + attribution required; Cesium for Unreal shows attributions by default | https://developers.google.com/maps/documentation/tile/policies, https://mapsplatform.google.com/resources/blog/commonly-asked-questions-about-our-recently-launched-photorealistic-3d-tiles/ |
| 3d-tiles-renderer 0.5.3: `GoogleCloudAuthPlugin` (root `tile.googleapis.com/v1/3dtiles/root.json`), `GLTFExtensionsPlugin` (Draco), raycasting | package source in node_modules |

## To verify on a networked machine (could not be reached from the build environment)
- Valhalla `trace_attributes` attribute names and `edge.surface` categories (implemented from the Valhalla API docs as remembered: `edge.way_id`, `edge.surface`, `edge.road_class`, `edge.bridge`, `edge.tunnel`, `edge.names`, `edge.lane_count`, `edge.cycle_lane`, `edge.use`, `matched.edge_index`, `matched.type`): https://valhalla.github.io/valhalla/api/map-matching/api-reference/
- Valhalla Docker image name/tag (`ghcr.io/valhalla/valhalla-scripted`): https://github.com/valhalla/valhalla/tree/master/docker
- Open-Meteo hourly variable names (`wind_speed_10m, wind_direction_10m, wind_gusts_10m, temperature_2m, relative_humidity_2m, pressure_msl, precipitation, cloud_cover, visibility`) and `wind_speed_unit=ms`: https://open-meteo.com/en/docs
- Tacx FE-C over BLE service UUID `6E40FEC1-B5A3-F393-E0A9-E50E24DCCA9E` (fallback, not implemented beyond the UUID).
- Google Map Tiles API (Photorealistic 3D Tiles) current policies before enabling Photoreal mode: https://developers.google.com/maps/documentation/tile/policies
- Unreal Landscape recommended sizes (505/1009/2017…): https://dev.epicgames.com/documentation/en-us/unreal-engine/landscape-technical-guide-in-unreal-engine
- Live Google tiles end to end with a real key (the path was verified with the local stand-in tileset only); Mapillary Graph API `images` fields (`thumb_1024_url`, `compass_angle`).
- Cesium for Unreal: `ACesium3DTileset::SetUrl/SetTilesetSource/SetCreatePhysicsMeshes`, and that the georeference actor transform is respected (used for re-anchoring).
- glTFRuntime `TransformBaseType` mapping for Y-up glTF on UE 5.8; Cesium for Unreal `SetOriginLongitudeLatitudeHeight`.
- KTX-Software release asset name for the pinned version (worker Dockerfile).
- Licences of canopy-height datasets (Meta/WRI 1 m, ETH 10 m) and Overture/3D BAG themes before adding those providers.
- Overture Maps release `2026-09-23.0` (themes transportation/buildings/base/places), schema as read from the Parquet footers: https://docs.overturemaps.org/ ; bucket `overturemaps-us-west-2`.
- IRONMAN 70.3 Italy Emilia-Romagna bike course description (one 90 km loop: Cervia promenade, Saline di Cervia, Forlimpopoli, Bertinoro): https://www.turismo.comunecervia.it/en/events/events-and-initiatives/sports-and-games/ironman-70-3-italy-emilia-romagna/ , https://www.discovercervia.com/en/events/2026/settembre/ironman-70-3-italy-emilia-romagna
- HMM map matching: Newson & Krumm, "Hidden Markov Map Matching Through Noise and Sparseness" (ACM SIGSPATIAL 2009).
- Italian road furniture shapes/colours: Codice della Strada, Regolamento di esecuzione (DPR 495/1992), figures II.
