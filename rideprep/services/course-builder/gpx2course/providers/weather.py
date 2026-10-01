"""Weather providers: Open-Meteo (forecast, ERA5 archive, climatology) and manual scenarios."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import ProviderInfo, ProviderUnavailable, http_client

HOURLY_VARS = ["wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "temperature_2m", "relative_humidity_2m", "pressure_msl",
               "precipitation", "cloud_cover", "visibility"]
# Open-Meteo variable → weather.json variable
VAR_MAP = {"wind_speed_10m": "u10", "wind_direction_10m": "dirDeg", "wind_gusts_10m": "gust10", "temperature_2m": "tempC",
           "relative_humidity_2m": "rh", "pressure_msl": "pMslHpa", "precipitation": "precipMmH", "cloud_cover": "cloudCover",
           "visibility": "visibilityM"}

OPEN_METEO_INFO = ProviderInfo("open-meteo", "weather", "Data CC BY 4.0; free API for non-commercial use only",
                               "Weather data by Open-Meteo.com (CC BY 4.0)", bakeable=True)


class OpenMeteo:
    info = OPEN_METEO_INFO

    def __init__(self, forecast_url: str, archive_url: str, cache_dir: Path, timeout: float, offline: bool):
        self.forecast_url = forecast_url
        self.archive_url = archive_url
        self.cache_dir = cache_dir / "open-meteo"
        self.timeout = timeout
        self.offline = offline

    def _get(self, url: str, params: dict, cache: bool) -> dict | list:
        key = hashlib.sha256((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()[:24]
        path = self.cache_dir / f"{key}.json"
        if cache and path.exists():
            return json.loads(path.read_text())
        if self.offline:
            raise ProviderUnavailable("offline")
        try:
            with http_client(self.timeout) as c:
                r = c.get(url, params=params)
                r.raise_for_status()
                data = r.json()
        except Exception as ex:  # noqa: BLE001
            raise ProviderUnavailable(f"Open-Meteo request failed: {ex}") from ex
        if cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
        return data

    def hourly(self, lats, lons, start: datetime, end: datetime, historical: bool) -> list[dict]:
        """Hourly series for several points. Returns one dict per point: {time: [...epoch], var: [...]}."""
        params = {"latitude": ",".join(f"{v:.4f}" for v in lats), "longitude": ",".join(f"{v:.4f}" for v in lons),
                  "hourly": ",".join(HOURLY_VARS if not historical else [v for v in HOURLY_VARS if v != "visibility"]),
                  "wind_speed_unit": "ms", "timezone": "GMT", "timeformat": "unixtime",
                  "start_date": start.strftime("%Y-%m-%d"), "end_date": end.strftime("%Y-%m-%d")}
        url = self.archive_url if historical else self.forecast_url
        data = self._get(url, params, cache=historical)
        items = data if isinstance(data, list) else [data]
        out = []
        for it in items:
            h = it["hourly"]
            rec = {"time": h["time"]}
            for k, v in VAR_MAP.items():
                if k in h:
                    rec[v] = [math.nan if x is None else x for x in h[k]]
            out.append(rec)
        return out

    def climatology_samples(self, lat: float, lon: float, centre: datetime, years: int, day_range: int, hour_range: int) -> dict:
        """15 years of hourly archive data for the month-day ±day_range and local hour ±hour_range (cached per 0.25° cell)."""
        clat, clon = round(lat * 4) / 4, round(lon * 4) / 4
        samples: dict[str, list] = {v: [] for v in VAR_MAP.values()}
        this_year = datetime.now(timezone.utc).year
        for y in range(this_year - years, this_year):
            try:
                c = centre.replace(year=y)
            except ValueError:
                c = centre.replace(year=y, day=28)
            s, e = c - timedelta(days=day_range), c + timedelta(days=day_range)
            rec = self.hourly([clat], [clon], s, e, historical=True)[0]
            for i, t in enumerate(rec["time"]):
                dt = datetime.fromtimestamp(t, timezone.utc)
                dh = abs((dt.hour - c.hour + 12) % 24 - 12)
                if dh <= hour_range:
                    for v in samples:
                        if v in rec:
                            samples[v].append(rec[v][i])
        if not samples["u10"]:
            raise ProviderUnavailable("no archive data")
        return samples


def generic_climatology(lat: float, month: int) -> dict:
    """Last-resort typical conditions when no weather provider is reachable (flagged as a warning in the report)."""
    westerlies = 35 <= abs(lat) <= 65
    summer = month in (5, 6, 7, 8, 9) if lat >= 0 else month in (11, 12, 1, 2, 3)
    return {
        "source": "generic-fallback",
        "modalDirDeg": 247.5 if westerlies and lat >= 0 else (292.5 if westerlies else 90.0),
        "p50": 4.0 if summer else 5.0, "p75": 5.5 if summer else 6.8, "p90": 7.2 if summer else 8.8,
        "tempC": (12 + 6 * summer - abs(lat - 45) * 0.3, 17 + 6 * summer - abs(lat - 45) * 0.3, 22 + 6 * summer - abs(lat - 45) * 0.3),
        "rh": 0.72, "pMsl": 1015.0, "rainProbability": 0.12 if summer else 0.2, "gustRatio": 1.6,
    }


def wind_rose(u: np.ndarray, d: np.ndarray, speed_bins=(0, 2, 4, 6, 8, 10)) -> list[list[float]]:
    ok = np.isfinite(u) & np.isfinite(d)
    u, d = u[ok], d[ok]
    dbin = np.floor(((d + 11.25) % 360) / 22.5).astype(int)
    sbin = np.clip(np.searchsorted(speed_bins, u, side="right") - 1, 0, len(speed_bins) - 1)
    freq = np.zeros((16, len(speed_bins)))
    np.add.at(freq, (dbin, sbin), 1)
    if freq.sum() > 0:
        freq /= freq.sum()
    return np.round(freq, 5).tolist()
