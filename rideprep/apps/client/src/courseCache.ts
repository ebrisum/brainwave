import { LoadedCourse, loadCourse, loadQuickGeometry, QuickBuilding, QuickRoad, QuickWater } from "@rideprep/course-format";
import { courseFetcher } from "./api";
import type { RideSession } from "./ride/RideSession";
import type { AnalysisResult } from "./analysis/run";
import type { VideoSyncJson } from "./ride/videoSync";

/** Heavy objects live outside React/Zustand. */
export const cache: {
  courseId?: string;
  course?: LoadedCourse;
  quick?: { buildings: QuickBuilding[]; roads: QuickRoad[]; water: QuickWater[] };
  session?: RideSession;
  analysis?: AnalysisResult;
  /** Conditions chosen on the start screen (undefined = the package's race-day weather field). */
  rideWeather?: import("@rideprep/physics").WeatherJson;
  /** Video mode: synced footage chosen on the pairing screen (object URL of a local file). */
  video?: { sync: VideoSyncJson; url: string };
} = {};

export async function getCourse(courseId: string): Promise<LoadedCourse> {
  if (cache.courseId === courseId && cache.course) return cache.course;
  const f = courseFetcher(courseId);
  const course = await loadCourse(f);
  cache.courseId = courseId;
  cache.course = course;
  cache.quick = undefined;
  cache.analysis = undefined;
  return course;
}

/** Simulated start time: event date, else the weather file's start (pipeline default: tomorrow ~10:00 solar time). */
export function startEpochOf(c: LoadedCourse): number {
  const ev = c.manifest.eventStart ?? (c.weatherJson as { eventStart?: string }).eventStart;
  return ev ? Date.parse(ev) / 1000 : Date.now() / 1000;
}

export async function getQuick(courseId: string) {
  const c = await getCourse(courseId);
  if (!cache.quick) cache.quick = await loadQuickGeometry(courseFetcher(courseId), c.manifest);
  return cache.quick;
}
