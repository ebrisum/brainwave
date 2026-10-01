import * as THREE from "three";
import { MaterialCatalogue } from "@rideprep/course-format";

/** ENU (x east, y north, z up) → three.js (x, y up, −z north). Same as glTF chunks. */
export const enu = (x: number, y: number, z: number, out = new THREE.Vector3()) => out.set(x, z, -y);

export function color(cat: MaterialCatalogue | undefined, id: string, fallback = "#808080"): THREE.Color {
  const m = cat?.materials[id];
  return m ? new THREE.Color().setRGB(m.baseColor[0], m.baseColor[1], m.baseColor[2], THREE.SRGBColorSpace) : new THREE.Color(fallback);
}

export async function loadImageData(buf: ArrayBuffer): Promise<{ data: Uint8ClampedArray; width: number; height: number }> {
  const bmp = await createImageBitmap(new Blob([buf], { type: "image/png" }), { colorSpaceConversion: "none", premultiplyAlpha: "none" });
  const c = typeof OffscreenCanvas !== "undefined" ? new OffscreenCanvas(bmp.width, bmp.height) : Object.assign(document.createElement("canvas"), { width: bmp.width, height: bmp.height });
  const ctx = (c as OffscreenCanvas).getContext("2d", { willReadFrequently: true }) as OffscreenCanvasRenderingContext2D;
  ctx.drawImage(bmp, 0, 0);
  const img = ctx.getImageData(0, 0, bmp.width, bmp.height);
  bmp.close();
  return { data: img.data, width: img.width, height: img.height };
}

/** Grid index buffer for an n×m vertex grid (two CCW-from-above triangles per cell in three.js space). */
export function gridIndex(cols: number, rows: number): THREE.BufferAttribute {
  const idx = new Uint32Array((cols - 1) * (rows - 1) * 6);
  let k = 0;
  for (let r = 0; r < rows - 1; r++) {
    for (let c = 0; c < cols - 1; c++) {
      const a = r * cols + c;
      const b = a + 1;
      const d = a + cols;
      const e = d + 1;
      idx[k++] = a; idx[k++] = d; idx[k++] = b;
      idx[k++] = b; idx[k++] = d; idx[k++] = e;
    }
  }
  return new THREE.BufferAttribute(idx, 1);
}

export function disposeObject(o: THREE.Object3D) {
  o.traverse((c) => {
    const m = c as THREE.Mesh;
    m.geometry?.dispose?.();
    const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
    mats.forEach((mm) => mm.dispose());
  });
  o.removeFromParent();
}

/** Deterministic hash noise in 0..1 for vertex colour variation. */
export const hash01 = (x: number, y: number) => {
  const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return s - Math.floor(s);
};
