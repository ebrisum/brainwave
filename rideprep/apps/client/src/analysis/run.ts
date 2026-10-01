import { LoadedCourse } from "@rideprep/course-format";
import { ClimatologyJson, RiderProfile } from "@rideprep/physics";
import type { AnalysisRequest, AnalysisResult } from "./analysis.worker";

export type { AnalysisResult, ScenarioResult } from "./analysis.worker";

export function runAnalysis(c: LoadedCourse, rider: RiderProfile, opts: { powerW: number; startEpoch: number; optimizeFor: string; ifTarget: number }): Promise<AnalysisResult> {
  return new Promise((resolve, reject) => {
    const w = new Worker(new URL("./analysis.worker.ts", import.meta.url), { type: "module" });
    w.onmessage = (e) => { resolve(e.data as AnalysisResult); w.terminate(); };
    w.onerror = (e) => { reject(e); w.terminate(); };
    const r = c.route;
    const req: AnalysisRequest = {
      route: { spacingM: r.spacingM, count: r.count, s: r.s, x: r.x, y: r.y, z: r.z, gradePct: r.gradePct, headingRad: r.headingRad, radiusM: r.radiusM, crrMultiplier: r.crrMultiplier },
      wind: { data: c.wind.data, count: c.wind.count, spacingM: c.wind.spacingM, bins: c.wind.bins, layers: [...c.wind.layers] },
      weather: c.weatherJson, climatology: c.climatology as ClimatologyJson, rider, startEpoch: opts.startEpoch, powerW: opts.powerW,
      climbs: c.manifest.segments.climbs, laps: c.manifest.segments.laps, optimizeFor: opts.optimizeFor, ifTarget: opts.ifTarget,
    };
    w.postMessage(req);
  });
}
