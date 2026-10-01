import * as THREE from "three";
import { LoadedCourse, poseAt } from "@rideprep/course-format";
import { enu } from "./util";

function labelTexture(text: string, sub?: string): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = "#0d0f12";
  g.fillRect(0, 0, 512, 128);
  g.fillStyle = "#f0b429";
  g.fillRect(0, 118, 512, 10);
  g.fillStyle = "#ffffff";
  g.font = "bold 54px system-ui, sans-serif";
  g.textAlign = "center";
  g.fillText(text, 256, sub ? 62 : 82);
  if (sub) {
    g.font = "36px system-ui, sans-serif";
    g.fillStyle = "#cfd6dd";
    g.fillText(sub, 256, 106);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

/**
 * Subtle course information in the world: banners at climb starts/tops, aid stations and the finish,
 * and flags at town entries and bridges that point and flutter with the real wind.
 */
export class CourseMarkers {
  group = new THREE.Group();
  private flags: { cloth: THREE.Mesh; base: Float32Array; pivot: THREE.Group }[] = [];
  private t = 0;

  constructor(course: LoadedCourse) {
    const seg = course.manifest.segments;
    const pole = new THREE.MeshStandardMaterial({ color: 0x2b3036, roughness: 0.5, metalness: 0.4 });
    const banner = (s: number, text: string, sub?: string) => {
      const p = poseAt(course.route, s);
      const i = Math.min(Math.round(s / course.route.spacingM), course.route.count - 1);
      const hw = course.route.roadWidthM[i] / 2 + 0.6;
      const g = new THREE.Group();
      for (const side of [-1, 1]) {
        const m = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 4.6, 8), pole);
        m.position.set(side * hw, 2.3, 0);
        g.add(m);
      }
      const plane = new THREE.Mesh(new THREE.PlaneGeometry(Math.max(hw * 2, 3), 0.9), new THREE.MeshBasicMaterial({ map: labelTexture(text, sub), side: THREE.DoubleSide, toneMapped: false }));
      plane.position.set(0, 4.3, 0);
      g.add(plane);
      g.position.copy(enu(p.x, p.y, p.z));
      g.rotation.y = -p.headingRad;
      this.group.add(g);
    };
    for (const c of seg.climbs) {
      banner(c.sStart, `Climb ${(c.lengthM / 1000).toFixed(1)} km`, `${c.avgGradePct.toFixed(1)} % avg · max ${c.maxGradePct.toFixed(0)} % · +${Math.round(c.gainM)} m`);
      banner(c.sEnd, "Top", `cat ${c.category}`);
    }
    for (const p of seg.pois) {
      if (p.type === "aid_station") banner(p.s, "Aid station", p.name);
      else if (p.type === "transition") banner(p.s, "Transition", p.name);
      else if (p.type === "town_entry" || p.type === "bridge") this.addFlag(course, p.s, pole);
    }
    const L = course.manifest.stats.distanceM;
    if (L > 200) banner(L - 1, "Finish");
    for (const l of seg.laps.slice(1)) banner(l.sStart + 1, `Lap ${l.index + 1}/${seg.laps.length}`);
  }

  private addFlag(course: LoadedCourse, s: number, poleMat: THREE.Material) {
    const p = poseAt(course.route, s);
    const i = Math.min(Math.round(s / course.route.spacingM), course.route.count - 1);
    const off = course.route.roadWidthM[i] / 2 + 2;
    const nx = Math.cos(p.headingRad), ny = -Math.sin(p.headingRad);
    const root = new THREE.Group();
    root.position.copy(enu(p.x + nx * off, p.y + ny * off, p.z));
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 6, 8), poleMat);
    mast.position.y = 3;
    root.add(mast);
    const pivot = new THREE.Group();
    pivot.position.y = 5.4;
    const geo = new THREE.PlaneGeometry(1.5, 1, 12, 4).translate(0.75, 0, 0);
    const cloth = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0xd55e00, side: THREE.DoubleSide, roughness: 0.8 }));
    pivot.add(cloth);
    root.add(pivot);
    this.group.add(root);
    this.flags.push({ cloth, base: Float32Array.from(geo.getAttribute("position").array as Float32Array), pivot });
  }

  /** windToX/Y: unit vector (ENU) the wind blows toward; u: wind speed at flag height (m/s). */
  update(dt: number, windToX: number, windToY: number, u: number) {
    this.t += dt;
    const yaw = Math.atan2(windToY, windToX); // ENU angle from east, CCW
    const droop = Math.max(0, 1 - u / 4);
    for (const f of this.flags) {
      f.pivot.rotation.set(0, yaw, -droop * 1.2);
      const pos = f.cloth.geometry.getAttribute("position") as THREE.BufferAttribute;
      for (let k = 0; k < pos.count; k++) {
        const x = f.base[k * 3];
        const amp = 0.05 + 0.02 * Math.min(u, 12);
        pos.setZ(k, Math.sin(this.t * (3 + u * 0.6) - x * 4) * amp * x);
      }
      pos.needsUpdate = true;
    }
  }
}
