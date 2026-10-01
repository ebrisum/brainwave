import { Fetcher, httpFetcher, Manifest } from "@rideprep/course-format";

export const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

export interface CourseListItem {
  courseId: string; name: string; tier: string; eventStart: string | null; climbs: number;
  stats: { distanceM: number; ascentM: number; maxGradePct: number; laps: number };
}

export async function listCourses(): Promise<CourseListItem[]> {
  const r = await fetch(`${API}/courses`);
  if (!r.ok) throw new Error(`API ${r.status}`);
  return r.json();
}

export interface UploadOptions { name?: string; eventStart?: string; tier: "quick" | "full"; weather: string }

export async function uploadCourse(file: File, o: UploadOptions): Promise<{ buildId: string; courseId: string | null; status: string }> {
  const fd = new FormData();
  fd.append("file", file);
  if (o.name) fd.append("name", o.name);
  if (o.eventStart) fd.append("event_start", o.eventStart);
  fd.append("tier", o.tier);
  fd.append("weather", o.weather);
  const r = await fetch(`${API}/courses`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export interface BuildEvent { event: string; stage?: string; status?: string; duration_s?: number; fraction?: number; message?: string; courseId?: string; t?: number }

export function buildEvents(buildId: string, onEvent: (e: BuildEvent) => void): () => void {
  const es = new EventSource(`${API}/courses/${buildId}/events`);
  const kinds = ["queued", "stage_start", "stage_progress", "stage_end", "warning", "error", "done", "course_id", "closed", "info"];
  for (const k of kinds) es.addEventListener(k, (m) => onEvent(JSON.parse((m as MessageEvent).data)));
  es.addEventListener("closed", () => es.close());
  return () => es.close();
}

export const courseFetcher = (courseId: string): Fetcher => httpFetcher(`${API}/courses/${courseId}/files`);

export async function refreshWeather(courseId: string, body: Record<string, unknown>) {
  const r = await fetch(`${API}/courses/${courseId}/weather`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export type { Manifest };
