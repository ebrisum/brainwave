import { Quality } from "../store";

export interface QualityPreset { pixelRatio: number; shadowMap: number; antialias: boolean; viewDistance: number }

export function preset(q: Quality): QualityPreset {
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  switch (q) {
    case "low": return { pixelRatio: Math.min(dpr, 1) * 0.75, shadowMap: 0, antialias: false, viewDistance: 6000 };
    case "medium": return { pixelRatio: Math.min(dpr, 1), shadowMap: 1024, antialias: true, viewDistance: 9000 };
    case "ultra": return { pixelRatio: Math.min(dpr, 2), shadowMap: 4096, antialias: true, viewDistance: 20000 };
    default: return { pixelRatio: Math.min(dpr, 1.5), shadowMap: 2048, antialias: true, viewDistance: 14000 };
  }
}

/** First-run guess from the GPU string: integrated → low/medium, discrete/Apple silicon → high. */
export function detectQuality(): Quality {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl2");
    if (!gl) return "low";
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    const r = (ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)) as string;
    if (/swiftshader|llvmpipe|software/i.test(r)) return "low";
    if (/intel|mali|adreno [1-6]|powervr/i.test(r)) return /iris xe|arc/i.test(r) ? "medium" : "low";
    if (/apple m[2-9]|rtx|radeon rx [6-9]|rx 7/i.test(r)) return "high";
    return "medium";
  } catch {
    return "medium";
  }
}
