import * as THREE from "three";
import { Fetcher, LoadedCourse, QuickBuilding, QuickRoad, QuickWater, poseAt } from "@rideprep/course-format";
import { CameraMode, Quality } from "../store";
import { Buildings } from "./Buildings";
import { CameraRig } from "./CameraRig";
import { ChunkStreamer } from "./ChunkStreamer";
import { CourseMarkers } from "./CourseMarkers";
import { Cockpit } from "./Cockpit";
import { GameWorld } from "./GameWorld";
import { Photoreal, PhotorealOptions } from "./Photoreal";
import { preset } from "./quality";
import { LaneKeeper, RoadLine } from "./LaneKeeper";
import { RiderModel } from "./RiderModel";
import { crossSlopeDz, Road } from "./Road";
import { SkyWeather } from "./SkyWeather";
import { Terrain } from "./Terrain";
import { enu, color } from "./util";
import { Vegetation, windUniforms } from "./Vegetation";

/** What the renderer needs each frame (interpolated physics state). */
export interface RenderState {
  s: number; speed: number; leanRad: number; crankRad: number; gradePct: number; cadence: number; powerW: number;
  windToX: number; windToY: number; uRider: number; gust: number;
  sunElevationDeg: number; sunAzimuthDeg: number; cloud: number; visibilityM: number; rainMmH: number;
  ghostS?: number;
  hr?: number;
}

export class World {
  renderer: THREE.WebGLRenderer;
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(60, 1, 0.3, 30000);
  rig: CameraRig;
  terrain: Terrain;
  road: Road;
  buildings?: Buildings;
  vegetation: Vegetation;
  chunks: ChunkStreamer;
  skyw: SkyWeather;
  rider: RiderModel;
  ghost?: RiderModel;
  /** Where the bike rides across the road (the trainer gives speed, not steering). */
  lane: LaneKeeper;
  private ghostLane: LaneKeeper;
  private lastS = 0;
  markers: CourseMarkers;
  cockpit = new Cockpit();
  photoreal?: Photoreal;
  game?: GameWorld;
  cameraMode: CameraMode = "chase";
  fps = 60;
  private raf = 0;
  private last = 0;
  private frameTimes: number[] = [];
  private scale = 1;
  private baseRatio: number;
  private timeAcc = 0;
  private lastStream = -1e9;
  private wet = false;

  constructor(private canvas: HTMLCanvasElement, private course: LoadedCourse, private fetch: Fetcher,
              quick: { buildings: QuickBuilding[]; roads: QuickRoad[]; water: QuickWater[] }, quality: Quality,
              riderLook: { jersey: string; bike: "road" | "tt"; position?: "hoods" | "drops" | "aero"; line?: RoadLine },
              private source: () => RenderState) {
    const q = preset(quality);
    this.baseRatio = q.pixelRatio;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: q.antialias, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(q.pixelRatio);
    this.renderer.toneMapping = THREE.AgXToneMapping;
    this.renderer.toneMappingExposure = 1.0;
    this.renderer.shadowMap.enabled = q.shadowMap > 0;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.camera.far = q.viewDistance * 2;
    this.rig = new CameraRig(this.camera);
    const m = course.manifest;
    this.skyw = new SkyWeather(this.scene, q.shadowMap);
    this.terrain = new Terrain(m, fetch, course.materials, quality, course.route);
    this.terrain.loadRadius = Math.min(q.viewDistance * 0.4, 6000);
    this.road = new Road(course.route, course.materials, 500);
    this.road.addSideRoads(quick.roads);
    this.buildings = quick.buildings.length ? new Buildings(quick.buildings, course.materials, course.route, 500) : undefined;
    this.vegetation = new Vegetation(course.instances, course.materials, quality, m.wind.leafOn ?? true);
    this.chunks = new ChunkStreamer(course.chunks, fetch, (id, baked) => {
      if (this.road.chunks[id]) this.road.chunks[id].visible = !baked;
      const b = this.buildings?.byChunk.get(id);
      if (b) b.visible = !baked;
    });
    this.rider = new RiderModel(riderLook.jersey, riderLook.bike, false, riderLook.position);
    this.lane = new LaneKeeper(course.route, riderLook.line);
    this.ghostLane = new LaneKeeper(course.route, riderLook.line);
    this.markers = new CourseMarkers(course);
    this.scene.add(this.markers.group);
    this.scene.add(this.terrain.group, this.road.group, this.vegetation.group, this.chunks.group, this.rider.root);
    if (this.buildings) this.scene.add(this.buildings.group);
    this.water = this.addWater(quick.water);
    this.scene.add(this.camera); // the cockpit is parented to the camera
    this.cockpit.attach(this.camera);
    this.resize();
  }

  async init() {
    await this.terrain.loadFar().catch((e) => console.warn("far terrain", e));
    const p = poseAt(this.course.route, 0);
    this.terrain.update(p.x, p.y);
  }

  enableGhost(on: boolean) {
    if (on && !this.ghost) {
      this.ghost = new RiderModel("#ffffff", "road", true);
      this.ghostLane.reset();
      this.scene.add(this.ghost.root);
    } else if (!on && this.ghost) {
      this.ghost.root.removeFromParent();
      this.ghost = undefined;
    }
  }

  private water: THREE.Group;
  private lastGame = -1e9;

  /**
   * Game-art world: the regional art kit's textured terrain, roads, buildings and instanced vegetation replace the
   * generated quick/lite world (course markers and the rider stay).
   */
  setGame(gw: GameWorld | undefined) {
    if (this.game) {
      this.scene.remove(this.game.group);
      this.game.dispose();
    }
    this.game = gw;
    const on = !!gw && !this.photoreal;
    for (const g of [this.terrain.group, this.vegetation.group, this.chunks.group, this.buildings?.group, this.water, this.road.group]) if (g) g.visible = !on;
    if (gw) {
      this.scene.add(gw.group);
      gw.group.visible = !this.photoreal;
      this.lastGame = -1e9;
      this.scene.environment ??= GameWorld.environment(this.renderer);
      this.scene.environmentIntensity = 0.75;
    }
  }

  /**
   * Real-world view: photogrammetric 3D tiles replace our generated terrain, buildings, trees and baked chunks.
   * Our road ribbon (crisp surface, exact width), course markers and the rider stay on top.
   */
  setPhotoreal(opts: PhotorealOptions | null) {
    this.photoreal?.dispose();
    this.photoreal = undefined;
    const on = !!opts;
    for (const g of [this.terrain.group, this.vegetation.group, this.chunks.group, this.buildings?.group, this.water]) if (g) g.visible = !on && !this.game;
    if (this.game) this.game.group.visible = !on;
    this.road.group.visible = on || !this.game;
    if (on) {
      this.road.chunks.forEach((m) => (m.visible = true));
      this.road.material.polygonOffset = true;
      this.road.material.polygonOffsetFactor = -2;
      this.road.material.polygonOffsetUnits = -2;
      this.photoreal = new Photoreal(this.course.manifest, this.course.route, this.camera, this.renderer, opts!);
      this.scene.add(this.photoreal.root);
      this.camera.near = 0.1;
    } else {
      this.road.material.polygonOffset = false;
      this.camera.near = 0.3;
    }
    this.camera.updateProjectionMatrix();
  }

  private addWater(water: QuickWater[]): THREE.Group {
    const group = new THREE.Group();
    this.scene.add(group);
    const mat = new THREE.MeshStandardMaterial({ color: color(this.course.materials, "water"), roughness: 0.08, metalness: 0.1 });
    for (const w of water) {
      const shape = new THREE.Shape(w.ring.map((p) => new THREE.Vector2(p[0] - w.ring[0][0], p[1] - w.ring[0][1])));
      const g = new THREE.ShapeGeometry(shape);
      g.rotateX(-Math.PI / 2); // shape xy (east, north) → xz with north = −z
      const mesh = new THREE.Mesh(g, mat);
      mesh.position.copy(enu(w.ring[0][0], w.ring[0][1], w.z + 0.05));
      mesh.receiveShadow = true;
      group.add(mesh);
    }
    return group;
  }

  setWet(wet: boolean) {
    if (wet === this.wet) return;
    this.wet = wet;
    this.road.setWet(wet);
  }

  resize() {
    const w = this.canvas.clientWidth || window.innerWidth;
    const h = this.canvas.clientHeight || window.innerHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  start() {
    this.last = performance.now();
    const loop = (now: number) => {
      this.raf = requestAnimationFrame(loop);
      const dt = Math.min((now - this.last) / 1000, 0.1);
      this.last = now;
      this.frame(dt);
      this.trackFrameTime(dt);
    };
    this.raf = requestAnimationFrame(loop);
  }

  stop() {
    cancelAnimationFrame(this.raf);
  }

  /** Dynamic resolution: keep frame time near 16.7 ms by scaling the pixel ratio between 50 % and 100 % of the preset. */
  private trackFrameTime(dt: number) {
    this.frameTimes.push(dt);
    if (this.frameTimes.length < 60) return;
    const avg = this.frameTimes.reduce((a, b) => a + b, 0) / this.frameTimes.length;
    this.frameTimes.length = 0;
    this.fps = 1 / avg;
    const prev = this.scale;
    if (avg > 0.0185) this.scale = Math.max(0.5, this.scale - 0.08);
    else if (avg < 0.0135) this.scale = Math.min(1, this.scale + 0.05);
    if (prev !== this.scale) this.renderer.setPixelRatio(this.baseRatio * this.scale);
  }

  private frame(dt: number) {
    const st = this.source();
    const c = this.course.route;
    const p = poseAt(c, st.s);
    if (Math.abs(st.s - this.lastS) > 50) this.lane.reset(); // start, restart or a jump along the course
    this.lastS = st.s;
    this.lane.update(dt, st.s, st.speed, st.crankRad);
    const riderPos = this.onRoad(p, st.s, this.lane.offset);
    this.rider.root.position.copy(riderPos);
    this.rider.root.rotation.set(0, -(p.headingRad + this.lane.yaw), 0, "YXZ");
    const ri = Math.min(c.count - 1, Math.max(0, Math.round(st.s / c.spacingM)));
    this.rider.update(dt, st.crankRad, st.speed, st.leanRad + this.lane.lean, st.gradePct, st.cadence, st.powerW, c.radiusM[ri]);
    if (this.ghost && st.ghostS !== undefined) {
      const g = poseAt(c, st.ghostS);
      this.ghostLane.update(dt, st.ghostS, st.speed, st.crankRad);
      this.ghost.root.position.copy(this.onRoad(g, st.ghostS, this.ghostLane.offset));
      this.ghost.root.rotation.set(0, -(g.headingRad + this.ghostLane.yaw), 0, "YXZ");
      this.ghost.update(dt, st.crankRad, st.speed, this.ghostLane.lean, st.gradePct, st.cadence, st.powerW);
    }
    const fwd = new THREE.Vector3(Math.sin(p.headingRad), 0, -Math.cos(p.headingRad));
    const sAhead = st.s + Math.max(25, st.speed * 2.5);
    const ahead = this.onRoad(poseAt(c, sAhead), sAhead, this.lane.target(sAhead, st.speed));
    const cockpit = this.cameraMode === "cockpit";
    this.rider.root.visible = !cockpit;
    this.cockpit.setVisible(cockpit);
    if (cockpit) {
      const standing = st.gradePct > 8 && st.cadence > 0 && st.cadence < 70;
      const bob = this.cockpit.eyeBob(dt, st.cadence, standing);
      this.rig.eyeOffset.set(Math.cos(p.headingRad) * bob.x, bob.y, Math.sin(p.headingRad) * bob.x);
      this.rig.roll = -st.leanRad * 0.6;
      this.cockpit.updateScreen(st.powerW, st.speed * 3.6, st.gradePct, st.cadence, st.hr);
    }
    this.rig.update(dt, this.cameraMode, riderPos, fwd, ahead, (q) => {
      // ground under the camera: nearest route height is a safe lower bound near the road
      return riderPos.y + (q.y - q.y) - 2;
    });
    // Wind for vegetation sway (direction the wind blows TOWARD, three.js xz)
    this.timeAcc += dt;
    windUniforms.uTime.value = this.timeAcc;
    const wl = Math.hypot(st.windToX, st.windToY) || 1;
    windUniforms.uWindDir.value.set(st.windToX / wl, -st.windToY / wl);
    windUniforms.uWindStrength.value = st.uRider;
    windUniforms.uGust.value = st.gust;
    this.markers.update(dt, st.windToX / wl, st.windToY / wl, st.uRider * 1.6 * st.gust);
    this.skyw.set(st.sunElevationDeg, st.sunAzimuthDeg, st.cloud, st.visibilityM, st.rainMmH);
    this.skyw.followRider(riderPos);
    this.skyw.update(dt, (st.windToX / wl) * st.uRider, (-st.windToY / wl) * st.uRider);
    this.setWet(st.rainMmH > 0.2);
    if (this.photoreal) {
      this.camera.updateMatrixWorld();
      this.photoreal.update(st.s);
    }
    if (this.game && !this.photoreal && Math.abs(st.s - this.lastGame) > 8) {
      this.lastGame = st.s;
      this.game.update(st.s, this.camera.position);
    }
    if (!this.photoreal && !this.game && Math.abs(st.s - this.lastStream) > 50) {
      this.lastStream = st.s;
      this.terrain.update(p.x, p.y);
      this.vegetation.update(p.x, p.y);
      this.chunks.update(st.s);
    }
    this.renderer.render(this.scene, this.camera);
  }

  /** Road surface point `off` metres right of the route centreline (crown/superelevation included), three.js coords. */
  private onRoad(p: { x: number; y: number; z: number; headingRad: number }, s: number, off: number): THREE.Vector3 {
    const c = this.course.route;
    const i = Math.min(c.count - 1, Math.max(0, Math.round(s / c.spacingM)));
    const rx = Math.cos(p.headingRad); // right of the heading, ENU
    const ry = -Math.sin(p.headingRad);
    return enu(p.x + rx * off, p.y + ry * off, p.z + crossSlopeDz(off, c.bankDeg?.[i] ?? 0));
  }

  dispose() {
    this.stop();
    this.terrain.dispose();
    this.road.dispose();
    this.vegetation.dispose();
    this.chunks.dispose();
    this.buildings?.dispose();
    this.photoreal?.dispose();
    this.game?.dispose();
    this.renderer.dispose();
  }
}
