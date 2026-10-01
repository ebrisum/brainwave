"""report.html: route map, data sources per zone, warnings, stage timings, attribution. Self-contained, no external assets."""
from __future__ import annotations

import html

import numpy as np

from .stages.common import load_route

CSS = """
:root{--bg:#f7f7f5;--fg:#1d1f21;--muted:#666;--card:#fff;--line:#e2e2de;--accent:#2f6fb2;--warn:#b26a00}
@media (prefers-color-scheme: dark){:root{--bg:#141517;--fg:#e8e8e6;--muted:#9a9a98;--card:#1d1f22;--line:#2c2f33;--accent:#6aa6e8;--warn:#e0a040}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:24px 16px}
main{max-width:1100px;margin:0 auto}h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}
.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
.kpi{font-size:22px;font-variant-numeric:tabular-nums}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}
svg{width:100%;height:auto;display:block}.warn{color:var(--warn)}
"""


def _svg_map(x, y, climbs, s) -> str:
    minx, maxx, miny, maxy = x.min(), x.max(), y.min(), y.max()
    span = max(maxx - minx, maxy - miny, 1)
    W = 600
    sx = lambda v: (v - minx) / span * (W - 20) + 10  # noqa: E731
    sy = lambda v: (maxy - v) / span * (W - 20) + 10  # noqa: E731
    step = max(1, len(x) // 1500)
    pts = " ".join(f"{sx(a):.1f},{sy(b):.1f}" for a, b in zip(x[::step], y[::step]))
    h = int((maxy - miny) / span * (W - 20) + 20)
    out = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="Route map"><polyline points="{pts}" fill="none" stroke="var(--accent)" stroke-width="2"/>']
    for c in climbs:
        a, b = np.searchsorted(s, c["sStart"]), np.searchsorted(s, c["sEnd"])
        seg = " ".join(f"{sx(p):.1f},{sy(q):.1f}" for p, q in zip(x[a:b:step], y[a:b:step]))
        out.append(f'<polyline points="{seg}" fill="none" stroke="#d0402b" stroke-width="3.5"/>')
    out.append(f'<circle cx="{sx(x[0]):.1f}" cy="{sy(y[0]):.1f}" r="5" fill="#2a9d55"/></svg>')
    return "".join(out)


def _svg_profile(s, z) -> str:
    W, H = 1000, 180
    step = max(1, len(s) // 1000)
    s, z = s[::step], z[::step]
    zmin, zmax = z.min(), max(z.max(), z.min() + 10)
    px = lambda v: v / s[-1] * W  # noqa: E731
    py = lambda v: H - 10 - (v - zmin) / (zmax - zmin) * (H - 30)  # noqa: E731
    pts = " ".join(f"{px(a):.1f},{py(b):.1f}" for a, b in zip(s, z))
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Elevation profile"><polygon points="0,{H} {pts} {W},{H}" fill="var(--accent)" '
            f'fill-opacity="0.25" stroke="var(--accent)" stroke-width="1.5"/><text x="4" y="14" font-size="12" fill="currentColor">{zmax:.0f} m</text>'
            f'<text x="4" y="{H - 14}" font-size="12" fill="currentColor">{zmin:.0f} m</text></svg>')


def write_report(ctx, m: dict) -> None:
    r = load_route(ctx)
    e = html.escape
    st = m["stats"]
    seg = m["segments"]
    rows_src = []
    for stage, srcs in ctx.state.get("sources", {}).items():
        for kind, v in srcs.items():
            res = f"{v['resolution_m']} m" if v.get("resolution_m") else "—"
            rows_src.append(f"<tr><td>{e(stage)}</td><td>{e(kind)}</td><td>{e(v['name'])}</td><td>{res}</td><td>{e(v['license'])}</td></tr>")
    zones = "".join(f"<tr><td>{e(z['provider'])}</td><td>{z['share']:.0%}</td><td>{z['resolution_m'] or '—'}</td></tr>" for z in m.get("elevationSources", []))
    warns = "".join(f"<tr><td>{e(w['stage'])}</td><td class='warn'>{e(w['code'])}</td><td>{e(w['message'])}</td></tr>" for w in m["warnings"]) or "<tr><td colspan=3>None</td></tr>"
    timing = "".join(f"<tr><td>{e(k)}</td><td>{v.get('status')}</td><td>{v.get('duration_s', 0):.2f} s</td></tr>" for k, v in ctx.state.get("stages", {}).items())
    climbs = "".join(f"<tr><td>{c['sStart'] / 1000:.2f}</td><td>{c['lengthM'] / 1000:.2f} km</td><td>{c['avgGradePct']:.1f}%</td><td>{c['maxGradePct']:.1f}%</td>"
                     f"<td>{c['gainM']:.0f} m</td><td>{c['category']}</td></tr>" for c in seg["climbs"]) or "<tr><td colspan=6>No climbs ≥ 500 m at ≥ 3 %</td></tr>"
    corners = sum(1 for c in seg["corners"])
    baro = m.get("barometric")
    baro_html = (f"<p>Input file ascent {baro['inputAscentM']:.0f} m vs DEM {baro['demAscentM']:.0f} m (difference {baro['differenceM']:+.0f} m).</p>" if baro else "")
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Course Build Report</title><style>{CSS}</style></head><body><main>
<h1>{e(m['name'])}</h1><div class="muted">{e(m['courseId'])} · pipeline {e(m['pipelineVersion'])} · tier {e(m['tier'])}</div>
<h2>Overview</h2><div class="grid">
<div class="card"><div class="muted">Distance</div><div class="kpi">{st['distanceM'] / 1000:.1f} km</div></div>
<div class="card"><div class="muted">Ascent</div><div class="kpi">{st['ascentM']:.0f} m</div></div>
<div class="card"><div class="muted">Max grade</div><div class="kpi">{st['maxGradePct']:.1f} %</div></div>
<div class="card"><div class="muted">Climbs</div><div class="kpi">{len(seg['climbs'])}</div></div>
<div class="card"><div class="muted">Technical corners</div><div class="kpi">{corners}</div></div>
<div class="card"><div class="muted">Laps</div><div class="kpi">{st['laps']}</div></div></div>
<h2>Route map</h2><div class="card">{_svg_map(r['x'], r['y'], seg['climbs'], r['s'])}<div class="muted">Climbs in red; start in green.</div></div>
<h2>Elevation</h2><div class="card">{_svg_profile(r['s'], r['z'])}{baro_html}</div>
<h2>Climbs</h2><div class="card"><table><tr><th>Start km</th><th>Length</th><th>Avg</th><th>Max (100 m)</th><th>Gain</th><th>Cat</th></tr>{climbs}</table></div>
<h2>Data sources</h2><div class="card"><table><tr><th>Stage</th><th>Kind</th><th>Provider</th><th>Resolution</th><th>Licence</th></tr>{''.join(rows_src)}</table>
<h3>Elevation per zone</h3><table><tr><th>Provider</th><th>Share of route</th><th>Resolution (m)</th></tr>{zones}</table></div>
<h2>Warnings</h2><div class="card"><table><tr><th>Stage</th><th>Code</th><th>Message</th></tr>{warns}</table></div>
<h2>Stage timings</h2><div class="card"><table><tr><th>Stage</th><th>Status</th><th>Duration</th></tr>{timing}</table></div>
<h2>Attribution</h2><div class="card"><ul>{''.join(f'<li>{e(a)}</li>' for a in m['attribution'])}</ul></div>
</main></body></html>"""
    ctx.write_bytes("report.html", doc.encode())
