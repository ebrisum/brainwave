import * as THREE from "three";
import { CourseProfile, MaterialCatalogue } from "@rideprep/course-format";
import { color, disposeObject, enu } from "./util";

/**
 * Quick-tier road: a cambered ribbon from route.bin per 500 m chunk (so baked chunks can replace it), coloured by surface,
 * with edge lines on wider roads; side roads from quick/roads.json.
 */
export class Road {
  group = new THREE.Group();
  chunks: THREE.Mesh[] = [];
  material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.85, metalness: 0 });

  constructor(private c: CourseProfile & { surfaceCode: Uint8Array; roadWidthM: Uint8Array }, private cat: MaterialCatalogue, chunkM: number) {
    const n = Math.ceil(c.s[c.count - 1] / chunkM);
    for (let k = 0; k < n; k++) this.chunks.push(this.buildChunk(k * chunkM, (k + 1) * chunkM));
    this.chunks.forEach((m) => this.group.add(m));
  }

  setWet(wet: boolean) {
    this.material.roughness = wet ? 0.25 : 0.85;
    this.material.color.setScalar(wet ? 0.75 : 1);
  }

  private buildChunk(s0: number, s1: number): THREE.Mesh {
    const c = this.c;
    const a = Math.max(0, Math.floor(s0 / c.spacingM) - 1);
    const b = Math.min(c.count - 1, Math.ceil(s1 / c.spacingM) + 1);
    const ox = c.x[a], oy = c.y[a], oz = c.z[a];
    // Across the road: edge line (white, ~12 cm), asphalt to the crown, mirrored. Camber: edges 2 % lower.
    const lanes = [-1, -0.97, -0.969, -0.5, 0, 0.5, 0.969, 0.97, 1];
    const m = b - a + 1;
    const pos: number[] = [];
    const col: number[] = [];
    const idx: number[] = [];
    const s2m = this.cat.surfaceCodeToMaterial;
    const mark = new THREE.Color(0.92, 0.92, 0.9);
    for (let i = a; i <= b; i++) {
      const hd = c.headingRad[i];
      const nx = Math.cos(hd), ny = -Math.sin(hd);
      const hw = c.roadWidthM[i] / 2;
      const base = color(this.cat, s2m[String(c.surfaceCode[i])] ?? "road_asphalt");
      for (const f of lanes) {
        const off = f * hw;
        const x = c.x[i] + nx * off - ox;
        const y = c.y[i] + ny * off - oy;
        const z = c.z[i] - oz + 0.04 - 0.02 * Math.abs(off);
        pos.push(x, z, -y);
        const edge = Math.abs(f) >= 0.97 && hw >= 2.5;
        const cc = edge ? mark : base;
        col.push(cc.r, cc.g, cc.b);
      }
    }
    const L = lanes.length;
    for (let r = 0; r < m - 1; r++) {
      for (let q = 0; q < L - 1; q++) {
        const p0 = r * L + q, p1 = p0 + 1, p2 = p0 + L, p3 = p2 + 1;
        idx.push(p0, p1, p2, p1, p3, p2);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    g.setIndex(idx);
    g.computeVertexNormals();
    // Make sure faces point up regardless of winding mistakes
    const nrm = g.getAttribute("normal");
    let flip = 0;
    for (let i = 0; i < nrm.count; i++) flip += nrm.getY(i);
    if (flip < 0) {
      for (let i = 0; i < idx.length; i += 3) [idx[i + 1], idx[i + 2]] = [idx[i + 2], idx[i + 1]];
      g.setIndex(idx);
      g.computeVertexNormals();
    }
    const mesh = new THREE.Mesh(g, this.material);
    mesh.position.copy(enu(ox, oy, oz));
    mesh.receiveShadow = true;
    return mesh;
  }

  addSideRoads(roads: { w: number; surface: string; pts: [number, number, number][] }[]) {
    const pos: number[] = [];
    const idx: number[] = [];
    if (!roads.length) return;
    const o = roads[0].pts[0];
    for (const r of roads) {
      const start = pos.length / 3;
      for (let i = 0; i < r.pts.length; i++) {
        const p = r.pts[i];
        const q = r.pts[Math.min(i + 1, r.pts.length - 1)];
        const pp = r.pts[Math.max(i - 1, 0)];
        let dx = q[0] - pp[0], dy = q[1] - pp[1];
        const l = Math.hypot(dx, dy) || 1;
        dx /= l; dy /= l;
        const hw = r.w / 2;
        for (const sgn of [-1, 1]) pos.push(p[0] + dy * hw * sgn - o[0], p[2] + 0.02 - o[2], -(p[1] - dx * hw * sgn - o[1]));
      }
      for (let i = 0; i < r.pts.length - 1; i++) {
        const a = start + i * 2;
        idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    g.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({ color: color(this.cat, "road_asphalt"), roughness: 0.9, side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(g, mat);
    mesh.position.copy(enu(o[0], o[1], o[2]));
    mesh.receiveShadow = true;
    this.group.add(mesh);
  }

  dispose() {
    disposeObject(this.group);
  }
}
