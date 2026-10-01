import { compass } from "../units";

/** Wind rose from climatology.json: 16 directions × speed bins, petals point to where the wind comes FROM. */
export function WindRose({ freq, speedBins, size = 220, highlightDeg }: { freq: number[][]; speedBins: number[]; size?: number; highlightDeg?: number }) {
  const c = size / 2;
  const total = freq.map((row) => row.reduce((a, b) => a + b, 0));
  const max = Math.max(...total, 1e-6);
  const colors = ["#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#08306b"];
  const petals = [];
  for (let d = 0; d < freq.length; d++) {
    let r0 = 0;
    for (let k = 0; k < freq[d].length; k++) {
      const r1 = r0 + (freq[d][k] / max) * (c - 22);
      const a0 = ((d * 22.5 - 10) * Math.PI) / 180;
      const a1 = ((d * 22.5 + 10) * Math.PI) / 180;
      const p = (r: number, a: number) => `${c + r * Math.sin(a)},${c - r * Math.cos(a)}`;
      petals.push(<polygon key={`${d}-${k}`} points={`${p(r0, a0)} ${p(r1, a0)} ${p(r1, a1)} ${p(r0, a1)}`} fill={colors[k]} stroke="rgba(0,0,0,0.25)" strokeWidth={0.5} />);
      r0 = r1;
    }
  }
  return (
    <figure className="windrose">
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label="Wind rose">
        {[0.33, 0.66, 1].map((f) => <circle key={f} cx={c} cy={c} r={f * (c - 22)} fill="none" stroke="rgba(255,255,255,0.15)" />)}
        {petals}
        {["N", "E", "S", "W"].map((l, i) => (
          <text key={l} x={c + (c - 10) * Math.sin((i * Math.PI) / 2)} y={c - (c - 10) * Math.cos((i * Math.PI) / 2) + 4} fill="currentColor" fontSize="12" textAnchor="middle">{l}</text>
        ))}
        {highlightDeg !== undefined && (
          <line x1={c} y1={c} x2={c + (c - 24) * Math.sin((highlightDeg * Math.PI) / 180)} y2={c - (c - 24) * Math.cos((highlightDeg * Math.PI) / 180)} stroke="#F0E442" strokeWidth={2} />
        )}
      </svg>
      <figcaption>
        {speedBins.map((b, k) => <span key={b}><i style={{ background: colors[k] }} />{k < speedBins.length - 1 ? `${b}–${speedBins[k + 1]}` : `>${b}`} m/s</span>)}
        {highlightDeg !== undefined && <span>modal {compass(highlightDeg)}</span>}
      </figcaption>
    </figure>
  );
}
