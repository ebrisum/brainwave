"""Proposed structure — Phase 1 (Blender Python): GPX → local metres → DEM-grounded Z → smoothed 3D Bezier curve.

  blender -b --python phase1_gpx_to_curve.py -- --gpx course.gpx --dem dem.tif --out phase1.blend [--json pts.json]

Implemented as specified (no road network): parse trkpt/rtept, project to a local Cartesian frame (equirectangular at
the route centroid — what a self-contained Blender script can do without pyproj), replace Z with bilinear samples from
a local GeoTIFF (EPSG:4326, uncompressed — read with a tiny reader because Blender ships without GDAL), densify to 5 m,
Gaussian-smooth XY and Z, and build a Bezier curve with AUTO handles every 10 m.
"""
import argparse
import json
import math
import struct
import sys
import xml.etree.ElementTree as ET

import numpy as np

import bpy  # noqa: I001

R_EARTH = 6_371_008.8


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--gpx", required=True)
    p.add_argument("--dem", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--json", default=None)
    p.add_argument("--sigma", type=float, default=10.0, help="smoothing (m)")
    p.add_argument("--handle-step", type=float, default=10.0)
    return p.parse_args(argv)


# ---- GPX -----------------------------------------------------------------------------------------------------------


def parse_gpx(path):
    root = ET.parse(path).getroot()
    pts = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in ("trkpt", "rtept"):
            ele = None
            for ch in el:
                if ch.tag.split("}")[-1] == "ele" and ch.text:
                    ele = float(ch.text)
            pts.append((float(el.get("lat")), float(el.get("lon")), ele))
    # drop exact duplicates
    out = [pts[0]]
    for p in pts[1:]:
        if p[:2] != out[-1][:2]:
            out.append(p)
    return out


# ---- projection -----------------------------------------------------------------------------------------------------


class LocalFrame:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.k = math.cos(math.radians(lat0))

    def to_xy(self, lat, lon):
        return (np.radians(np.asarray(lon) - self.lon0) * R_EARTH * self.k, np.radians(np.asarray(lat) - self.lat0) * R_EARTH)

    def to_latlon(self, x, y):
        return (self.lat0 + np.degrees(np.asarray(y) / R_EARTH), self.lon0 + np.degrees(np.asarray(x) / (R_EARTH * self.k)))


# ---- minimal GeoTIFF reader (uncompressed, strips or tiles, float32/int16, north-up) ---------------------------------


def read_geotiff(path):
    data = open(path, "rb").read()
    bo = "<" if data[:2] == b"II" else ">"
    off = struct.unpack(bo + "I", data[4:8])[0]
    n = struct.unpack(bo + "H", data[off:off + 2])[0]
    tags = {}
    sizes = {1: 1, 2: 1, 3: 2, 4: 4, 11: 4, 12: 8, 16: 8}
    fmt = {1: "B", 2: "c", 3: "H", 4: "I", 11: "f", 12: "d", 16: "Q"}
    for k in range(n):
        e = off + 2 + 12 * k
        tag, typ, cnt = struct.unpack(bo + "HHI", data[e:e + 8])
        sz = sizes[typ] * cnt
        voff = e + 8 if sz <= 4 else struct.unpack(bo + "I", data[e + 8:e + 12])[0]
        vals = struct.unpack(bo + fmt[typ] * cnt, data[voff:voff + sz]) if typ != 2 else data[voff:voff + sz]
        tags[tag] = vals
    if tags.get(259, (1,))[0] != 1:
        raise SystemExit("GeoTIFF must be uncompressed for this reader (gdal_translate -co COMPRESS=NONE)")
    w, h = tags[256][0], tags[257][0]
    bits, sfmt = tags[258][0], tags.get(339, (1,))[0]
    dt = np.dtype({(32, 3): "f4", (64, 3): "f8", (16, 2): "i2", (16, 1): "u2", (32, 2): "i4"}[(bits, sfmt)]).newbyteorder(bo)
    arr = np.empty((h, w), dt.newbyteorder("="))
    if 324 in tags:  # tiled
        tw, th = tags[322][0], tags[323][0]
        across = (w + tw - 1) // tw
        for t, (o, c) in enumerate(zip(tags[324], tags[325])):
            ty, tx = divmod(t, across)
            tile = np.frombuffer(data[o:o + c], dt).reshape(th, tw)
            ys, xs = ty * th, tx * tw
            arr[ys:ys + th, xs:xs + tw] = tile[: min(th, h - ys), : min(tw, w - xs)]
    else:
        rps = tags.get(278, (h,))[0]
        for s, (o, c) in enumerate(zip(tags[273], tags[279])):
            rows = np.frombuffer(data[o:o + c], dt).reshape(-1, w)
            arr[s * rps:s * rps + len(rows)] = rows
    sx, sy = tags[33550][0], tags[33550][1]
    tie = tags[33922]
    x0, y0 = tie[3] - tie[0] * sx, tie[4] + tie[1] * sy
    return arr.astype(np.float64), (x0, y0, sx, sy)


def sample_bilinear(arr, geo, lon, lat):
    x0, y0, sx, sy = geo
    c = (np.asarray(lon) - x0) / sx - 0.5
    r = (y0 - np.asarray(lat)) / sy - 0.5
    c = np.clip(c, 0, arr.shape[1] - 1.001)
    r = np.clip(r, 0, arr.shape[0] - 1.001)
    c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
    fc, fr = c - c0, r - r0
    a = arr[r0, c0] * (1 - fc) + arr[r0, c0 + 1] * fc
    b = arr[r0 + 1, c0] * (1 - fc) + arr[r0 + 1, c0 + 1] * fc
    return a * (1 - fr) + b * fr


# ---- smoothing ------------------------------------------------------------------------------------------------------


def densify(x, y, step):
    s = np.r_[0, np.cumsum(np.hypot(np.diff(x), np.diff(y)))]
    g = np.arange(0, s[-1], step)
    return np.interp(g, s, x), np.interp(g, s, y), g


def gaussian(v, sigma_samples):
    if sigma_samples <= 0:
        return v
    r = int(3 * sigma_samples)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_samples) ** 2)
    k /= k.sum()
    pad = np.r_[np.full(r, v[0]), v, np.full(r, v[-1])]
    return np.convolve(pad, k, mode="valid")


def main():
    a = args()
    pts = parse_gpx(a.gpx)
    lat = np.array([p[0] for p in pts])
    lon = np.array([p[1] for p in pts])
    frame = LocalFrame(float(lat.mean()), float(lon.mean()))
    x, y = frame.to_xy(lat, lon)
    dem, geo = read_geotiff(a.dem)
    step = 5.0
    xd, yd, s = densify(x, y, step)
    xs, ys = gaussian(xd, a.sigma / step), gaussian(yd, a.sigma / step)
    la, lo = frame.to_latlon(xs, ys)
    z = gaussian(sample_bilinear(dem, geo, lo, la), a.sigma / step)
    # Bezier curve, AUTO handles every handle_step metres
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cu = bpy.data.curves.new("GPX_Route", "CURVE")
    cu.dimensions = "3D"
    cu.twist_mode = "Z_UP"
    sp = cu.splines.new("BEZIER")
    k = max(1, int(round(a.handle_step / step)))
    idx = list(range(0, len(xs), k))
    if idx[-1] != len(xs) - 1:
        idx.append(len(xs) - 1)
    sp.bezier_points.add(len(idx) - 1)
    for bp, i in zip(sp.bezier_points, idx):
        bp.co = (xs[i], ys[i], z[i])
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new("GPX_Route", cu)
    bpy.context.scene.collection.objects.link(ob)
    ob["frame"] = [frame.lat0, frame.lon0]
    bpy.ops.wm.save_as_mainfile(filepath=a.out)
    L = float(np.sum(np.hypot(np.diff(xs), np.diff(ys))))
    print(f"phase1: {len(pts)} GPX points → {len(idx)} Bezier points, {L / 1000:.2f} km, z {z.min():.1f}–{z.max():.1f} m")
    if a.json:
        json.dump({"frame": [frame.lat0, frame.lon0], "x": np.round(xs, 3).tolist(), "y": np.round(ys, 3).tolist(),
                   "z": np.round(z, 3).tolist(), "gpx_x": np.round(x, 3).tolist(), "gpx_y": np.round(y, 3).tolist()}, open(a.json, "w"))


if __name__ == "__main__":
    main()
