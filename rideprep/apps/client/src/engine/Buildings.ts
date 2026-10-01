import * as THREE from "three";
import { QuickBuilding, MaterialCatalogue, CourseProfile } from "@rideprep/course-format";
import { color, disposeObject, enu, hash01 } from "./util";

const FACADE: Record<string, string> = {
  house: "facade_brick", detached: "facade_brick", terrace: "facade_brick", church: "facade_brick", barn: "facade_barn", farm_auxiliary: "facade_barn",
  shed: "facade_barn", apartments: "facade_plaster", commercial: "facade_plaster",
};

/**
 * Quick-tier buildings: footprints extruded to height with flat or gabled roofs, merged into one mesh per cell.
 * Near-route buildings are also grouped per 500 m chunk so a baked chunk can replace them.
 */
export class Buildings {
  group = new THREE.Group();
  byChunk = new Map<number, THREE.Mesh>();
  private material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.85 });

  constructor(list: QuickBuilding[], private cat: MaterialCatalogue, route: CourseProfile, chunkM: number) {
    const cells = new Map<string, QuickBuilding[]>();
    const nearByChunk = new Map<number, QuickBuilding[]>();
    for (const b of list) {
      const cx = b.ring.reduce((a, p) => a + p[0], 0) / b.ring.length;
      const cy = b.ring.reduce((a, p) => a + p[1], 0) / b.ring.length;
      if (b.near) {
        const k = Math.floor(nearestS(route, cx, cy) / chunkM);
        (nearByChunk.get(k) ?? nearByChunk.set(k, []).get(k)!).push(b);
      } else {
        const key = `${Math.floor(cx / 1500)}_${Math.floor(cy / 1500)}`;
        (cells.get(key) ?? cells.set(key, []).get(key)!).push(b);
      }
    }
    for (const bs of cells.values()) this.group.add(this.build(bs));
    for (const [k, bs] of nearByChunk) {
      const m = this.build(bs);
      this.byChunk.set(k, m);
      this.group.add(m);
    }
  }

  private build(bs: QuickBuilding[]): THREE.Mesh {
    const o = bs[0].ring[0];
    const oz = bs[0].z;
    const pos: number[] = [];
    const col: number[] = [];
    const push = (x: number, y: number, z: number, c: THREE.Color, shade: number) => {
      pos.push(x - o[0], z - oz, -(y - o[1]));
      col.push(c.r * shade, c.g * shade, c.b * shade);
    };
    for (const b of bs) {
      let ring = b.ring;
      if (signedArea(ring) < 0) ring = [...ring].reverse();
      const fac = color(this.cat, FACADE[b.type] ?? "facade_plaster");
      const v = 0.9 + 0.2 * hash01(ring[0][0], ring[0][1]);
      fac.multiplyScalar(v);
      const gable = (b.roof === "gabled" || b.roof === "hipped") && ring.length === 4;
      let eave = b.h;
      let roofH = 0;
      if (gable) {
        const e0 = Math.hypot(ring[1][0] - ring[0][0], ring[1][1] - ring[0][1]);
        const e1 = Math.hypot(ring[2][0] - ring[1][0], ring[2][1] - ring[1][1]);
        if (e0 < e1) ring = [ring[1], ring[2], ring[3], ring[0]];
        roofH = Math.min(0.4 * Math.min(e0, e1), b.h * 0.45);
        eave = Math.max(b.h - roofH, 2.5);
      }
      const z0 = b.z;
      for (let i = 0; i < ring.length; i++) {
        const a = ring[i];
        const c = ring[(i + 1) % ring.length];
        // CCW footprint: outward faces → (a0, c0, cTop), (a0, cTop, aTop)
        push(a[0], a[1], z0, fac, 0.62); push(c[0], c[1], z0, fac, 0.62); push(c[0], c[1], z0 + eave, fac, 1);
        push(a[0], a[1], z0, fac, 0.62); push(c[0], c[1], z0 + eave, fac, 1); push(a[0], a[1], z0 + eave, fac, 1);
      }
      if (gable) {
        const roof = color(this.cat, "roof_tile");
        const m03 = [(ring[0][0] + ring[3][0]) / 2, (ring[0][1] + ring[3][1]) / 2];
        const m12 = [(ring[1][0] + ring[2][0]) / 2, (ring[1][1] + ring[2][1]) / 2];
        const top = z0 + eave + roofH;
        const E = z0 + eave;
        const tri = (p: number[], q: number[], r: number[], c: THREE.Color, sh = 1) => { push(p[0], p[1], p[2], c, sh); push(q[0], q[1], q[2], c, sh); push(r[0], r[1], r[2], c, sh); };
        tri([...ring[0], E], [...ring[1], E], [...m12, top], roof, 0.9);
        tri([...ring[0], E], [...m12, top], [...m03, top], roof, 0.9);
        tri([...ring[2], E], [...ring[3], E], [...m03, top], roof, 1);
        tri([...ring[2], E], [...m03, top], [...m12, top], roof, 1);
        tri([...ring[1], E], [...ring[2], E], [...m12, top], fac);
        tri([...ring[3], E], [...ring[0], E], [...m03, top], fac);
      } else {
        const roof = color(this.cat, "roof_flat");
        const flat = ring.flatMap((p) => [p[0], p[1]]);
        const tris = THREE.ShapeUtils.triangulateShape(ring.map((p) => new THREE.Vector2(p[0], p[1])), []);
        for (const [i, j, k] of tris) {
          const ok = (ring[j][0] - ring[i][0]) * (ring[k][1] - ring[i][1]) - (ring[j][1] - ring[i][1]) * (ring[k][0] - ring[i][0]) > 0;
          const [p, q] = ok ? [j, k] : [k, j];
          push(flat[i * 2], flat[i * 2 + 1], z0 + eave, roof, 1);
          push(flat[p * 2], flat[p * 2 + 1], z0 + eave, roof, 1);
          push(flat[q * 2], flat[q * 2 + 1], z0 + eave, roof, 1);
        }
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    g.computeVertexNormals();
    g.computeBoundingSphere();
    const mesh = new THREE.Mesh(g, this.material);
    mesh.position.copy(enu(o[0], o[1], oz));
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    return mesh;
  }

  dispose() {
    disposeObject(this.group);
  }
}

function signedArea(r: [number, number][]) {
  let a = 0;
  for (let i = 0; i < r.length; i++) {
    const p = r[i], q = r[(i + 1) % r.length];
    a += p[0] * q[1] - q[0] * p[1];
  }
  return a / 2;
}

function nearestS(c: CourseProfile, x: number, y: number): number {
  let best = Infinity, bi = 0;
  for (let i = 0; i < c.count; i += 4) {
    const d = (c.x[i] - x) ** 2 + (c.y[i] - y) ** 2;
    if (d < best) { best = d; bi = i; }
  }
  return c.s[bi];
}
