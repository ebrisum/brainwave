import * as THREE from "three";

/**
 * Procedural placeholder cyclist on a road or TT bike: pedalling driven by crank angle (cadence), wheel spin from speed,
 * lean from speed and radius, standing on steep slow climbs, aero tuck on fast descents. Replace with a licensed rigged
 * glTF later (docs/LICENSES.md).
 */
export class RiderAvatar {
  root = new THREE.Group();
  private body = new THREE.Group();
  private wheels: THREE.Mesh[] = [];
  private crank = new THREE.Group();
  private legs: { thigh: THREE.Mesh; shin: THREE.Mesh; side: number }[] = [];
  private torso: THREE.Mesh;
  private head: THREE.Mesh;
  private jerseyMat: THREE.MeshStandardMaterial;
  private wheelAngle = 0;
  private standing = 0;
  private tuck = 0;

  constructor(jersey = "#f0b429", bike: "road" | "tt" = "road", ghost = false) {
    const frameMat = new THREE.MeshStandardMaterial({ color: 0x1b1f24, roughness: 0.4, metalness: 0.6, transparent: ghost, opacity: ghost ? 0.35 : 1 });
    const tyreMat = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.8, transparent: ghost, opacity: ghost ? 0.35 : 1 });
    this.jerseyMat = new THREE.MeshStandardMaterial({ color: jersey, roughness: 0.6, transparent: ghost, opacity: ghost ? 0.35 : 1 });
    const skin = new THREE.MeshStandardMaterial({ color: 0xd7a07b, roughness: 0.7, transparent: ghost, opacity: ghost ? 0.35 : 1 });
    const shorts = new THREE.MeshStandardMaterial({ color: 0x15171a, roughness: 0.7, transparent: ghost, opacity: ghost ? 0.35 : 1 });
    const R = 0.335;
    for (const z of [-0.5, 0.5]) {
      const w = new THREE.Mesh(new THREE.TorusGeometry(R - 0.012, 0.014, 6, 32), tyreMat);
      w.position.set(0, R, z);
      w.rotation.y = Math.PI / 2;
      if (bike === "tt" && z > 0) (w.material as THREE.Material) = tyreMat;
      this.wheels.push(w);
      this.root.add(w);
    }
    const tube = (a: THREE.Vector3, b: THREE.Vector3, r = 0.016, mat = frameMat) => {
      const d = b.clone().sub(a);
      const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, d.length(), 6), mat);
      m.position.copy(a).add(b).multiplyScalar(0.5);
      m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
      return m;
    };
    // Frame (z forward is negative: the bike faces −z, i.e. three.js "north" when heading 0)
    const bb = new THREE.Vector3(0, 0.28, 0.02);
    const seat = new THREE.Vector3(0, 0.85, 0.2);
    const head = new THREE.Vector3(0, 0.82, -0.38);
    const rear = new THREE.Vector3(0, R, 0.5);
    const front = new THREE.Vector3(0, R, -0.5);
    [tube(bb, seat), tube(seat, head), tube(bb, head), tube(bb, rear), tube(seat, rear), tube(head, front)].forEach((m) => this.root.add(m));
    const bar = tube(new THREE.Vector3(-0.21, 0.88, -0.42), new THREE.Vector3(0.21, 0.88, -0.42), 0.012);
    this.root.add(bar);
    this.crank.position.copy(bb);
    this.root.add(this.crank);
    // Rider
    this.body.position.set(0, 0, 0);
    this.root.add(this.body);
    this.torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.15, 0.42, 4, 8), this.jerseyMat);
    this.body.add(this.torso);
    this.head = new THREE.Mesh(new THREE.SphereGeometry(0.11, 12, 10), new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3, transparent: ghost, opacity: ghost ? 0.35 : 1 }));
    this.body.add(this.head);
    for (const side of [-1, 1]) {
      const thigh = new THREE.Mesh(new THREE.CapsuleGeometry(0.06, 0.32, 4, 6), shorts);
      const shin = new THREE.Mesh(new THREE.CapsuleGeometry(0.045, 0.34, 4, 6), skin);
      this.body.add(thigh, shin);
      this.legs.push({ thigh, shin, side });
      const arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.04, 0.45, 4, 6), this.jerseyMat);
      arm.name = `arm${side}`;
      this.body.add(arm);
    }
    this.root.traverse((o) => { if ((o as THREE.Mesh).isMesh) (o as THREE.Mesh).castShadow = !ghost; });
  }

  setJersey(c: string) {
    this.jerseyMat.color.set(c);
  }

  /** Update pose. crankRad: crank angle; speed m/s; leanRad signed (+ = lean right); grade %; cadence rpm; power W. */
  update(dt: number, crankRad: number, speed: number, leanRad: number, gradePct: number, cadence: number, power: number) {
    this.wheelAngle -= (speed / 0.335) * dt;
    for (const w of this.wheels) w.rotation.x = this.wheelAngle;
    const wantStand = gradePct > 8 && cadence > 0 && cadence < 70 ? 1 : 0;
    const wantTuck = speed > 50 / 3.6 && power < 5 ? 1 : 0;
    this.standing += (wantStand - this.standing) * Math.min(1, dt * 2);
    this.tuck += (wantTuck - this.tuck) * Math.min(1, dt * 1.5);
    this.root.rotation.z = -leanRad;
    // Torso & head
    const hip = new THREE.Vector3(0, 0.92 + 0.18 * this.standing, 0.18 - 0.1 * this.standing);
    const shoulder = new THREE.Vector3(0, 1.22 + 0.1 * this.standing - 0.16 * this.tuck, -0.22 - 0.06 * this.tuck);
    const mid = hip.clone().add(shoulder).multiplyScalar(0.5);
    this.torso.position.copy(mid);
    this.torso.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), shoulder.clone().sub(hip).normalize());
    this.head.position.copy(shoulder).add(new THREE.Vector3(0, 0.12 - 0.04 * this.tuck, -0.12));
    // Arms to the bars
    for (const side of [-1, 1]) {
      const arm = this.body.getObjectByName(`arm${side}`) as THREE.Mesh;
      const sh = shoulder.clone().add(new THREE.Vector3(0.17 * side, -0.02, 0));
      const hand = new THREE.Vector3(0.2 * side, 0.88 - 0.04 * this.tuck, -0.42);
      arm.position.copy(sh).add(hand).multiplyScalar(0.5);
      arm.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), hand.clone().sub(sh).normalize());
    }
    // Legs: two-bone IK from hip to pedal
    const L1 = 0.44, L2 = 0.44, crankLen = 0.17;
    for (const leg of this.legs) {
      const a = crankRad + (leg.side > 0 ? 0 : Math.PI);
      const pedal = new THREE.Vector3(0.1 * leg.side, 0.28 + crankLen * Math.cos(a), 0.02 - crankLen * Math.sin(a));
      const h = hip.clone().add(new THREE.Vector3(0.1 * leg.side, -0.04, 0));
      const d = pedal.clone().sub(h);
      const len = Math.min(d.length(), L1 + L2 - 1e-3);
      const cosA = (L1 * L1 + len * len - L2 * L2) / (2 * L1 * len);
      const ang = Math.acos(Math.min(1, Math.max(-1, cosA)));
      const dir = d.clone().normalize();
      const knee = h.clone().add(dir.clone().applyAxisAngle(new THREE.Vector3(1, 0, 0), ang).multiplyScalar(L1));
      leg.thigh.position.copy(h).add(knee).multiplyScalar(0.5);
      leg.thigh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), knee.clone().sub(h).normalize());
      leg.shin.position.copy(knee).add(pedal).multiplyScalar(0.5);
      leg.shin.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), pedal.clone().sub(knee).normalize());
    }
  }
}
