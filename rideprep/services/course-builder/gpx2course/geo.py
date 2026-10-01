"""Geodesy helpers: local metric frame, resampling, curvature."""
from __future__ import annotations

import numpy as np
from pyproj import Geod, Transformer

GEOD = Geod(ellps="WGS84")


class LocalFrame:
    """Local east-north frame around an origin.

    x/y come from a transverse Mercator projection centred on the origin (scale 1), which matches ENU east/north
    to well under 0.1 % within the 10 km far zone, but — unlike a true topocentric frame — does not drop the
    terrain away with the Earth's curvature. z is the orthometric height. See docs/DECISIONS.md.
    """

    def __init__(self, lat0: float, lon0: float):
        self.lat0 = float(lat0)
        self.lon0 = float(lon0)
        self.proj = f"+proj=tmerc +lat_0={self.lat0} +lon_0={self.lon0} +k=1 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs"
        self._fwd = Transformer.from_crs("EPSG:4326", self.proj, always_xy=True)
        self._inv = Transformer.from_crs(self.proj, "EPSG:4326", always_xy=True)

    def to_xy(self, lat, lon):
        x, y = self._fwd.transform(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
        return np.asarray(x), np.asarray(y)

    def to_latlon(self, x, y):
        lon, lat = self._inv.transform(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
        return np.asarray(lat), np.asarray(lon)

    def crs_wkt(self) -> str:
        from pyproj import CRS
        return CRS.from_proj4(self.proj).to_wkt()


def cumulative_distance(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    d = np.hypot(np.diff(x), np.diff(y))
    return np.concatenate([[0.0], np.cumsum(d)])


def resample_uniform(s: np.ndarray, spacing: float, *arrays: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
    """Linear resampling of arrays defined at cumulative distances s onto a uniform grid."""
    # Drop duplicate distances so interp is well defined
    keep = np.concatenate([[True], np.diff(s) > 1e-6])
    s = s[keep]
    n = int(np.floor(s[-1] / spacing)) + 1
    grid = np.arange(n) * spacing
    if grid[-1] < s[-1] - 1e-6:
        grid = np.append(grid, s[-1])
    return grid, [np.interp(grid, s, a[keep]) for a in arrays]


def heading_compass(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Compass bearing (rad, clockwise from north) of travel using centred differences."""
    dx = np.gradient(x)
    dy = np.gradient(y)
    return np.mod(np.arctan2(dx, dy), 2 * np.pi)


def turning_radius(x: np.ndarray, y: np.ndarray, spacing: float, half_window_m: float = 10.0) -> np.ndarray:
    """Radius (m) from a 3-point circle fit over ±half_window; straight → inf. Smoothed (median of 3)."""
    k = max(1, int(round(half_window_m / spacing)))
    n = len(x)
    i = np.arange(n)
    a = np.clip(i - k, 0, n - 1)
    b = np.clip(i + k, 0, n - 1)
    ax, ay, bx, by = x[a], y[a], x[b], y[b]
    cx, cy = x, y
    # Circumradius R = |AB||BC||CA| / (4·area)
    ab = np.hypot(bx - ax, by - ay)
    bc = np.hypot(cx - bx, cy - by)
    ca = np.hypot(ax - cx, ay - cy)
    area2 = np.abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(area2 > 1e-6, ab * bc * ca / (2 * area2), np.inf)
    r[(a == i) | (b == i)] = np.inf
    # median-of-3 smoothing
    rp = np.pad(r, 1, mode="edge")
    r = np.median(np.stack([rp[:-2], rp[1:-1], rp[2:]]), axis=0)
    return r


def gaussian_smooth(values: np.ndarray, spacing: float, sigma_m: float) -> np.ndarray:
    from scipy.ndimage import gaussian_filter1d
    return gaussian_filter1d(values, sigma=sigma_m / spacing, mode="nearest")
