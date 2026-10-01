import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { Instances, MaterialCatalogue } from "@rideprep/course-format";
import { color, disposeObject, enu } from "./util";

const CELL = 1500;

/** Shared wind uniforms: direction the wind blows TOWARD in three.js xz, strength (m/s at rider height) and gust. */
export const windUniforms = { uTime: { value: 0 }, uWindDir: { value: new THREE.Vector2(1, 0) }, uWindStrength: { value: 0 }, uGust: { value: 1 } };

function swayMaterial(mat: THREE.MeshStandardMaterial, stiffness: number): THREE.MeshStandardMaterial {
  mat.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, windUniforms, { uStiff: { value: stiffness } });
    sh.vertexShader = sh.vertexShader
      .replace("#include <common>", "#include <common>\nuniform float uTime; uniform vec2 uWindDir; uniform float uWindStrength; uniform float uGust; uniform float uStiff;")
      .replace("#include <begin_vertex>", `#include <begin_vertex>
        #ifdef USE_INSTANCING
          vec3 ip = vec3(instanceMatrix[3][0], instanceMatrix[3][1], instanceMatrix[3][2]);
        #else
          vec3 ip = vec3(0.0);
        #endif
        float hgt = clamp(position.y, 0.0, 1.0);
        float bend = hgt * hgt * uWindStrength * uGust * uStiff * 0.03;
        float flutter = sin(uTime * (1.3 + uWindStrength * 0.15) + ip.x * 0.37 + ip.z * 0.21) * 0.35 + 0.65;
        transformed.x += uWindDir.x * bend * flutter;
        transformed.z += uWindDir.y * bend * flutter;`);
  };
  return mat;
}

function treeGeometry(kind: "deciduous" | "conifer" | "poplar", crown: THREE.Color, bark: THREE.Color): THREE.BufferGeometry {
  // Unit-height tree (height scaled by instance matrix); y in 0..1 so the sway shader can use position.y as height fraction.
  const trunk = new THREE.CylinderGeometry(0.02, 0.03, 0.35, 5).translate(0, 0.175, 0);
  let top: THREE.BufferGeometry;
  if (kind === "conifer") top = new THREE.ConeGeometry(0.2, 0.8, 7).translate(0, 0.6, 0);
  else if (kind === "poplar") top = new THREE.CylinderGeometry(0.07, 0.11, 0.8, 7).translate(0, 0.58, 0);
  else top = new THREE.IcosahedronGeometry(0.28, 1).scale(1, 0.9, 1).translate(0, 0.68, 0);
  const paint = (g: THREE.BufferGeometry, c: THREE.Color) => {
    const n = g.getAttribute("position").count;
    const a = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const sh = 0.75 + 0.25 * g.getAttribute("position").getY(i);
      a[i * 3] = c.r * sh; a[i * 3 + 1] = c.g * sh; a[i * 3 + 2] = c.b * sh;
    }
    g.setAttribute("color", new THREE.BufferAttribute(a, 3));
    return g.index ? g.toNonIndexed() : g;
  };
  return mergeGeometries([paint(trunk, bark), paint(top, crown)])!;
}

/** Instanced vegetation and props from instances.bin, partitioned into 1.5 km cells and shown by distance. */
export class Vegetation {
  group = new THREE.Group();
  private cells: { cx: number; cy: number; meshes: THREE.InstancedMesh[] }[] = [];
  viewDistance = 2500;

  constructor(inst: Instances, cat: MaterialCatalogue, quality: string, leafOn: boolean) {
    this.viewDistance = { low: 1200, medium: 2000, high: 2800, ultra: 4000 }[quality] ?? 2500;
    const bark = color(cat, "bark");
    const decid = color(cat, "tree_deciduous");
    if (!leafOn) decid.lerp(new THREE.Color(0.42, 0.36, 0.3), 0.7);
    const geos: Record<number, THREE.BufferGeometry> = {
      0: treeGeometry("deciduous", decid, bark),
      1: treeGeometry("conifer", color(cat, "tree_conifer"), bark),
      2: treeGeometry("poplar", decid, bark),
      3: new THREE.BoxGeometry(3, 1, 1.2).translate(0, 0.5, 0),
      4: new THREE.BoxGeometry(0.12, 1, 0.12).translate(0, 0.5, 0),
    };
    const mats: Record<number, THREE.MeshStandardMaterial> = {
      0: swayMaterial(new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9 }), 1),
      1: swayMaterial(new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9 }), 0.6),
      2: swayMaterial(new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9 }), 1.3),
      3: swayMaterial(new THREE.MeshStandardMaterial({ color: color(cat, "hedge"), roughness: 0.95 }), 0.3),
      4: new THREE.MeshStandardMaterial({ color: 0xe8e8e8, roughness: 0.6 }),
    };
    const buckets = new Map<string, Map<number, number[]>>();
    for (let i = 0; i < inst.count; i++) {
      const key = `${Math.floor(inst.x[i] / CELL)}_${Math.floor(inst.y[i] / CELL)}`;
      const b = buckets.get(key) ?? buckets.set(key, new Map()).get(key)!;
      (b.get(inst.category[i]) ?? b.set(inst.category[i], []).get(inst.category[i])!).push(i);
    }
    const m4 = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const up = new THREE.Vector3(0, 1, 0);
    const p = new THREE.Vector3();
    const sc = new THREE.Vector3();
    for (const [key, byCat] of buckets) {
      const [ci, cj] = key.split("_").map(Number);
      const cx = (ci + 0.5) * CELL, cy = (cj + 0.5) * CELL;
      const cell = { cx, cy, meshes: [] as THREE.InstancedMesh[] };
      for (const [k, ids] of byCat) {
        const mesh = new THREE.InstancedMesh(geos[k], mats[k], ids.length);
        ids.forEach((i, n) => {
          const h = inst.height[i];
          q.setFromAxisAngle(up, -inst.rot[i]);
          if (k === 3) sc.set(1, h, 1);
          else if (k === 4) sc.set(1, h, 1);
          else sc.set(h, h, h);
          enu(inst.x[i] - cx, inst.y[i] - cy, inst.z[i], p);
          m4.compose(p, q, sc);
          mesh.setMatrixAt(n, m4);
        });
        mesh.instanceMatrix.needsUpdate = true;
        mesh.computeBoundingSphere();
        mesh.position.copy(enu(cx, cy, 0));
        mesh.castShadow = k < 3;
        mesh.receiveShadow = true;
        cell.meshes.push(mesh);
        this.group.add(mesh);
      }
      this.cells.push(cell);
    }
  }

  update(x: number, y: number) {
    for (const c of this.cells) {
      const vis = Math.hypot(c.cx - x, c.cy - y) < this.viewDistance + CELL * 0.7;
      for (const m of c.meshes) m.visible = vis;
    }
  }

  dispose() {
    disposeObject(this.group);
  }
}
