import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";
import { Fetcher, GameIndex, GameInstances, KitMaterial, Manifest } from "@rideprep/course-format";
import { disposeObject, enu } from "./util";

/**
 * Game-art world (`gpx2course game`, docs/GAME_ART.md): textured terrain/road/building chunks streamed ahead of the
 * rider, regional art-kit instances (trees, vine rows, props) as InstancedMeshes with a distance LOD, and a far field
 * whose corridor fills hide while the near chunk is loaded. Chunk materials are kit ids → shared kit materials
 * (UVs in metres, repeat = 1/tileM).
 */
export class GameWorld {
  group = new THREE.Group();
  aheadM = 2500;
  behindM = 400;
  lod1DistanceM = 320;
  private loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  private mats = new Map<string, THREE.Material>();
  private assets = new Map<string, THREE.Mesh[]>();
  private loaded = new Map<number, { root: THREE.Group; lod0: THREE.Group; lod1: THREE.Group; centre: THREE.Vector3 }>();
  private loading = new Set<number>();
  private farFill = new Map<number, THREE.Object3D>();
  private textures: THREE.Texture[] = [];

  private constructor(private index: GameIndex, private fetch: Fetcher, private renderer?: THREE.WebGLRenderer, private camera?: THREE.Camera) {}

  /** `renderer`/`camera`: streamed chunks are shader-compiled asynchronously before they enter the scene, so loading
   * never stalls the main thread (which also feeds sensor power to the physics). */
  static async create(manifest: Manifest, fetch: Fetcher, anisotropy = 8, renderer?: THREE.WebGLRenderer,
                      camera?: THREE.Camera): Promise<GameWorld | undefined> {
    if (!manifest.game) return undefined;
    const index = JSON.parse(new TextDecoder().decode(await fetch(manifest.game.index))) as GameIndex;
    const gw = new GameWorld(index, fetch, renderer, camera);
    await gw.loadKit(anisotropy);
    await gw.loadFar();
    return gw;
  }

  /** Sky/ground gradient as image-based light: the kit's PBR materials need ambient beyond the hemisphere light. */
  static environment(renderer: THREE.WebGLRenderer): THREE.Texture {
    const scene = new THREE.Scene();
    const geo = new THREE.SphereGeometry(10, 32, 16);
    const mat = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      vertexShader: "varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      fragmentShader: `varying vec3 vP; void main(){ float h = normalize(vP).y;
        vec3 sky = mix(vec3(0.80, 0.86, 0.92), vec3(0.42, 0.60, 0.88), smoothstep(0.0, 0.6, h));
        vec3 ground = mix(vec3(0.46, 0.44, 0.34), vec3(0.30, 0.31, 0.22), smoothstep(0.0, -0.5, h));
        gl_FragColor = vec4(h >= 0.0 ? sky : ground, 1.0); }`,
    });
    scene.add(new THREE.Mesh(geo, mat));
    const pmrem = new THREE.PMREMGenerator(renderer);
    const tex = pmrem.fromScene(scene, 0.02).texture;
    pmrem.dispose();
    geo.dispose();
    mat.dispose();
    return tex;
  }

  get label() {
    return this.index.kit.label;
  }

  private async texture(file: string, srgb: boolean, anisotropy: number): Promise<THREE.Texture> {
    const buf = await this.fetch(`${this.index.kit.dir}/textures/${file}`);
    const bmp = await createImageBitmap(new Blob([buf]), { imageOrientation: "none" });
    const t = new THREE.Texture(bmp);
    t.flipY = false; // glTF UV convention (same as the chunk meshes)
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    t.anisotropy = anisotropy;
    t.needsUpdate = true;
    this.textures.push(t);
    return t;
  }

  private async loadKit(anisotropy: number) {
    const doc = JSON.parse(new TextDecoder().decode(await this.fetch(this.index.kit.materials))) as { materials: Record<string, KitMaterial> };
    await Promise.all(Object.entries(doc.materials).map(async ([id, m]) => {
      // Foliage cards: no specular (grazing crown normals would rim-light white under PBR Fresnel)
      // Calm water (roughness < 0.15): grazing-angle Fresnel on a bright horizon gradient reads as snow, so water gets
      // a subdued, sky-tinted specular instead of a full dielectric mirror.
      const water = m.alphaCutoff == null && (m.roughness ?? 1) < 0.15;
      const mat: THREE.MeshStandardMaterial | THREE.MeshLambertMaterial = m.alphaCutoff != null
        ? new THREE.MeshLambertMaterial({ name: id })
        : water
          ? new THREE.MeshPhysicalMaterial({ name: id, roughness: 0.18, metalness: 0, specularIntensity: 0.35, specularColor: new THREE.Color(0x8fa9bb),
                                             envMapIntensity: 0.55 })
          : new THREE.MeshStandardMaterial({ name: id, roughness: m.roughness ?? 0.9, metalness: m.metallic ?? 0 });
      const [sx, sy] = m.tileM == null ? [1, 1] : Array.isArray(m.tileM) ? m.tileM : [m.tileM, m.tileM];
      if (m.albedo) {
        mat.map = await this.texture(m.albedo, true, anisotropy);
        mat.map.repeat.set(1 / sx, 1 / sy);
      } else if (m.color) {
        mat.color.set(m.color);
      }
      if (m.normal && mat instanceof THREE.MeshStandardMaterial) {
        mat.normalMap = await this.texture(m.normal, false, anisotropy);
        mat.normalMap.repeat.set(1 / sx, 1 / sy);
        mat.normalScale.set(0.8, 0.8);
      }
      if (m.alphaCutoff != null) {
        mat.alphaTest = m.alphaCutoff;
        mat.side = THREE.DoubleSide;
        // Foliage cards carry outward "crown" normals from the kit: keep them on back faces (no double-sided flip)
        mat.onBeforeCompile = (sh) => {
          sh.fragmentShader = sh.fragmentShader.replace("#include <normal_fragment_begin>",
            THREE.ShaderChunk.normal_fragment_begin.replace("normal *= faceDirection;", ""));
        };
      } else if (m.alpha != null) {
        mat.transparent = true;
        mat.opacity = m.alpha;
        mat.depthWrite = false;
      }
      if (m.emissive && m.color) mat.emissive.set(m.color).multiplyScalar(m.emissive);
      this.mats.set(id, mat);
    }));
    // Kit meshes: one node per asset (`<asset>` and `<asset>__lod1`); primitives become separate meshes
    const gltf = await this.loader.parseAsync(await this.fetch(this.index.kit.glb), "");
    for (const node of gltf.scene.children) {
      const meshes: THREE.Mesh[] = [];
      node.updateMatrixWorld(true);
      node.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        const g = m.geometry.clone().applyMatrix4(m.matrixWorld);
        meshes.push(new THREE.Mesh(g, this.kitMaterial(m.material as THREE.Material)));
      });
      this.assets.set(node.name, meshes);
    }
  }

  /** Kit material by glTF material name ("asphalt", "leaf_pine.001" → "leaf_pine"). */
  private kitMaterial(m: THREE.Material): THREE.Material {
    return this.mats.get(m.name.replace(/\.\d+$/, "")) ?? m;
  }

  private bindMaterials(root: THREE.Object3D) {
    root.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!m.isMesh) return;
      m.material = Array.isArray(m.material) ? m.material.map((x) => this.kitMaterial(x)) : this.kitMaterial(m.material);
      m.receiveShadow = true;
      m.castShadow = /^buildings|^road/.test(m.name);
    });
  }

  private async loadFar() {
    const gltf = await this.loader.parseAsync(await this.fetch(this.index.far), "");
    this.bindMaterials(gltf.scene);
    gltf.scene.traverse((o) => {
      const mm = o.name.match(/^farfill_(\d+)/);
      if (mm) this.farFill.set(Number(mm[1]), o);
    });
    gltf.scene.position.copy(enu(0, 0, 0));
    this.group.add(gltf.scene);
  }

  update(s: number, camera: THREE.Vector3) {
    // Spatial streaming: every chunk whose terrain lies within `aheadM` of the camera (out-and-back courses share land
    // between legs, so ride order alone leaves holes), plus the next stretch in ride order for prefetching.
    const ce = camera.x, cn = -camera.z;
    const ids = new Set<number>();
    const queue: { c: GameIndex["chunks"][number]; d: number }[] = [];
    for (const c of this.index.chunks) {
      const b = c.bounds;
      const d = b ? Math.hypot(Math.max(b[0] - ce, 0, ce - b[2]), Math.max(b[1] - cn, 0, cn - b[3]))
        : Math.hypot(c.origin[0] - ce, c.origin[1] - cn);
      if (d < this.aheadM || (c.sEnd > s - this.behindM && c.sStart < s + this.aheadM)) {
        ids.add(c.id);
        queue.push({ c, d });
      }
    }
    queue.sort((a, b) => a.d - b.d); // nearest first
    for (const { c } of queue) {
      if (this.loaded.has(c.id) || this.loading.has(c.id) || this.loading.size >= 3) continue;
      this.loading.add(c.id);
      this.load(c).catch((e) => console.warn("game chunk", c.id, e)).finally(() => this.loading.delete(c.id));
    }
    for (const [id, ch] of this.loaded) {
      if (!ids.has(id)) {
        this.group.remove(ch.root);
        disposeChunk(ch.root);
        this.loaded.delete(id);
        const f = this.farFill.get(id);
        if (f) f.visible = true;
        continue;
      }
      const near = ch.centre.distanceTo(camera) < this.lod1DistanceM;
      ch.lod0.visible = near;
      ch.lod1.visible = !near;
    }
  }

  private async load(c: GameIndex["chunks"][number]) {
    const [gltf, instBuf] = await Promise.all([this.fetch(c.glb).then((b) => this.loader.parseAsync(b, "")), this.fetch(c.instances)]);
    const inst = JSON.parse(new TextDecoder().decode(instBuf)) as GameInstances;
    const root = new THREE.Group();
    root.name = `game_${c.id}`;
    root.position.copy(enu(c.origin[0], c.origin[1], c.origin[2]));
    this.bindMaterials(gltf.scene);
    root.add(gltf.scene);
    const lod0 = new THREE.Group();
    const lod1 = new THREE.Group();
    const m4 = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const up = new THREE.Vector3(0, 1, 0);
    const p = new THREE.Vector3();
    const sc = new THREE.Vector3();
    for (const [asset, rows] of Object.entries(inst.instances)) {
      for (const [lodName, target] of [[asset, lod0], [`${asset}__lod1`, lod1]] as const) {
        const parts = this.assets.get(lodName) ?? this.assets.get(asset);
        if (!parts) continue;
        for (const part of parts) {
          const im = new THREE.InstancedMesh(part.geometry, part.material, rows.length);
          rows.forEach(([x, y, z, rot, s], k) => {
            // ENU (x, y, z) → three (x, z, −y); a CCW rotation about Up is the same angle about +Y
            m4.compose(p.set(x, z, -y), q.setFromAxisAngle(up, rot), sc.set(s, s, s));
            im.setMatrixAt(k, m4);
          });
          im.instanceMatrix.needsUpdate = true;
          im.computeBoundingSphere();
          im.castShadow = target === lod0 && /^tree|^campanile|^vine/.test(asset);
          im.receiveShadow = false;
          target.add(im);
        }
      }
    }
    root.add(lod0, lod1);
    if (this.renderer && this.camera) {
      // Compile both LOD variants off the critical path (KHR_parallel_shader_compile where available)
      try { await this.renderer.compileAsync(root, this.camera, (this.group.parent as THREE.Scene | null) ?? undefined); } catch { /* compile on first draw */ }
    }
    lod1.visible = false;
    const centre = root.position.clone();
    this.group.add(root);
    this.loaded.set(c.id, { root, lod0, lod1, centre });
    const f = this.farFill.get(c.id);
    if (f) f.visible = false;
  }

  dispose() {
    for (const ch of this.loaded.values()) disposeChunk(ch.root);
    this.loaded.clear();
    disposeObject(this.group);
    this.mats.forEach((m) => m.dispose());
    this.textures.forEach((t) => t.dispose());
    this.assets.forEach((ms) => ms.forEach((m) => m.geometry.dispose()));
  }
}

/** Chunk geometry only — materials and instance geometries are shared kit resources. */
function disposeChunk(root: THREE.Object3D) {
  root.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh && !(m as THREE.InstancedMesh).isInstancedMesh) m.geometry?.dispose();
    if ((m as THREE.InstancedMesh).isInstancedMesh) (m as THREE.InstancedMesh).dispose();
  });
}
