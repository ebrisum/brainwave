import * as THREE from "three";
import { DRACOLoader } from "three/examples/jsm/loaders/DRACOLoader.js";
import { TilesRenderer } from "3d-tiles-renderer";
import { GoogleCloudAuthPlugin, GLTFExtensionsPlugin, TilesFadePlugin, UnloadTilesPlugin } from "3d-tiles-renderer/plugins";
import { CourseProfile, globeAnchor, GlobeAnchor, Manifest, poseAt } from "@rideprep/course-format";

export const GOOGLE_3D_TILES_URL = "https://tile.googleapis.com/v1/3dtiles/root.json";

export interface PhotorealOptions {
  /** Google Maps Platform key with the Map Tiles API enabled (runtime streaming only — never cached or baked). */
  apiKey?: string;
  /** Any 3D Tiles 1.x tileset URL instead of Google (e.g. the package's dev stand-in, or a Cesium-hosted tileset). */
  url?: string;
}

/**
 * Real-world view from photogrammetric 3D tiles (Google Photorealistic 3D Tiles — what Google Earth shows), placed
 * exactly on the course: an ECEF → course-frame anchor that follows the rider (re-anchored every 750 m so Earth
 * curvature never shows), and a vertical offset calibrated by raycasting the tiles at the road ahead and behind.
 */
export class Photoreal {
  root = new THREE.Group();
  tiles: TilesRenderer;
  anchor?: GlobeAnchor;
  verticalOffset = 0;
  calibrated = false;
  private anchorS = -1e9;
  private raycaster = new THREE.Raycaster();
  private lastCal = 0;
  private offsets: number[] = [];

  constructor(private manifest: Manifest, private route: CourseProfile, camera: THREE.Camera, renderer: THREE.WebGLRenderer, opts: PhotorealOptions) {
    const url = opts.url ?? GOOGLE_3D_TILES_URL;
    this.tiles = new TilesRenderer(url);
    if (!opts.url) {
      if (!opts.apiKey) throw new Error("Photoreal mode needs a Google Maps Platform API key (Map Tiles API enabled)");
      this.tiles.registerPlugin(new GoogleCloudAuthPlugin({ apiToken: opts.apiKey, autoRefreshToken: true }));
    }
    const draco = new DRACOLoader().setDecoderPath(`${import.meta.env.BASE_URL}draco/`);
    this.tiles.registerPlugin(new GLTFExtensionsPlugin({ dracoLoader: draco }));
    this.tiles.registerPlugin(new TilesFadePlugin());
    this.tiles.registerPlugin(new UnloadTilesPlugin());
    this.tiles.errorTarget = opts.url ? 8 : 12;
    this.tiles.setCamera(camera);
    this.tiles.setResolutionFromRenderer(camera, renderer);
    this.tiles.addEventListener("load-model", (e: { scene: THREE.Object3D }) => {
      e.scene.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        m.receiveShadow = true;
        const mat = m.material as THREE.MeshStandardMaterial;
        if (mat && "side" in mat) mat.side = THREE.DoubleSide;
      });
    });
    this.root.matrixAutoUpdate = false;
    this.root.add(this.tiles.group);
  }

  /** Re-anchor the ECEF transform at route distance s (course frame → three: (x, z, −y)). */
  anchorAt(s: number) {
    const p = poseAt(this.route, s);
    const o = this.manifest.origin;
    this.anchor = globeAnchor(o.lat, o.lon, p.x, p.y, p.z, o.geoidUndulation ?? 0);
    this.anchorS = s;
    this.applyMatrix();
    this.offsets = [];
    this.calibrated = false;
  }

  private applyMatrix() {
    const a = this.anchor!;
    const L = a.linear;
    const t = a.translation;
    // three = S · (L·ecef + t), S: (x, y, z) → (x, z, −y); plus the calibrated vertical offset on three's y
    this.root.matrix.set(
      L[0], L[1], L[2], t[0],
      L[6], L[7], L[8], t[2] + this.verticalOffset,
      -L[3], -L[4], -L[5], -t[1],
      0, 0, 0, 1,
    );
    this.root.matrixWorldNeedsUpdate = true;
  }

  /**
   * Vertical calibration: cast rays down at road samples around the anchor; the median of (road height − tile hit)
   * absorbs the geoid undulation and dataset bias. Roofs/trees over the road are rejected by the median.
   */
  private calibrate(s: number) {
    const hits: number[] = [];
    this.root.updateMatrixWorld(true);
    for (let d = -60; d <= 60; d += 15) {
      const p = poseAt(this.route, Math.max(0, s + d));
      this.raycaster.set(new THREE.Vector3(p.x, p.z + 400, -p.y), new THREE.Vector3(0, -1, 0));
      (this.raycaster as THREE.Raycaster & { firstHitOnly?: boolean }).firstHitOnly = true;
      const hit = this.raycaster.intersectObject(this.tiles.group, true)[0];
      if (hit) hits.push(p.z - hit.point.y);
    }
    console.info("[photoreal] calibrate", { hits: hits.length, offset: this.verticalOffset.toFixed(2), sample: hits.slice(0, 3).map((h) => h.toFixed(2)) });
    if (hits.length >= 4) {
      this.offsets.push(...hits);
      const sorted = [...this.offsets].sort((a, b) => a - b);
      const med = sorted[Math.floor(sorted.length / 2)];
      this.verticalOffset += med;
      this.applyMatrix();
      this.offsets = [];
      if (Math.abs(med) < 0.25) this.calibrated = true;
    }
  }

  update(s: number) {
    if (!this.anchor || Math.abs(s - this.anchorS) > 750) this.anchorAt(s);
    const now = performance.now();
    if (!this.calibrated && now - this.lastCal > 400) {
      this.lastCal = now;
      this.calibrate(s);
    }
    this.tiles.update();
  }

  /** Data attributions that must stay visible (Google logo + per-tile copyrights). */
  attributions(): string {
    const list = this.tiles.getAttributions() as { type: string; value: string }[];
    return list.filter((a) => a.type === "string").map((a) => a.value).join("; ");
  }

  dispose() {
    this.tiles.dispose();
    this.root.removeFromParent();
  }
}
