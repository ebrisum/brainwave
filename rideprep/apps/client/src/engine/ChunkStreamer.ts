import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";
import { ChunkRef, Fetcher } from "@rideprep/course-format";
import { disposeObject, enu } from "./util";

/**
 * Streams baked full-tier chunks (glTF, 3 LODs) 3 km ahead / 500 m behind the rider, in ride order. When a chunk is in,
 * the Quick-tier road and near buildings for that range are hidden (`onSwap`).
 */
export class ChunkStreamer {
  group = new THREE.Group();
  aheadM = 3000;
  behindM = 500;
  private loaded = new Map<number, THREE.LOD>();
  private loading = new Set<number>();
  private loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  private maxParallel = 3;

  constructor(private chunks: ChunkRef[], private fetch: Fetcher, private onSwap: (id: number, baked: boolean) => void) {}

  update(s: number) {
    const want = this.chunks.filter((c) => c.status === "baked" && c.lod.length && c.sEnd > s - this.behindM && c.sStart < s + this.aheadM)
      .sort((a, b) => a.sStart - b.sStart);
    const wantIds = new Set(want.map((c) => c.id));
    for (const c of want) {
      if (this.loaded.has(c.id) || this.loading.has(c.id) || this.loading.size >= this.maxParallel) continue;
      this.loading.add(c.id);
      this.load(c).catch((e) => console.warn("chunk", c.id, e)).finally(() => this.loading.delete(c.id));
    }
    for (const [id, lod] of this.loaded) {
      if (!wantIds.has(id)) {
        disposeObject(lod);
        this.loaded.delete(id);
        this.onSwap(id, false);
      }
    }
  }

  /** Refresh chunk statuses from the server while the bake is still running (progressive streaming). */
  setChunks(chunks: ChunkRef[]) {
    this.chunks = chunks;
  }

  private async load(c: ChunkRef) {
    const parse = async (path: string) => {
      const buf = await this.fetch(path);
      const gltf = await this.loader.parseAsync(buf, "");
      gltf.scene.traverse((o) => {
        const m = o as THREE.Mesh;
        if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; }
      });
      return gltf.scene;
    };
    const scenes = await Promise.all(c.lod.map(parse));
    const lod = new THREE.LOD();
    const dist = c.lodDistancesM ?? [150, 600];
    scenes.forEach((sc, i) => lod.addLevel(sc, i === 0 ? 0 : dist[i - 1]));
    const o = c.origin ?? [0, 0, 0];
    lod.position.copy(enu(o[0], o[1], o[2]));
    lod.name = `chunk_${c.id}`;
    this.group.add(lod);
    this.loaded.set(c.id, lod);
    this.onSwap(c.id, true);
  }

  dispose() {
    disposeObject(this.group);
  }
}
