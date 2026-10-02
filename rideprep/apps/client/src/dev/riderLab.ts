import * as THREE from "three";
import { RiderModel } from "../engine/RiderModel";

/**
 * Dev page (/rider-lab.html): the rigged rider on a plain backdrop, posed exactly (crank phase, clip weights, lean)
 * with fixed orthographic views, to check the exported clips against Blender. URL: ?bike=road|tt&pos=hoods|drops|aero&view=side|left|front|back|34|back34|top
 * &deg=<crank angle>&stand=0..1&coast=0..1&lean=<deg>&half=<zoom>&cx=&cy=<pan>&spin=1 (animate at 90 rpm).
 */
const q = new URLSearchParams(location.search);
const bike = (q.get("bike") ?? "road") as "road" | "tt";
const canvas = document.getElementById("c") as HTMLCanvasElement;
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(2, devicePixelRatio));
renderer.shadowMap.enabled = true;
const scene = new THREE.Scene();
scene.background = new THREE.Color("#c9d3dc");
scene.add(new THREE.HemisphereLight("#eef4ff", "#5a5040", 1.4));
const sun = new THREE.DirectionalLight("#fff6e8", 2.2);
sun.position.set(4, 8, 3);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -2, right: 2, top: 2, bottom: -2 });
scene.add(sun);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(20, 20), new THREE.MeshStandardMaterial({ color: "#8a8f94", roughness: 0.95 }));
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

const rider = new RiderModel(q.get("jersey") ?? "#f0b429", bike, false, (q.get("pos") ?? (bike === "tt" ? "aero" : "hoods")) as "hoods" | "drops" | "aero");
scene.add(rider.root); // faces −Z

const views: Record<string, [THREE.Vector3, THREE.Vector3]> = {
  side: [new THREE.Vector3(6, 0.85, 0.05), new THREE.Vector3(0, 0.85, 0.05)], // camera on the rider's right
  left: [new THREE.Vector3(-6, 0.85, 0.05), new THREE.Vector3(0, 0.85, 0.05)],
  front: [new THREE.Vector3(0, 0.95, -6), new THREE.Vector3(0, 0.95, 0)],
  "34": [new THREE.Vector3(4.2, 2.2, -4.2), new THREE.Vector3(0, 0.8, 0.1)],
  top: [new THREE.Vector3(0, 6, 0.05), new THREE.Vector3(0, 0, 0.05)],
  back: [new THREE.Vector3(0, 1.6, 6), new THREE.Vector3(0, 0.95, 0)], // the chase camera's angle
  back34: [new THREE.Vector3(3.5, 2.0, 4.5), new THREE.Vector3(0, 0.85, 0)],
};
const view = q.get("view") ?? "side";
const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 50);
const [eye, at] = views[view] ?? views.side;
camera.position.copy(eye);
if (view === "top") camera.up.set(0, 0, -1);
camera.lookAt(at);

const half = Number(q.get("half") ?? 1.15); // ortho half-height (m): smaller zooms in
const centre = new THREE.Vector2(Number(q.get("cx") ?? 0), Number(q.get("cy") ?? 0)); // screen-space pan (m)
function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  Object.assign(camera, { left: (-half * w) / h + centre.x, right: (half * w) / h + centre.x, top: half + centre.y, bottom: -half + centre.y });
  camera.updateProjectionMatrix();
}
addEventListener("resize", resize);
resize();

const state = { deg: Number(q.get("deg") ?? 90), stand: Number(q.get("stand") ?? 0), coast: Number(q.get("coast") ?? 0), lean: Number(q.get("lean") ?? 0) };
const spin = q.get("spin") === "1";
const ui = document.getElementById("ui")!;
for (const [k, max] of [["deg", 360], ["stand", 1], ["coast", 1], ["lean", 30]] as const) {
  const l = document.createElement("label");
  l.textContent = `${k} `;
  const i = document.createElement("input");
  Object.assign(i, { type: "range", min: k === "lean" ? "-30" : "0", max: String(max), step: max === 1 ? "0.05" : "1", value: String(state[k]) });
  i.oninput = () => (state[k] = Number(i.value));
  l.appendChild(i);
  ui.appendChild(l);
}

let last = performance.now();
function frame(now: number) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  if (spin) state.deg = (state.deg + dt * 540) % 360; // 90 rpm
  rider.pose((state.deg * Math.PI) / 180, state.stand, state.coast, (state.lean * Math.PI) / 180, spin ? 9 * dt : 0);
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
rider.ready.then(() => {
  (window as unknown as { __riderReady: boolean }).__riderReady = true;
  requestAnimationFrame(frame);
});
Object.assign(window, { __lab: { state, rider, scene, camera, renderer, THREE } });
