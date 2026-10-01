import * as THREE from "three";

/**
 * First-person cockpit: drop handlebars, stem, gloved hands on the hoods and a bike computer with live numbers,
 * attached to the camera. The camera sits at eye height over the bars with a small pedalling bob and corner roll.
 */
export class Cockpit {
  group = new THREE.Group();
  private screen: HTMLCanvasElement;
  private tex: THREE.CanvasTexture;
  private lastDraw = 0;
  private bob = 0;

  constructor(gloves = "#1b1f24", tape = "#111111") {
    const tapeMat = new THREE.MeshStandardMaterial({ color: tape, roughness: 0.7 });
    const metal = new THREE.MeshStandardMaterial({ color: 0x2a2e33, roughness: 0.35, metalness: 0.7 });
    const glove = new THREE.MeshStandardMaterial({ color: gloves, roughness: 0.8 });
    // Bar geometry in a bike frame: x right, y up, z backward (camera looks down −z). Bars ~0.42 m wide.
    const half = (side: number) => new THREE.CatmullRomCurve3([
      new THREE.Vector3(0, 0, 0), new THREE.Vector3(0.21 * side, 0, 0), new THREE.Vector3(0.215 * side, 0.005, -0.06),
      new THREE.Vector3(0.22 * side, -0.05, -0.1), new THREE.Vector3(0.22 * side, -0.13, -0.06), new THREE.Vector3(0.22 * side, -0.14, 0.03),
    ]);
    for (const side of [-1, 1]) {
      const bar = new THREE.Mesh(new THREE.TubeGeometry(half(side), 48, 0.0125, 10, false), tapeMat);
      this.group.add(bar);
      // brake hood + lever
      const hood = new THREE.Mesh(new THREE.CapsuleGeometry(0.018, 0.06, 4, 8), metal);
      hood.position.set(0.215 * side, 0.02, -0.09);
      hood.rotation.x = Math.PI / 2.3;
      this.group.add(hood);
      // gloved hand resting on the hood
      const hand = new THREE.Mesh(new THREE.CapsuleGeometry(0.032, 0.07, 4, 10), glove);
      hand.position.set(0.212 * side, 0.045, -0.075);
      hand.rotation.set(Math.PI / 2.2, 0, side * 0.15);
      this.group.add(hand);
      const fingers = new THREE.Mesh(new THREE.CapsuleGeometry(0.02, 0.05, 4, 8), glove);
      fingers.position.set(0.22 * side, 0.0, -0.13);
      fingers.rotation.set(0.2, 0, Math.PI / 2);
      this.group.add(fingers);
    }
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.018, 0.11, 10), metal);
    stem.rotation.x = Math.PI / 2 - 0.12;
    stem.position.set(0, -0.012, 0.055);
    this.group.add(stem);
    const steerer = new THREE.Mesh(new THREE.CylinderGeometry(0.019, 0.019, 0.25, 10), metal);
    steerer.position.set(0, -0.14, 0.11);
    this.group.add(steerer);
    // Bike computer on an out-front mount
    this.screen = document.createElement("canvas");
    this.screen.width = 256;
    this.screen.height = 176;
    this.tex = new THREE.CanvasTexture(this.screen);
    this.tex.colorSpace = THREE.SRGBColorSpace;
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.058, 0.014, 0.088), new THREE.MeshStandardMaterial({ color: 0x15171a, roughness: 0.5 }));
    body.position.set(0, 0.022, -0.075);
    body.rotation.x = -0.35;
    const face = new THREE.Mesh(new THREE.PlaneGeometry(0.05, 0.075), new THREE.MeshBasicMaterial({ map: this.tex, toneMapped: false }));
    face.rotation.x = -Math.PI / 2;
    face.position.y = 0.0075;
    body.add(face);
    this.group.add(body);
    this.group.traverse((o) => { o.frustumCulled = false; o.renderOrder = 10; });
  }

  /**
   * Bars relative to the camera. Real eyes sit ~0.5 m above and behind the bars, but a 60° view cone would cut them
   * off; like other cycling sims we pull them into the lower third of the frame.
   */
  attach(camera: THREE.Camera) {
    camera.add(this.group);
    this.group.position.set(0, -0.27, -0.6);
    this.group.rotation.x = 0.7;
  }

  setVisible(v: boolean) {
    this.group.visible = v;
  }

  /** Eye offset from the head position for this frame (bob from pedalling, more when standing). */
  eyeBob(dt: number, cadence: number, standing: boolean): THREE.Vector3 {
    this.bob += (cadence / 60) * 2 * Math.PI * dt * 2; // two bobs per crank revolution
    const amp = standing ? 0.025 : 0.006;
    return new THREE.Vector3(Math.sin(this.bob / 2) * amp * (standing ? 1.6 : 0.5), Math.abs(Math.sin(this.bob / 2)) * amp, 0);
  }

  updateScreen(power: number, speedKmh: number, gradePct: number, cadence: number, hr?: number) {
    const now = performance.now();
    if (now - this.lastDraw < 250) return;
    this.lastDraw = now;
    const g = this.screen.getContext("2d")!;
    g.fillStyle = "#0c0e10";
    g.fillRect(0, 0, 256, 176);
    g.fillStyle = "#f0b429";
    g.font = "bold 64px system-ui, sans-serif";
    g.textAlign = "center";
    g.fillText(`${Math.round(power)}`, 128, 70);
    g.fillStyle = "#cfd6dd";
    g.font = "22px system-ui, sans-serif";
    g.fillText("W", 210, 70);
    g.font = "bold 34px system-ui, sans-serif";
    g.fillStyle = "#ffffff";
    g.textAlign = "left";
    g.fillText(`${speedKmh.toFixed(1)}`, 12, 122);
    g.fillText(`${gradePct.toFixed(1)}%`, 140, 122);
    g.font = "24px system-ui, sans-serif";
    g.fillStyle = "#98a2ad";
    g.fillText(`${Math.round(cadence)} rpm`, 12, 162);
    if (hr) g.fillText(`♥ ${Math.round(hr)}`, 140, 162);
    this.tex.needsUpdate = true;
  }
}
