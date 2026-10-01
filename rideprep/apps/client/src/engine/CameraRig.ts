import * as THREE from "three";
import { CameraMode } from "../store";

/** Chase (default), first-person, side, drone and cinematic flyover cameras, smoothed. */
export class CameraRig {
  private pos = new THREE.Vector3();
  private look = new THREE.Vector3();
  private init = false;

  constructor(public camera: THREE.PerspectiveCamera) {}

  /** rider: three.js position; fwd: unit forward vector (three.js xz); ahead: a point ~25 m ahead on the route. */
  update(dt: number, mode: CameraMode, rider: THREE.Vector3, fwd: THREE.Vector3, ahead: THREE.Vector3, groundAt: (p: THREE.Vector3) => number) {
    const right = new THREE.Vector3(-fwd.z, 0, fwd.x);
    const p = new THREE.Vector3();
    const l = new THREE.Vector3();
    switch (mode) {
      case "cockpit":
        // Eye position over the bars; look ~25 m down the road
        p.copy(rider).addScaledVector(fwd, 0.05).add(new THREE.Vector3(0, 1.48, 0)).add(this.eyeOffset);
        l.copy(ahead).add(new THREE.Vector3(0, 1.0, 0));
        break;
      case "side":
        p.copy(rider).addScaledVector(right, 5).addScaledVector(fwd, 1.5).add(new THREE.Vector3(0, 1.3, 0));
        l.copy(rider).add(new THREE.Vector3(0, 0.9, 0));
        break;
      case "drone":
        p.copy(rider).addScaledVector(fwd, -35).add(new THREE.Vector3(0, 28, 0));
        l.copy(rider).addScaledVector(fwd, 20);
        break;
      case "flyover":
        p.copy(rider).addScaledVector(fwd, -60).addScaledVector(right, 25).add(new THREE.Vector3(0, 45, 0));
        l.copy(ahead);
        break;
      default:
        p.copy(rider).addScaledVector(fwd, -5.5).add(new THREE.Vector3(0, 2.3, 0));
        l.copy(ahead).add(new THREE.Vector3(0, 0.6, 0));
    }
    const minY = groundAt(p) + 0.8;
    if (p.y < minY) p.y = minY;
    const k = this.init ? 1 - Math.exp(-dt * (mode === "cockpit" ? 30 : 4)) : 1;
    this.pos.lerp(p, k);
    this.look.lerp(l, this.init ? 1 - Math.exp(-dt * 6) : 1);
    this.init = true;
    this.camera.position.copy(this.pos);
    this.camera.lookAt(this.look);
    if (mode === "cockpit") this.camera.rotateZ(this.roll);
  }

  /** Cockpit extras set by the world each frame. */
  eyeOffset = new THREE.Vector3();
  roll = 0;

  reset() {
    this.init = false;
  }
}
