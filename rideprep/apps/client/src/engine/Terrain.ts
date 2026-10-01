import * as THREE from "three";
import { decodeTerrarium, Fetcher, Manifest, MaterialCatalogue, CourseProfile } from "@rideprep/course-format";
import { color, disposeObject, enu, gridIndex, hash01, loadImageData } from "./util";

interface TileState { mesh?: THREE.Mesh; loading: boolean; cx: number; cy: number; i: number; j: number }

/**
 * Quick-tier heightfield terrain: local tiles (3 km, 10 m vertex spacing) streamed around the rider, coloured by land cover,
 * plus a low-resolution far field. Heights near the road were already flattened by the pipeline.
 */
export class Terrain {
  group = new THREE.Group();
  private tiles = new Map<string, TileState>();
  private material: THREE.MeshStandardMaterial;
  private farMesh?: THREE.Mesh;
  private lcColors = new Map<number, THREE.Color>();
  stride: number;
  loadRadius = 4500;

  constructor(private m: Manifest, private fetch: Fetcher, private cat: MaterialCatalogue, quality: string,
              private route?: CourseProfile & { roadWidthM: Uint8Array }) {
    this.material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.97, metalness: 0 });
    this.stride = quality === "ultra" ? 1 : quality === "low" ? 3 : 2;
    for (const [cls, mid] of Object.entries(cat.landcoverToMaterial)) this.lcColors.set(Number(cls), color(cat, mid));
    const T = m.terrain.quickTier.tileSizeM;
    for (const t of m.terrain.quickTier.tiles) this.tiles.set(`${t.i}_${t.j}`, { loading: false, cx: (t.i + 0.5) * T, cy: (t.j + 0.5) * T, i: t.i, j: t.j });
  }

  async loadFar(): Promise<void> {
    const far = this.m.terrain.quickTier.far;
    const img = await loadImageData(await this.fetch(far.file));
    const z = decodeTerrarium(img.data);
    const step = Math.max(1, Math.ceil(Math.max(img.width, img.height) / 220));
    const cols = Math.ceil(img.width / step);
    const rows = Math.ceil(img.height / step);
    const pos = new Float32Array(cols * rows * 3);
    const col = new Float32Array(cols * rows * 3);
    const [minx, , , maxy] = far.bounds;
    const c0 = this.lcColors.get(30) ?? new THREE.Color(0.33, 0.5, 0.22);
    const ox = (far.bounds[0] + far.bounds[2]) / 2;
    const oy = (far.bounds[1] + far.bounds[3]) / 2;
    let k = 0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const px = Math.min(c * step, img.width - 1);
        const py = Math.min(r * step, img.height - 1);
        const x = minx + (px + 0.5) * far.resM - ox;
        const y = maxy - (py + 0.5) * far.resM - oy;
        const h = z[py * img.width + px] - 3;
        pos[k * 3] = x; pos[k * 3 + 1] = h; pos[k * 3 + 2] = -y;
        const v = 0.85 + 0.15 * hash01(x * 0.01, y * 0.01);
        col[k * 3] = c0.r * v; col[k * 3 + 1] = c0.g * v; col[k * 3 + 2] = c0.b * v;
        k++;
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    g.setIndex(gridIndex(cols, rows));
    g.computeVertexNormals();
    const mat = this.material.clone();
    mat.polygonOffset = true;
    mat.polygonOffsetFactor = 4;
    mat.polygonOffsetUnits = 4;
    this.farMesh = new THREE.Mesh(g, mat);
    this.farMesh.position.copy(enu(ox, oy, 0));
    this.farMesh.receiveShadow = false;
    this.group.add(this.farMesh);
  }

  /** Stream tiles around (x, y). */
  update(x: number, y: number) {
    for (const [key, t] of this.tiles) {
      const d = Math.hypot(t.cx - x, t.cy - y);
      if (d < this.loadRadius && !t.mesh && !t.loading) {
        t.loading = true;
        this.loadTile(t).catch((e) => console.warn("terrain tile", key, e)).finally(() => (t.loading = false));
      } else if (d > this.loadRadius + 2500 && t.mesh) {
        disposeObject(t.mesh);
        t.mesh = undefined;
      }
    }
  }

  private async loadTile(t: TileState) {
    const q = this.m.terrain.quickTier;
    const name = `${t.i}_${t.j}`;
    const [demBuf, lcBuf] = await Promise.all([this.fetch(q.demTiles.replace("{i}_{j}", name)), this.fetch(q.landcoverTiles.replace("{i}_{j}", name))]);
    const [dem, lc] = await Promise.all([loadImageData(demBuf), loadImageData(lcBuf)]);
    const z = decodeTerrarium(dem.data);
    const n = dem.width;
    const s = this.stride;
    const cols = Math.floor((n - 1) / s) + 1;
    const pos = new Float32Array(cols * cols * 3);
    const col = new Float32Array(cols * cols * 3);
    const T = q.tileSizeM;
    const sp = q.vertexSpacingM;
    let k = 0;
    for (let r = 0; r < cols; r++) {
      for (let c = 0; c < cols; c++) {
        const pr = Math.min(r * s, n - 1);
        const pc = Math.min(c * s, n - 1);
        const lx = pc * sp - T / 2;
        const ly = T / 2 - pr * sp;
        pos[k * 3] = lx; pos[k * 3 + 1] = z[pr * n + pc]; pos[k * 3 + 2] = -ly;
        const cls = lc.data[(pr * n + pc) * 4];
        const base = this.lcColors.get(cls) ?? this.lcColors.get(30)!;
        const v = 0.86 + 0.18 * hash01(t.cx + lx, t.cy + ly);
        col[k * 3] = base.r * v; col[k * 3 + 1] = base.g * v; col[k * 3 + 2] = base.b * v;
        k++;
      }
    }
    this.carveRoad(pos, cols, t, sp * s);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    g.setIndex(gridIndex(cols, cols));
    g.computeVertexNormals();
    g.computeBoundingSphere();
    const mesh = new THREE.Mesh(g, this.material);
    mesh.position.copy(enu(t.cx, t.cy, 0));
    mesh.receiveShadow = true;
    mesh.name = `terrain_${name}`;
    t.mesh = mesh;
    this.group.add(mesh);
  }

  /**
   * Keep terrain below the road at the *render* resolution: interpolation between coarse vertices otherwise lets slopes
   * poke through the road. Every vertex within (half width + one cell) of a route sample is lowered to road − 0.35 m.
   */
  private carveRoad(pos: Float32Array, cols: number, t: TileState, cell: number) {
    const r = this.route;
    if (!r) return;
    const T = this.m.terrain.quickTier.tileSizeM;
    const x0 = t.cx - T / 2, y1 = t.cy + T / 2;
    for (let i = 0; i < r.count; i += 1) {
      const rx = r.x[i], ry = r.y[i];
      if (rx < x0 - 30 || rx > x0 + T + 30 || ry < y1 - T - 30 || ry > y1 + 30) continue;
      const reach = r.roadWidthM[i] / 2 + cell;
      const c0 = Math.max(0, Math.floor((rx - reach - x0) / cell)), c1 = Math.min(cols - 1, Math.ceil((rx + reach - x0) / cell));
      const r0 = Math.max(0, Math.floor((y1 - ry - reach) / cell)), r1 = Math.min(cols - 1, Math.ceil((y1 - ry + reach) / cell));
      const zr = r.z[i] - 0.35;
      for (let row = r0; row <= r1; row++) {
        for (let c = c0; c <= c1; c++) {
          const vx = x0 + c * cell, vy = y1 - row * cell;
          if ((vx - rx) ** 2 + (vy - ry) ** 2 > reach * reach) continue;
          const k = (row * cols + c) * 3 + 1;
          if (pos[k] > zr) pos[k] = zr;
        }
      }
    }
  }

  /** Approximate ground height under a point from the route (used for camera clearance). */
  static routeHeightAt(c: CourseProfile, s: number) {
    const i = Math.min(Math.max(Math.round(s / c.spacingM), 0), c.count - 1);
    return c.z[i];
  }

  dispose() {
    disposeObject(this.group);
  }
}
