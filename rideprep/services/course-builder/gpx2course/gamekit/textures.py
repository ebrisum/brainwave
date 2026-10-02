"""Procedural, tileable PBR textures for regional art kits (numpy + Pillow; deterministic, no external downloads).

Every texture is generated from band-limited periodic noise (filtered in the frequency domain, so it tiles exactly)
plus simple procedural structure (tile rows, aggregate, bricks, window bays). Outputs per material:
  <id>_albedo.jpg (sRGB), <id>_normal.png (OpenGL +Y, tangent space), and a scalar roughness in materials.json.
Texture *content* is driven by a kit palette (kits/<name>.json) so other regions reuse the generators.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---- noise ------------------------------------------------------------------------------------------------------


def rng(seed) -> np.random.Generator:
    return np.random.default_rng(abs(hash(("kit", seed))) % (2**63) if not isinstance(seed, int) else seed)


def pnoise(n: int, cutoff: float, seed: int, m: int | None = None) -> np.ndarray:
    """Periodic band-limited noise in [0, 1], n×m px; cutoff = wavelength in px of the dominant detail."""
    m = m or n
    g = np.random.default_rng(seed)
    w = g.standard_normal((n, m))
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.fftfreq(m)[None, :]
    f = np.sqrt(fx**2 + fy**2)
    filt = np.exp(-((f * cutoff) ** 2))
    out = np.real(np.fft.ifft2(np.fft.fft2(w) * filt))
    out -= out.min()
    return out / max(out.max(), 1e-9)


def fbm(n: int, base: float, seed: int, octaves: int = 5, m: int | None = None) -> np.ndarray:
    acc, amp, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        acc = acc + amp * pnoise(n, base / 2**o, seed + o * 101, m)
        tot += amp
        amp *= 0.5
    return acc / tot


def normal_from_height(h: np.ndarray, strength: float) -> np.ndarray:
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength
    nz = np.ones_like(h)
    # OpenGL convention (+Y up in texture space): image rows grow downward, so flip dy
    v = np.dstack([-dx, dy, nz])
    v /= np.linalg.norm(v, axis=2, keepdims=True)
    return ((v * 0.5 + 0.5) * 255).astype(np.uint8)


def colorize(t: np.ndarray, stops: list[tuple[float, tuple[float, float, float]]]) -> np.ndarray:
    xs = np.array([s[0] for s in stops])
    cs = np.array([s[1] for s in stops], dtype=np.float64)
    out = np.empty(t.shape + (3,))
    for c in range(3):
        out[..., c] = np.interp(t, xs, cs[:, c])
    return out


def tint(rgb, factor_map):
    return np.clip(rgb * factor_map[..., None], 0, 1)


def to_u8(rgb) -> np.ndarray:
    return (np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)


def hexrgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


# ---- surfaces -----------------------------------------------------------------------------------------------------


def asphalt(n, seed, base="#4a4a48", worn=0.0):
    g = np.random.default_rng(seed)
    low = fbm(n, n / 6, seed)
    grain = g.random((n, n))
    agg = (grain > 0.82).astype(float) * g.random((n, n))
    v = 0.85 + 0.25 * (low - 0.5) + 0.18 * (grain - 0.5) + 0.35 * agg
    rgb = hexrgb(base)[None, None, :] * v[..., None]
    if worn:
        # patch repairs: darker fresh tar rectangles + crack network (Italian provincial roads)
        patches = pnoise(n, n / 5, seed + 7) > 0.8
        rgb[patches] *= 0.82
        cracks = np.zeros((n, n))
        for _ in range(int(6 * worn)):
            y, x = g.integers(0, n, 2)
            a = g.random() * math.tau
            for _ in range(int(n * 0.35)):
                a += g.normal(0, 0.35)
                x, y = (x + math.cos(a)) % n, (y + math.sin(a)) % n
                cracks[int(y), int(x)] = 1
        cracks = np.maximum(cracks, np.roll(cracks, 1, 1))
        rgb[cracks > 0] *= 0.45
    h = 0.6 * grain + 0.6 * agg + 0.3 * low
    return rgb, h, 0.88


def stucco(n, seed, color: str):
    low = fbm(n, n / 3, seed)
    mid = pnoise(n, 10, seed + 3)
    fine = np.random.default_rng(seed).random((n, n))
    v = 0.9 + 0.16 * (low - 0.5) + 0.06 * (mid - 0.5) + 0.05 * (fine - 0.5)
    rgb = hexrgb(color)[None, None, :] * v[..., None]
    # flaking: patches showing brick underneath (old Romagna houses)
    flake = (pnoise(n, n / 10, seed + 11) > 0.86)
    rgb[flake] = rgb[flake] * 0.6 + hexrgb("#9c5a3c") * 0.4
    return rgb, 0.4 * mid + 0.2 * fine + 0.6 * flake, 0.9


def facade_bay(n, seed, wall: str, shutter: str, frame: str = "#e9e2d0", ground=False):
    """One 4 m × 3 m facade bay (u: 4 m, v: 3 m) with a window, persiane (louvred shutters) and a stone sill.
    Texture is n wide × 3/4 n tall; tiles horizontally and vertically (floor after floor)."""
    W, H = n, int(n * 3 / 4)
    rgb, hgt, _ = stucco(n, seed, wall)
    rgb, hgt = rgb[:H], hgt[:H]
    px = W / 4.0  # px per metre
    cx = W / 2

    def box(x0, y0, x1, y1, col, h=0.0, noise=0.0):
        y0, y1 = int(H - y1 * px), int(H - y0 * px)  # metres from bottom → rows
        x0, x1 = int(cx + x0 * px), int(cx + x1 * px)
        sub = rgb[y0:y1, x0:x1]
        c = hexrgb(col) if isinstance(col, str) else col
        sub[:] = c * (1 + noise * (np.random.default_rng(seed + x0).random(sub.shape[:2])[..., None] - 0.5))
        hgt[y0:y1, x0:x1] = h

    if ground:
        # Ground-floor arched door/shopfront: dark opening with frame
        box(-0.75, 0.0, 0.75, 2.4, frame, 0.7)
        box(-0.62, 0.0, 0.62, 2.28, "#3a2e26", 0.1, 0.2)
        for k in range(5):
            box(-0.62 + k * 0.31, 0.0, -0.6 + k * 0.31, 2.28, "#2a211b", 0.2)
    else:
        sill_y, top_y = 0.95, 2.35
        box(-0.62, sill_y - 0.08, 0.62, sill_y, "#d8d2c4", 0.9)  # stone sill
        box(-0.5, sill_y, 0.5, top_y, frame, 0.6)  # frame
        box(-0.42, sill_y + 0.05, 0.42, top_y - 0.06, "#20262a", 0.05)  # glass (dark)
        # Persiane: two shutter leaves beside the window, horizontal louvres
        for side in (-1, 1):
            x0, x1 = (-1.0, -0.52) if side < 0 else (0.52, 1.0)
            box(x0, sill_y, x1, top_y, shutter, 0.7, 0.12)
            n_l = 16
            for k in range(n_l):
                y = sill_y + 0.06 + k * (top_y - sill_y - 0.12) / n_l
                box(x0 + 0.04, y, x1 - 0.04, y + 0.03, hexrgb(shutter) * 0.6, 0.3)
        box(-0.55, top_y, 0.55, top_y + 0.12, "#d8d2c4", 0.8)  # lintel
    # Dirt streaks under the sill and darker base (rising damp)
    streak = pnoise(W, 6, seed + 5, None)[:H] * np.linspace(0.0, 1.0, H)[:, None] ** 4
    rgb *= (1 - 0.18 * streak)[..., None]
    return rgb, hgt, 0.85


def coppi(n, seed, color="#a8553a"):
    """Romagna coppi (curved clay tiles): ~18 cm wide channels, 40 cm courses, staggered; 2 m × 2 m tile."""
    g = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n] / n * 2.0  # metres
    col_w, course = 2.0 / 11, 2.0 / 5
    ci = np.floor(x / col_w)
    fx = (x / col_w) % 1.0
    shift = (ci % 2) * course / 2
    fy = ((y + shift) / course) % 1.0
    ridge = np.sin(fx * math.pi)  # convex channel
    overlap = np.clip((fy - 0.85) / 0.15, 0, 1)  # course step
    h = ridge * (1 - 0.3 * overlap) + 0.25 * (1 - fy)
    # Per-tile colour variation, darker in valleys and at the lower edge (moss/soot)
    tile_id = (ci * 31 + np.floor((y + shift) / course) * 7).astype(int)
    var = np.random.default_rng(seed).random(4096)[tile_id % 4096]
    base = hexrgb(color)
    rgb = base[None, None, :] * (0.78 + 0.32 * var[..., None]) * (0.65 + 0.35 * ridge[..., None])
    moss = (pnoise(n, n / 8, seed + 9) > 0.7) * (1 - ridge) * 0.6
    rgb = rgb * (1 - moss[..., None]) + hexrgb("#5d5a3a") * moss[..., None]
    rgb *= (1 - 0.25 * overlap)[..., None]
    rgb *= (0.95 + 0.1 * g.random((n, n)))[..., None]
    return rgb, h, 0.8


def bricks(n, seed, color="#a2533a", mortar="#cfc3ad"):
    y, x = np.mgrid[0:n, 0:n] / n * 1.2  # 1.2 m tile; bricks 25 × 6 cm (Italian mattoni) + 1 cm joints
    row = np.floor(y / 0.06)
    xs = x + (row % 2) * 0.13
    fx, fy = (xs / 0.26) % 1.0, (y / 0.06) % 1.0
    joint = (fx < 0.04) | (fy < 0.15)
    bid = (np.floor(xs / 0.26) * 13 + row * 7).astype(int) % 4096
    var = np.random.default_rng(seed).random(4096)[bid]
    rgb = hexrgb(color) * (0.75 + 0.4 * var[..., None])
    rgb = rgb * (0.9 + 0.2 * pnoise(n, n / 4, seed)[..., None])
    rgb[joint] = hexrgb(mortar) * 0.9
    return rgb, (~joint).astype(float) * 0.8 + 0.2 * pnoise(n, 6, seed + 1), 0.9


def setts(n, seed, color="#7c5f55"):
    """Porphyry setts (cubetti di porfido) laid in arcs — Italian town-centre paving; 2 m tile, ~10 cm stones."""
    y, x = np.mgrid[0:n, 0:n] / n * 2.0
    r = np.hypot(x - 1.0, (y % 1.0) - 1.0)  # concentric arcs, one fan per metre
    ring = np.floor(r / 0.1)
    ang = np.arctan2((y % 1.0) - 1.0, x - 1.0) * np.maximum(r, 0.1) / 0.1
    fr, fa = (r / 0.1) % 1.0, ang % 1.0
    joint = (fr < 0.12) | (fa < 0.12)
    sid = (ring * 131 + np.floor(ang) * 17).astype(int) % 4096
    var = np.random.default_rng(seed).random(4096)[sid]
    rgb = hexrgb(color) * (0.7 + 0.5 * var[..., None])
    rgb[joint] = hexrgb("#4a443d")
    return rgb, (~joint).astype(float) * 0.7 + 0.3 * var, 0.85


def ground(n, seed, stops, detail=6.0, rough=0.95, rows: float = 0.0, row_dark=0.75):
    t = 0.6 * fbm(n, n / 4, seed) + 0.4 * pnoise(n, detail, seed + 2)
    rgb = colorize(t, stops)
    h = t
    if rows:
        y = np.arange(n)[:, None] / n
        furrow = 0.5 + 0.5 * np.sin(y * rows * math.tau)
        rgb = rgb * (row_dark + (1 - row_dark) * furrow[..., None])
        h = 0.5 * h + 0.5 * furrow
    return rgb, h, rough


def water(n, seed, color, shallow):
    t = fbm(n, n / 3, seed)
    rgb = hexrgb(color) * (1 - t[..., None] * 0.25) + hexrgb(shallow) * (t[..., None] * 0.25)
    ripples = pnoise(n, 5, seed + 4)
    return rgb, ripples * 0.4, 0.08


# ---- cards (alpha) ------------------------------------------------------------------------------------------------


def leaf_card(n, seed, color: str, kind: str):
    """Foliage cluster card with alpha (RGBA): a ragged clump of leaves/needles that fills most of the card, darker
    towards the centre (self-shadowing), so crowns built from crossed cards read as dense, irregular foliage."""
    g = np.random.default_rng(seed)
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    base = hexrgb(color)
    # Ragged silhouette: radius threshold modulated by angular noise
    lobes = g.normal(0, 1, 9)
    count = {"broadleaf": 2600, "needle": 5200, "vine": 900, "olive": 3000}[kind]
    for _ in range(count):
        a = g.random() * math.tau
        rmax = 0.47 * (0.78 + 0.1 * sum(lobes[k] * math.sin((k + 2) * a + k) for k in range(len(lobes))) / 3)
        r = (g.random() ** 0.6) * rmax * n
        x, y = n / 2 + r * math.cos(a), n / 2 + r * math.sin(a)
        depth = r / max(rmax * n, 1)
        shade = (0.45 + 0.55 * depth) * (0.75 + 0.45 * g.random()) * (1.05 - 0.25 * (y / n))
        c = tuple(int(v) for v in np.clip(base * shade * 255, 0, 255)) + (255,)
        if kind == "needle":
            L = n * 0.035
            b = g.random() * math.tau
            d.line([(x, y), (x + L * math.cos(b), y + L * math.sin(b))], fill=c, width=max(1, n // 200))
        elif kind == "olive":
            L, b = n * 0.022, g.random() * math.tau
            dx, dy = math.cos(b) * L, math.sin(b) * L
            d.line([(x - dx, y - dy), (x + dx, y + dy)], fill=c, width=max(2, n // 110))
            if g.random() < 0.35:
                c2 = tuple(int(v) for v in np.clip(hexrgb("#a3ad97") * shade * 255, 0, 255)) + (255,)  # silver undersides
                d.line([(x - dx * 0.7, y - dy * 0.7), (x + dx * 0.7, y + dy * 0.7)], fill=c2, width=max(1, n // 160))
        else:
            s = n * (0.018 if kind == "broadleaf" else 0.04)
            b = g.random() * math.tau
            pts = [(x + s * math.cos(b + t) * (1.0 if k % 2 == 0 else 0.55), y + s * math.sin(b + t) * (1.0 if k % 2 == 0 else 0.55))
                   for k, t in enumerate(np.linspace(0, math.tau, 7)[:-1])]
            d.polygon(pts, fill=c)
            if kind == "vine" and g.random() < 0.05:  # Sangiovese bunches in September
                gx, gy = x + g.normal(0, s), y + s
                for _ in range(18):
                    ox, oy = g.normal(0, s * 0.28), g.random() * s * 1.4
                    d.ellipse([gx + ox - s * 0.13, gy + oy - s * 0.13, gx + ox + s * 0.13, gy + oy + s * 0.13], fill=(48, 26, 58, 255))
    return np.asarray(img).astype(np.float64) / 255.0


def foliage_dense(n, seed, color: str):
    """Opaque, tileable leafy texture for crown cores and hedges (no smooth 'balloon' look)."""
    g = np.random.default_rng(seed)
    base = hexrgb(color)
    rgb = np.empty((n, n, 3))
    rgb[:] = base * 0.45
    h = np.zeros((n, n))
    img = Image.fromarray(to_u8(rgb), "RGB")
    d = ImageDraw.Draw(img)
    hl = Image.fromarray(np.zeros((n, n), np.uint8), "L")
    dh = ImageDraw.Draw(hl)
    for _ in range(int(n * n / 90)):
        x, y = g.random() * n, g.random() * n
        s = n * 0.02 * (0.7 + 0.6 * g.random())
        shade = 0.55 + 0.6 * g.random()
        c = tuple(int(v) for v in np.clip(base * shade * 255, 0, 255))
        b = g.random() * math.tau
        for ox in (-n, 0, n):
            for oy in (-n, 0, n):
                if -s < x + ox < n + s and -s < y + oy < n + s:
                    pts = [(x + ox + s * math.cos(b + t) * (1.0 if k % 2 == 0 else 0.5), y + oy + s * math.sin(b + t) * (1.0 if k % 2 == 0 else 0.5))
                           for k, t in enumerate(np.linspace(0, math.tau, 7)[:-1])]
                    d.polygon(pts, fill=c)
                    dh.polygon(pts, fill=int(255 * shade / 1.15))
    return np.asarray(img).astype(np.float64) / 255.0, np.asarray(hl).astype(np.float64) / 255.0, 0.9


def bark(n, seed, color="#5a4a3a"):
    y, x = np.mgrid[0:n, 0:n] / n
    streak = pnoise(n, n / 40, seed, None)
    streak = np.repeat(streak.mean(axis=0, keepdims=True), n, axis=0) * 0.6 + 0.4 * pnoise(n, 12, seed + 1)
    rgb = hexrgb(color) * (0.6 + 0.6 * streak[..., None])
    return rgb, streak, 0.95


# ---- signs --------------------------------------------------------------------------------------------------------


def _font(px, bold=True):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"):
        try:
            return ImageFont.truetype(p, px)
        except OSError:
            continue
    return ImageFont.load_default()


def sign_atlas(n, towns: list[str]):
    """4×4 atlas of Italian road signs (Codice della Strada shapes/colours; generic, no logos):
    0 danger triangle, 1 speed 50, 2 speed 70, 3 no overtaking-ish roundel, 4 give way, 5 roundabout (blue),
    6 brown tourist sign, 7 km marker, 8.. town entry signs (white, black text) for the kit's towns."""
    cell = n // 4
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    red, white, blue, black, brown = (196, 30, 36, 255), (246, 246, 242, 255), (20, 70, 160, 255), (20, 20, 20, 255), (122, 70, 40, 255)

    def at(i):
        return (i % 4) * cell, (i // 4) * cell

    x, y = at(0)
    tri = [(x + cell * 0.5, y + cell * 0.08), (x + cell * 0.94, y + cell * 0.86), (x + cell * 0.06, y + cell * 0.86)]
    d.polygon(tri, fill=red)
    inner = [(x + cell * 0.5, y + cell * 0.24), (x + cell * 0.8, y + cell * 0.78), (x + cell * 0.2, y + cell * 0.78)]
    d.polygon(inner, fill=white)
    d.text((x + cell * 0.5, y + cell * 0.6), "!", fill=black, font=_font(int(cell * 0.32)), anchor="mm")
    for i, txt in ((1, "50"), (2, "70")):
        x, y = at(i)
        d.ellipse([x + cell * 0.06, y + cell * 0.06, x + cell * 0.94, y + cell * 0.94], fill=red)
        d.ellipse([x + cell * 0.18, y + cell * 0.18, x + cell * 0.82, y + cell * 0.82], fill=white)
        d.text((x + cell / 2, y + cell / 2), txt, fill=black, font=_font(int(cell * 0.3)), anchor="mm")
    x, y = at(3)
    d.ellipse([x + cell * 0.06, y + cell * 0.06, x + cell * 0.94, y + cell * 0.94], fill=red)
    d.ellipse([x + cell * 0.18, y + cell * 0.18, x + cell * 0.82, y + cell * 0.82], fill=white)
    d.text((x + cell / 2, y + cell / 2), "⇄", fill=black, font=_font(int(cell * 0.3)), anchor="mm")
    x, y = at(4)
    d.polygon([(x + cell * 0.06, y + cell * 0.12), (x + cell * 0.94, y + cell * 0.12), (x + cell * 0.5, y + cell * 0.9)], fill=red)
    d.polygon([(x + cell * 0.22, y + cell * 0.22), (x + cell * 0.78, y + cell * 0.22), (x + cell * 0.5, y + cell * 0.72)], fill=white)
    x, y = at(5)
    d.ellipse([x + cell * 0.06, y + cell * 0.06, x + cell * 0.94, y + cell * 0.94], fill=blue)
    d.arc([x + cell * 0.25, y + cell * 0.25, x + cell * 0.75, y + cell * 0.75], 0, 330, fill=white, width=int(cell * 0.07))
    x, y = at(6)
    d.rectangle([x + 2, y + cell * 0.25, x + cell - 2, y + cell * 0.75], fill=brown)
    d.text((x + cell / 2, y + cell / 2), "Saline", fill=white, font=_font(int(cell * 0.16)), anchor="mm")
    x, y = at(7)
    d.rectangle([x + cell * 0.25, y + 2, x + cell * 0.75, y + cell - 2], fill=white)
    d.text((x + cell / 2, y + cell * 0.4), "km", fill=black, font=_font(int(cell * 0.12)), anchor="mm")
    d.text((x + cell / 2, y + cell * 0.6), "12", fill=black, font=_font(int(cell * 0.16)), anchor="mm")
    for k, name in enumerate(towns[:8]):
        x, y = at(8 + k)
        d.rectangle([x + 2, y + cell * 0.3, x + cell - 2, y + cell * 0.7], fill=white, outline=black, width=max(2, cell // 40))
        size = int(cell * 0.15)
        while size > 8 and d.textlength(name.upper(), font=_font(size)) > cell * 0.88:
            size -= 1
        d.text((x + cell / 2, y + cell / 2), name.upper(), fill=black, font=_font(size), anchor="mm")
    return np.asarray(img).astype(np.float64) / 255.0


# ---- writer -------------------------------------------------------------------------------------------------------


def save(out: Path, mid: str, rgb, height=None, normal_strength=4.0):
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    if rgb.shape[-1] == 4:
        Image.fromarray(to_u8(rgb), "RGBA").save(out / f"{mid}_albedo.png", optimize=True)
        files["albedo"] = f"{mid}_albedo.png"
    else:
        Image.fromarray(to_u8(rgb), "RGB").save(out / f"{mid}_albedo.jpg", quality=88)
        files["albedo"] = f"{mid}_albedo.jpg"
    if height is not None:
        nm = Image.fromarray(normal_from_height(height, normal_strength), "RGB")
        if nm.width > 512:  # normal detail reads fine at half resolution; JPEG keeps web packages small
            nm = nm.resize((nm.width // 2, nm.height // 2), Image.LANCZOS)
        nm.save(out / f"{mid}_normal.jpg", quality=90)
        files["normal"] = f"{mid}_normal.jpg"
    return files
