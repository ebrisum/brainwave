/** Course package manifest (schema/manifest.schema.json, schemaVersion 1.0.0). */

export interface ArrayLayout { name: string; type: "float32" | "uint8"; offset: number }

export interface Climb {
  id: number; sStart: number; sEnd: number; lengthM: number; avgGradePct: number; maxGradePct: number; gainM: number;
  difficulty: number; category: string;
}
export interface Corner {
  id: number; s: number; sStart: number; sEnd: number; radiusM: number; turnDeg: number; direction: "left" | "right";
  vMaxDryKmh: number; vMaxWetKmh: number; hairpin: boolean;
}
export interface Lap { index: number; sStart: number; sEnd: number }
export interface Poi { s: number; sEnd?: number; name: string; type: string; source: "gpx" | "osm" }
export interface SurfaceRun { sStart: number; sEnd: number; surface: string; crrMultiplier: number }

export interface Segments { climbs: Climb[]; corners: Corner[]; laps: Lap[]; pois: Poi[]; surfaceRuns: SurfaceRun[]; kmMarkers?: { s: number; label: string }[] }

export interface TerrainTile { i: number; j: number; minZ: number; maxZ: number }
export interface QuickTerrain {
  tiling: "local"; tileSizeM: number; vertexSpacingM: number; verticesPerSide: number; encoding: "terrarium";
  demTiles: string; landcoverTiles: string; tiles: TerrainTile[];
  far: { file: string; bounds: [number, number, number, number]; resM: number; width: number; height: number };
}

export interface ChunkRef {
  id: number; sStart: number; sEnd: number; status: "baked" | "pending" | "quick"; lod: string[];
  origin?: [number, number, number]; lodDistancesM?: number[];
}

export interface Manifest {
  schemaVersion: "1.0.0";
  courseId: string;
  name: string;
  pipelineVersion: string;
  tier: "quick" | "full";
  contentHash: string;
  eventStart: string | null;
  origin: { lat: number; lon: number; hOrthometric: number; verticalDatum: string; geoidUndulation: number | null; frame?: string };
  stats: { distanceM: number; ascentM: number; descentM: number; maxGradePct: number; laps: number; minElevationM?: number; maxElevationM?: number };
  route: { file: string; sampleSpacingM: number; count: number; arrays: ArrayLayout[] };
  wind: { file: string; sampleSpacingM: number; count: number; directionBins: number; layers: string[]; encoding: string; month?: number; leafOn?: boolean };
  segments: Segments & { file: string };
  terrain: { quickTier: QuickTerrain };
  chunks: ChunkRef[];
  farField: string | null;
  instances: { file: string; categories: string[]; count: number; recordBytes: number; fields: [string, string][] };
  quick?: { buildings: string; roads: string; water: string };
  materialCatalogue: string;
  exports: { web?: string; unreal?: string };
  weather: { file: string };
  climatology: { file: string };
  attribution: string[];
  warnings?: { stage: string; code: string; message: string }[];
}

export interface QuickBuilding { h: number; z: number; type: string; roof: string; near: boolean; ring: [number, number][] }
export interface QuickRoad { w: number; surface: string; pts: [number, number, number][] }
export interface QuickWater { z: number; ring: [number, number][] }

export interface MaterialCatalogue {
  version: number;
  materials: Record<string, { baseColor: [number, number, number]; roughness: number; metallic: number }>;
  surfaceCodeToMaterial: Record<string, string>;
  landcoverToMaterial: Record<string, string>;
}

export const INSTANCE_CATEGORIES = ["tree_deciduous", "tree_conifer", "tree_poplar", "hedge", "prop"] as const;
