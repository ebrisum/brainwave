"""Elevation (DTM/DSM) providers."""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np

from . import ProviderInfo, ProviderUnavailable


class DemProvider:
    info: ProviderInfo

    def available(self) -> bool:
        return True

    def covers(self, lat: np.ndarray, lon: np.ndarray) -> float:
        """Fraction of points this provider covers (0..1)."""
        return 1.0

    def sample(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Bilinear orthometric heights (m) at points; NaN where not covered."""
        raise NotImplementedError


class GpxDem(DemProvider):
    """Fallback: heights recorded in the input file, spread to nearby points by nearest-neighbour."""

    info = ProviderInfo("gpx", "dem", "input file", "", resolution_m=None)

    def __init__(self, lat: np.ndarray, lon: np.ndarray, ele: np.ndarray):
        from scipy.spatial import cKDTree

        ok = np.isfinite(ele)
        if ok.sum() < 2:
            raise ProviderUnavailable("input has no elevation")
        self._lat0 = float(np.mean(lat))
        self._k = math.cos(math.radians(self._lat0))
        self._pts = np.c_[lat[ok], lon[ok] * self._k]
        self._ele = ele[ok]
        self._tree = cKDTree(self._pts)

    def sample(self, lat, lon):
        q = np.c_[np.ravel(lat), np.ravel(lon) * self._k]
        d, idx = self._tree.query(q, k=min(3, len(self._ele)), workers=-1)
        w = 1.0 / np.maximum(d, 1e-7) ** 2
        z = (self._ele[idx] * w).sum(axis=1) / w.sum(axis=1)
        return z.reshape(np.shape(lat))


def _gdal_env():
    import rasterio

    ca = os.environ.get("CURL_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    opts = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "GDAL_HTTP_TIMEOUT": "30",
            "VSI_CACHE": "TRUE", "GDAL_HTTP_MAX_RETRY": "2"}
    if ca:
        opts["CURL_CA_BUNDLE"] = ca
    return rasterio.Env(**opts)


class TiledCogSampler:
    """Bilinear sampler over a set of 1°/3° COG tiles, reading only the needed window (optionally decimated)."""

    def __init__(self, url_for_tile, tile_deg: int, cache_dir: Path, nodata_value: float | None = None, max_pixels: int = 40_000_000,
                 resampling: str = "bilinear"):
        self.url_for_tile = url_for_tile
        self.tile_deg = tile_deg
        self.cache_dir = cache_dir
        self.nodata_value = nodata_value
        self.max_pixels = max_pixels
        self.resampling = resampling
        self.missing: set[tuple[int, int]] = set()

    def local_path(self, url: str) -> Path:
        return self.cache_dir / "tiles" / url.rsplit("/", 1)[-1]

    def tiles_for(self, lat, lon):
        t = self.tile_deg
        keys = set(zip((np.floor(np.ravel(lat) / t) * t).astype(int), (np.floor(np.ravel(lon) / t) * t).astype(int)))
        return sorted(keys)

    def read(self, lat, lon, order: int = 1):
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.windows import from_bounds
        from scipy.ndimage import map_coordinates

        lat = np.ravel(np.asarray(lat, dtype=float))
        lon = np.ravel(np.asarray(lon, dtype=float))
        out = np.full(lat.shape, np.nan)
        t = self.tile_deg
        with _gdal_env():
            for (tlat, tlon) in self.tiles_for(lat, lon):
                sel = (np.floor(lat / t) * t == tlat) & (np.floor(lon / t) * t == tlon)
                if (tlat, tlon) in self.missing:
                    continue
                url = self.url_for_tile(tlat, tlon)
                local = self.local_path(url)
                if local.exists():
                    url = str(local)
                try:
                    ds = rasterio.open(url)
                except Exception:
                    self.missing.add((tlat, tlon))
                    continue
                with ds:
                    pad = 2 * max(abs(ds.res[0]), abs(ds.res[1]))
                    w, s, e, n = lon[sel].min() - pad, lat[sel].min() - pad, lon[sel].max() + pad, lat[sel].max() + pad
                    win = from_bounds(max(w, ds.bounds.left), max(s, ds.bounds.bottom), min(e, ds.bounds.right), min(n, ds.bounds.top), ds.transform)
                    win = win.round_offsets().round_lengths()
                    h, wd = max(int(win.height), 1), max(int(win.width), 1)
                    scale = max(1.0, math.sqrt(h * wd / self.max_pixels))
                    oh, ow = max(2, int(h / scale)), max(2, int(wd / scale))
                    rs = Resampling.nearest if self.resampling == "nearest" else Resampling.bilinear
                    arr = ds.read(1, window=win, out_shape=(oh, ow), resampling=rs).astype(float)
                    if ds.nodata is not None:
                        arr[arr == ds.nodata] = np.nan
                    wt = ds.window_transform(win)
                    # pixel coordinates in the decimated array
                    inv = ~wt
                    cols, rows = inv * (lon[sel], lat[sel])
                    rows = rows * oh / h - 0.5
                    cols = cols * ow / wd - 0.5
                    out[sel] = map_coordinates(arr, [rows, cols], order=order, mode="nearest", cval=np.nan)
        return out


class CopernicusDem(DemProvider):
    """Copernicus DEM GLO-30 (public COGs on AWS). Heights are EGM2008 orthometric. It is a DSM in forests/towns."""

    info = ProviderInfo("copernicus", "dem", "Copernicus DEM licence (free, attribution)",
                        "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA",
                        resolution_m=30)

    def __init__(self, base_url: str, cache_dir: Path, offline: bool = False):
        self.base_url = base_url.rstrip("/")
        self.offline = offline
        self.sampler = TiledCogSampler(self._url, 1, cache_dir)

    def _url(self, tlat: int, tlon: int) -> str:
        ns = f"N{tlat:02d}" if tlat >= 0 else f"S{-tlat:02d}"
        ew = f"E{tlon:03d}" if tlon >= 0 else f"W{-tlon:03d}"
        name = f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"
        return f"/vsicurl/{self.base_url}/{name}/{name}.tif"

    def available(self) -> bool:
        return not self.offline

    def sample(self, lat, lon):
        if self.offline:
            raise ProviderUnavailable("offline")
        z = self.sampler.read(lat, lon).reshape(np.shape(lat))
        if np.all(np.isnan(z)):
            raise ProviderUnavailable("no Copernicus DEM tiles reachable for this area")
        return z
