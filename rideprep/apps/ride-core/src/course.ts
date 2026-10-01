import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { Fetcher, httpFetcher, loadCourse } from "@rideprep/course-format";

/** Load a course package from a directory or an http(s) base URL (the API's /courses/{id}/files). */
export function fetcherFor(src: string): Fetcher {
  if (/^https?:\/\//.test(src)) return httpFetcher(src);
  return async (p) => {
    const b = await readFile(join(src, p));
    return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
  };
}

export const loadPackage = (src: string) => loadCourse(fetcherFor(src));
