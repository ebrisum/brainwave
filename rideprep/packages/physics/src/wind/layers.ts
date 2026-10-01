/**
 * Precomputed direction-dependent wind layers (wind.bin).
 * Layout: uint8 values (factor × 100), layer-major: offset = (layer·count + sample)·bins + dirBin.
 * Direction bin d covers the meteorological FROM-direction d·(360/bins) ± half a bin.
 */
export const WIND_LAYERS = ["fRough", "shelter", "topo", "channel"] as const;
export type WindLayerName = (typeof WIND_LAYERS)[number];

export interface WindFactors {
  fRough: number;
  shelter: number;
  topo: number;
  channel: number;
}

export class WindLayers {
  constructor(
    public readonly data: Uint8Array,
    public readonly count: number,
    public readonly spacingM = 10,
    public readonly bins = 16,
    public readonly layers: readonly WindLayerName[] = WIND_LAYERS,
  ) {
    if (data.length !== layers.length * count * bins) throw new Error(`wind.bin size mismatch: ${data.length}`);
  }

  /** Uniform layers (no terrain info): open grassland, no shelter. */
  static uniform(count: number, f: Partial<WindFactors> = {}, spacingM = 10, bins = 16): WindLayers {
    const vals = { fRough: 0.635, shelter: 1, topo: 1, channel: 1, ...f };
    const data = new Uint8Array(WIND_LAYERS.length * count * bins);
    WIND_LAYERS.forEach((name, l) => data.fill(Math.round(vals[name] * 100), l * count * bins, (l + 1) * count * bins));
    return new WindLayers(data, count, spacingM, bins);
  }

  private raw(layer: number, i: number, d: number): number {
    return this.data[(layer * this.count + i) * this.bins + d] / 100;
  }

  /** Factors at distance s for a FROM-direction, interpolated between the two nearest bins and samples. */
  factors(s: number, dirDeg: number, out?: WindFactors): WindFactors {
    const o = out ?? ({} as WindFactors);
    const binW = 360 / this.bins;
    const fd = ((((dirDeg % 360) + 360) % 360) / binW) % this.bins;
    const d0 = Math.floor(fd) % this.bins;
    const d1 = (d0 + 1) % this.bins;
    const td = fd - Math.floor(fd);
    const fi = Math.min(Math.max(s / this.spacingM, 0), this.count - 1);
    const i0 = Math.floor(fi);
    const i1 = Math.min(i0 + 1, this.count - 1);
    const ts = fi - i0;
    for (let l = 0; l < this.layers.length; l++) {
      const a = this.raw(l, i0, d0) * (1 - td) + this.raw(l, i0, d1) * td;
      const b = this.raw(l, i1, d0) * (1 - td) + this.raw(l, i1, d1) * td;
      (o as unknown as Record<string, number>)[this.layers[l]] = a + (b - a) * ts;
    }
    return o;
  }
}
