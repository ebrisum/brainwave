import { RideRecord, RideSummary } from "@rideprep/metrics";

/** Rides stored locally in IndexedDB (spec §12). */
export interface StoredRide {
  id: string;
  courseId: string;
  courseName: string;
  startedAt: number;
  records: RideRecord[];
  summary: RideSummary;
  plan?: { segmentM: number; watts: number[] };
}

const DB = "rideprep";
const STORE = "rides";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => {
      const s = req.result.createObjectStore(STORE, { keyPath: "id" });
      s.createIndex("courseId", "courseId");
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveRide(r: StoredRide): Promise<void> {
  const db = await open();
  await new Promise<void>((res, rej) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(r);
    tx.oncomplete = () => res();
    tx.onerror = () => rej(tx.error);
  });
}

export async function ridesForCourse(courseId: string): Promise<StoredRide[]> {
  try {
    const db = await open();
    return await new Promise((res, rej) => {
      const req = db.transaction(STORE).objectStore(STORE).index("courseId").getAll(courseId);
      req.onsuccess = () => res((req.result as StoredRide[]).sort((a, b) => b.startedAt - a.startedAt));
      req.onerror = () => rej(req.error);
    });
  } catch {
    return [];
  }
}
