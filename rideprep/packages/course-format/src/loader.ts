import { WeatherField, WeatherJson, ClimatologyJson } from "@rideprep/physics";
import { decodeInstances, decodeRoute, decodeWind } from "./decode";
import { Manifest, MaterialCatalogue, QuickBuilding, QuickRoad, QuickWater } from "./types";

export type Fetcher = (path: string) => Promise<ArrayBuffer>;

/** Fetcher for an HTTP base URL (API `/courses/{id}/files/` or a static directory). */
export const httpFetcher = (base: string): Fetcher => async (path) => {
  const r = await fetch(`${base.replace(/\/$/, "")}/${path}`);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.arrayBuffer();
};

const json = async <T>(f: Fetcher, p: string): Promise<T> => JSON.parse(new TextDecoder().decode(await f(p))) as T;

export async function loadCourse(f: Fetcher) {
  const manifest = await json<Manifest>(f, "manifest.json");
  if (manifest.schemaVersion !== "1.0.0") throw new Error(`unsupported schema ${manifest.schemaVersion}`);
  const [route, wind, weather, climatology, instances, materials] = await Promise.all([
    f(manifest.route.file).then((b) => decodeRoute(b, manifest)),
    f(manifest.wind.file).then((b) => decodeWind(b, manifest)),
    json<WeatherJson>(f, manifest.weather.file),
    json<ClimatologyJson & { scenarios?: unknown[] }>(f, manifest.climatology.file),
    f(manifest.instances.file).then((b) => decodeInstances(b, manifest)),
    json<MaterialCatalogue>(f, manifest.materialCatalogue),
  ]);
  // Prefer the web export's meshopt-compressed chunks when present
  let chunks = manifest.chunks;
  if (manifest.exports.web) {
    try {
      chunks = (await json<{ chunks: Manifest["chunks"] }>(f, manifest.exports.web)).chunks;
    } catch { /* fall back to the raw chunks */ }
  }
  return { manifest, route, wind, weather: new WeatherField(weather), weatherJson: weather, climatology, instances, materials, chunks };
}

export async function loadQuickGeometry(f: Fetcher, m: Manifest) {
  if (!m.quick) return { buildings: [], roads: [], water: [] };
  const [b, r, w] = await Promise.all([
    json<{ buildings: QuickBuilding[] }>(f, m.quick.buildings),
    json<{ roads: QuickRoad[] }>(f, m.quick.roads),
    json<{ water: QuickWater[] }>(f, m.quick.water),
  ]);
  return { buildings: b.buildings, roads: r.roads, water: w.water };
}

export type LoadedCourse = Awaited<ReturnType<typeof loadCourse>>;
