import { LoadedCourse, loadCourse, loadQuickGeometry, QuickBuilding, QuickRoad, QuickWater } from "@rideprep/course-format";
import { courseFetcher } from "./api";
import type { RideSession } from "./ride/RideSession";
import type { AnalysisResult } from "./analysis/run";

/** Heavy objects live outside React/Zustand. */
export const cache: {
  courseId?: string;
  course?: LoadedCourse;
  quick?: { buildings: QuickBuilding[]; roads: QuickRoad[]; water: QuickWater[] };
  session?: RideSession;
  analysis?: AnalysisResult;
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

export async function getQuick(courseId: string) {
  const c = await getCourse(courseId);
  if (!cache.quick) cache.quick = await loadQuickGeometry(courseFetcher(courseId), c.manifest);
  return cache.quick;
}
