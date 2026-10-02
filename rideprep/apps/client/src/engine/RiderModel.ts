import * as THREE from "three";
import { GLTF, GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import * as SkeletonUtils from "three/examples/jsm/utils/SkeletonUtils.js";
import { RiderAvatar } from "./RiderAvatar";

/**
 * Rigged cyclist on a road or TT bike (tools/rider/build_rider.py: MakeHuman CC0 body, fitted procedural bike).
 * One skeleton drives rider and bike; clips are one crank revolution (pedal, stand) or a pose (coast), with drops
 * variants on the road bike. The clip time follows the physics crank angle, so the legs, cranks and pedals stay in
 * sync at any cadence. Wheels spin from speed, the whole bike leans into corners, and the steer bone turns slightly
 * through bends. Falls back to the procedural avatar if the model cannot load.
 */
const URLS = { road: "/models/rider_road.glb", tt: "/models/rider_tt.glb" } as const;
const loads = new Map<string, Promise<GLTF>>();
const TAU = Math.PI * 2;
const WHEEL_R = 0.3345;

function loadOnce(url: string): Promise<GLTF> {
  let p = loads.get(url);
  if (!p) {
    p = new GLTFLoader().loadAsync(url);
    loads.set(url, p);
  }
  return p;
}

export class RiderModel {
  root = new THREE.Group();
  ready: Promise<void>;
  private lean = new THREE.Group();
  private mixer?: THREE.AnimationMixer;
  private actions: Record<string, THREE.AnimationAction> = {};
  private seated: (THREE.AnimationAction | undefined)[] = []; // [pedal, coast] for the chosen hand position
  private wheels: { bone: THREE.Bone; axis: THREE.Vector3 }[] = [];
  private steer?: { bone: THREE.Bone; axis: THREE.Vector3 };
  private fallback?: RiderAvatar;
  private wheelAngle = 0;
  private standing = 0;
  private coasting = 0;
  private q = new THREE.Quaternion();

  constructor(private jersey = "#f0b429", private bike: "road" | "tt" = "road", private ghost = false, private position: "hoods" | "drops" | "aero" = "hoods") {
    this.root.add(this.lean);
    this.ready = this.load().catch((e) => {
      console.warn("rider model unavailable, using the procedural avatar", e);
      this.fallback = new RiderAvatar(jersey, bike, ghost);
      this.root.add(this.fallback.root);
    });
  }

  private async load() {
    const gltf = await loadOnce(URLS[this.bike]);
    const model = SkeletonUtils.clone(gltf.scene);
    model.rotation.y = Math.PI / 2; // model faces +X; the rider root faces −Z
    const tint = new THREE.Color(this.jersey);
    model.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!m.isMesh) return;
      m.castShadow = !this.ghost;
      m.receiveShadow = !this.ghost;
      m.frustumCulled = false; // skinned bounds follow the bind pose, not the riding pose
      const mats = (Array.isArray(m.material) ? m.material : [m.material]).map((mat) => {
        const c = (mat as THREE.MeshStandardMaterial).clone();
        if (c.name.startsWith("jersey")) c.color.copy(tint);
        if (this.ghost) {
          c.transparent = true;
          c.opacity = 0.35;
          c.depthWrite = false;
        }
        return c;
      });
      m.material = Array.isArray(m.material) ? mats : mats[0];
    });
    this.mixer = new THREE.AnimationMixer(model);
    for (const clip of gltf.animations) {
      const a = this.mixer.clipAction(clip);
      a.play();
      a.setEffectiveWeight(0);
      a.setEffectiveTimeScale(0); // time is set from the crank angle each frame
      this.actions[clip.name] = a;
    }
    const drops = this.position === "drops" && this.actions.pedal_drops ? "_drops" : "";
    this.seated = [this.actions["pedal" + drops], this.actions["coast" + drops]];
    this.mixer.update(0);
    model.updateMatrixWorld(true);
    // Spin/steer axes in each bone's local frame: wheels about the bike's lateral axis, steer about its own axis
    const modelQ = model.getWorldQuaternion(new THREE.Quaternion());
    const lateral = new THREE.Vector3(0, 0, -1); // Blender +Y (left) after the glTF Y-up conversion
    model.traverse((o) => {
      const b = o as THREE.Bone;
      if (!b.isBone) return;
      const rel = modelQ.clone().invert().multiply(b.getWorldQuaternion(new THREE.Quaternion()));
      if (b.name === "wheelF" || b.name === "wheelR") this.wheels.push({ bone: b, axis: lateral.clone().applyQuaternion(rel.clone().invert()) });
      if (b.name === "steer") this.steer = { bone: b, axis: new THREE.Vector3(0, 1, 0) };
    });
    this.lean.add(model);
  }

  /** Update pose. crankRad: crank angle (0 = right pedal at the top); speed m/s; leanRad + = right; grade %; cadence rpm; power W. */
  update(dt: number, crankRad: number, speed: number, leanRad: number, gradePct: number, cadence: number, power: number, radiusM = Infinity) {
    if (this.fallback) {
      this.fallback.update(dt, crankRad, speed, leanRad, gradePct, cadence, power);
      return;
    }
    const wantStand = gradePct > 8 && cadence > 0 && cadence < 70 ? 1 : 0;
    const wantCoast = cadence < 8 || power < 5 ? 1 : 0;
    this.standing += (wantStand - this.standing) * Math.min(1, dt * 2.2);
    this.coasting += (wantCoast - this.coasting) * Math.min(1, dt * 3);
    // Steering: kinematic bicycle, atan(wheelbase / R), small and smoothed by the radius filter upstream
    const steer = Number.isFinite(radiusM) && radiusM > 3 ? Math.atan(0.99 / radiusM) * Math.sign(leanRad || 0) : 0;
    this.pose(crankRad, this.standing, this.coasting, leanRad, (speed / WHEEL_R) * dt, steer);
  }

  /** Pose directly: crank angle, clip weights (0..1), lean (+ = right), wheel rotation step and steer angle (rad, + = right). */
  pose(crankRad: number, standing: number, coasting: number, leanRad = 0, wheelStep = 0, steerRad = 0) {
    this.lean.rotation.z = -leanRad;
    if (!this.mixer) return;
    // Clip phase: clips start with the right crank forward (3 o'clock)
    const phi = (((crankRad - Math.PI / 2) % TAU) + TAU) % TAU;
    const [pedal, coast] = this.seated;
    const stand = this.actions.stand;
    for (const a of [pedal, stand]) if (a) a.time = (phi / TAU) * a.getClip().duration;
    pedal?.setEffectiveWeight((1 - standing) * (1 - coasting));
    stand?.setEffectiveWeight(standing * (1 - coasting));
    coast?.setEffectiveWeight(coasting);
    this.mixer.update(0);
    // Wheels and steering after the clips (they only key the rest orientation)
    this.wheelAngle = (this.wheelAngle + wheelStep) % TAU;
    for (const w of this.wheels) w.bone.quaternion.multiply(this.q.setFromAxisAngle(w.axis, this.wheelAngle));
    if (this.steer && steerRad) this.steer.bone.quaternion.multiply(this.q.setFromAxisAngle(this.steer.axis, -steerRad));
  }
}
