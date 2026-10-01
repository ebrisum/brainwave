import * as THREE from "three";
import { Sky } from "three/examples/jsm/objects/Sky.js";

/** Physical sky with the true sun, sun light with a shadow box following the rider, fog from visibility, rain. */
export class SkyWeather {
  sky = new Sky();
  sun = new THREE.DirectionalLight(0xffffff, 3);
  hemi = new THREE.HemisphereLight(0xbfd8ff, 0x4a5a3a, 0.9);
  fog = new THREE.FogExp2(0xcfd8e0, 0.00012);
  private rain?: THREE.Points;
  private rainVel?: Float32Array;
  sunDir = new THREE.Vector3(0, 1, 0);

  constructor(private scene: THREE.Scene, shadowMap: number) {
    this.sky.scale.setScalar(450000);
    const u = this.sky.material.uniforms;
    u.turbidity.value = 4;
    u.rayleigh.value = 1.5;
    u.mieCoefficient.value = 0.005;
    u.mieDirectionalG.value = 0.8;
    scene.add(this.sky, this.sun, this.sun.target, this.hemi);
    scene.fog = this.fog;
    this.sun.castShadow = shadowMap > 0;
    if (shadowMap > 0) {
      this.sun.shadow.mapSize.set(shadowMap, shadowMap);
      const c = this.sun.shadow.camera;
      c.left = -60; c.right = 60; c.top = 60; c.bottom = -60; c.near = 1; c.far = 600;
      this.sun.shadow.bias = -0.0004;
      this.sun.shadow.normalBias = 0.04;
    }
  }

  /** elevation/azimuth in degrees (azimuth clockwise from north); cloud 0..1; visibility m; rain mm/h. */
  set(elevationDeg: number, azimuthDeg: number, cloud: number, visibilityM: number, rainMmH: number) {
    const phi = THREE.MathUtils.degToRad(90 - Math.max(elevationDeg, -5));
    const theta = THREE.MathUtils.degToRad(azimuthDeg);
    // three.js: north = −z, east = +x
    this.sunDir.setFromSphericalCoords(1, phi, theta).set(Math.sin(theta) * Math.sin(phi), Math.cos(phi), -Math.cos(theta) * Math.sin(phi));
    this.sky.material.uniforms.sunPosition.value.copy(this.sunDir);
    this.sky.material.uniforms.turbidity.value = 3 + 12 * cloud;
    this.sky.material.uniforms.rayleigh.value = 1.5 + cloud;
    const day = THREE.MathUtils.clamp((elevationDeg + 4) / 14, 0, 1);
    this.sun.intensity = 3.2 * day * (1 - 0.75 * cloud);
    this.hemi.intensity = 0.25 + 0.9 * day;
    const grey = new THREE.Color().setHSL(0.58, 0.15 * (1 - cloud), 0.55 + 0.25 * day * (1 - cloud * 0.5));
    this.fog.color.copy(grey);
    this.fog.density = THREE.MathUtils.clamp(2.5 / Math.max(visibilityM, 300), 0.00004, 0.006);
    this.setRain(rainMmH);
  }

  followRider(p: THREE.Vector3) {
    this.sun.position.copy(p).addScaledVector(this.sunDir, 300);
    this.sun.target.position.copy(p);
    if (this.rain) this.rain.position.copy(p);
  }

  private setRain(mmH: number) {
    const n = Math.min(Math.round(mmH * 6000), 20000);
    if (n === 0) {
      if (this.rain) { this.rain.geometry.dispose(); this.rain.removeFromParent(); this.rain = undefined; }
      return;
    }
    if (this.rain && this.rain.geometry.getAttribute("position").count === n) return;
    if (this.rain) { this.rain.geometry.dispose(); this.rain.removeFromParent(); }
    const pos = new Float32Array(n * 3);
    this.rainVel = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 80;
      pos[i * 3 + 1] = Math.random() * 40;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 80;
      this.rainVel[i] = 8 + Math.random() * 3;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.rain = new THREE.Points(g, new THREE.PointsMaterial({ color: 0xaab4c0, size: 0.06, transparent: true, opacity: 0.6, depthWrite: false }));
    this.rain.frustumCulled = false;
    this.scene.add(this.rain);
  }

  /** Animate rain; wind (three.js xz, m/s) slants it. */
  update(dt: number, windX: number, windZ: number) {
    if (!this.rain || !this.rainVel) return;
    const a = this.rain.geometry.getAttribute("position") as THREE.BufferAttribute;
    for (let i = 0; i < a.count; i++) {
      let y = a.getY(i) - this.rainVel[i] * dt;
      let x = a.getX(i) + windX * dt;
      let z = a.getZ(i) + windZ * dt;
      if (y < 0) { y += 40; x = (Math.random() - 0.5) * 80; z = (Math.random() - 0.5) * 80; }
      a.setXYZ(i, x, y, z);
    }
    a.needsUpdate = true;
  }
}
