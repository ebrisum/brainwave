"""Stage 7 — weather: weather.json for the chosen mode and climatology.json (wind rose, percentiles, scenarios).

Never blocks a ride: provider failures fall back to generic climatology with a warning.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ..pipeline import BuildContext
from ..providers import ProviderUnavailable
from ..providers.weather import OpenMeteo, generic_climatology, wind_rose
from .common import load_route

VARS = ["u10", "dirDeg", "gust10", "tempC", "rh", "pMslHpa", "precipMmH", "cloudCover", "visibilityM"]


def _points(ctx: BuildContext):
    r = load_route(ctx)
    L = r["s"][-1]
    sp = ctx.config.tunables.weather_spacing_m
    ss = np.arange(0, L + 1e-6, sp)
    if ss[-1] < L:
        ss = np.append(ss, L)
    lat = np.interp(ss, r["s"], r["lat"])
    lon = np.interp(ss, r["s"], r["lon"])
    return ss, lat, lon, L


def _hours(start: datetime, L: float) -> list[datetime]:
    est = L / (25 / 3.6) + 2 * 3600  # generous: 25 km/h + 2 h
    h0 = start.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    return [h0 + timedelta(hours=k) for k in range(int(math.ceil(est / 3600)) + 2)]


def _normalise(rec: dict) -> dict:
    """Unit fixes: RH % → fraction, cloud % → fraction."""
    out = dict(rec)
    if "rh" in out:
        out["rh"] = [None if v is None or (isinstance(v, float) and math.isnan(v)) else v / 100 for v in out["rh"]]
    if "cloudCover" in out:
        out["cloudCover"] = [None if v is None or (isinstance(v, float) and math.isnan(v)) else v / 100 for v in out["cloudCover"]]
    return out


def build_weather_json(mode: str, source: str, ss, times: list[int], per_point: list[dict]) -> dict:
    values = {}
    for v in VARS:
        if all(v in p for p in per_point):
            grid = []
            for p in per_point:
                tt = np.array(p["time"], dtype=float)
                vals = np.array([np.nan if x is None else x for x in p[v]], dtype=float)
                ok = np.isfinite(vals)
                if ok.sum() == 0:
                    break
                if v == "dirDeg":  # interpolate direction via vector components
                    ex = np.interp(times, tt[ok], np.sin(np.radians(vals[ok])))
                    ny = np.interp(times, tt[ok], np.cos(np.radians(vals[ok])))
                    row = np.mod(np.degrees(np.arctan2(ex, ny)), 360)
                else:
                    row = np.interp(times, tt[ok], vals[ok])
                grid.append([round(float(a), 3) for a in row])
            else:
                values[v] = grid
    return {"mode": mode, "source": source, "s": [round(float(a), 1) for a in ss], "t": times, "values": values}


def constant_weather_json(mode: str, source: str, state: dict, t0: int) -> dict:
    return {"mode": mode, "source": source, "s": [0.0], "t": [t0], "values": {k: [[float(v)]] for k, v in state.items() if k in VARS}}


def climatology(ctx: BuildContext, om: OpenMeteo, lat: float, lon: float, start: datetime) -> dict:
    t = ctx.config.tunables
    try:
        smp = om.climatology_samples(lat, lon, start, t.climatology_years, 15, 2)
        u = np.array(smp["u10"], dtype=float)
        d = np.array(smp["dirDeg"], dtype=float)
        g = np.array(smp.get("gust10", []), dtype=float)
        T = np.array(smp["tempC"], dtype=float)
        rh = np.array(smp.get("rh", []), dtype=float) / 100
        p = np.array(smp.get("pMslHpa", []), dtype=float)
        pr = np.array(smp.get("precipMmH", []), dtype=float)
        rose = wind_rose(u, d)
        dir_freq = np.array(rose).sum(axis=1)
        modal = float(np.argmax(dir_freq) * 22.5)
        ok = np.isfinite(u) & np.isfinite(g) & (u > 1) if len(g) == len(u) else np.zeros(0, bool)
        years = (start.year - t.climatology_years, start.year - 1)
        clim = {"source": "open-meteo-era5", "years": [datetime.now(timezone.utc).year - t.climatology_years, datetime.now(timezone.utc).year - 1],
                "windRose": {"dirBins": 16, "speedBinsMs": [0, 2, 4, 6, 8, 10], "freq": rose},
                "windSpeedPercentiles": {k: round(float(np.nanpercentile(u, q)), 2) for k, q in (("p50", 50), ("p75", 75), ("p90", 90))},
                "gustRatio": round(float(np.nanmedian(g[ok] / u[ok])) if ok.any() else 1.6, 2),
                "modalDirDeg": modal, "prevailingDirDeg": _vector_mean_dir(u, d),
                "tempC": {k: round(float(np.nanpercentile(T, q)), 1) for k, q in (("p10", 10), ("p50", 50), ("p90", 90))},
                "rhMedian": round(float(np.nanmedian(rh)), 3) if len(rh) else 0.72,
                "pMslMedianHpa": round(float(np.nanmedian(p)), 1) if len(p) else 1015.0,
                "rainProbability": round(float(np.nanmean(pr > 0.2)), 3) if len(pr) else 0.15, "samples": int(len(u))}
        del years
        ctx.source("climatology", om.info)
    except ProviderUnavailable as ex:
        gc = generic_climatology(lat, start.month)
        ctx.warn(f"climatology unavailable ({ex}); using generic mid-latitude defaults", code="climatology_fallback")
        clim = {"source": gc["source"], "years": None, "windRose": {"dirBins": 16, "speedBinsMs": [0, 2, 4, 6, 8, 10], "freq": _synthetic_rose(gc)},
                "windSpeedPercentiles": {"p50": gc["p50"], "p75": gc["p75"], "p90": gc["p90"]}, "gustRatio": gc["gustRatio"],
                "modalDirDeg": gc["modalDirDeg"], "prevailingDirDeg": gc["modalDirDeg"],
                "tempC": {"p10": round(gc["tempC"][0], 1), "p50": round(gc["tempC"][1], 1), "p90": round(gc["tempC"][2], 1)},
                "rhMedian": gc["rh"], "pMslMedianHpa": gc["pMsl"], "rainProbability": gc["rainProbability"], "samples": 0}
    clim["window"] = {"monthDayCentre": start.strftime("%m-%d"), "dayRange": 15, "hourRange": 2, "utcHour": start.astimezone(timezone.utc).hour}
    clim["scenarios"] = [
        {"name": "calm", "label": "Calm", "u10": 1.0, "dirDeg": clim["modalDirDeg"]},
        {"name": "mostLikely", "label": "Most likely", "u10": clim["windSpeedPercentiles"]["p50"], "dirDeg": clim["modalDirDeg"]},
        {"name": "windy", "label": "Windy", "u10": clim["windSpeedPercentiles"]["p90"], "dirDeg": clim["modalDirDeg"]},
        {"name": "worstCase", "label": "Worst case", "u10": clim["windSpeedPercentiles"]["p75"], "dirDeg": None,
         "note": "direction chosen at runtime by the predictor (all 16 bins at P75 speed)"},
    ]
    return clim


def _vector_mean_dir(u, d) -> float:
    ok = np.isfinite(u) & np.isfinite(d)
    ex = np.sum(u[ok] * np.sin(np.radians(d[ok])))
    ny = np.sum(u[ok] * np.cos(np.radians(d[ok])))
    return round(float(np.degrees(np.arctan2(ex, ny)) % 360), 1)


def _synthetic_rose(gc) -> list[list[float]]:
    dirs = np.arange(16) * 22.5
    w = np.exp(np.cos(np.radians(dirs - gc["modalDirDeg"])) * 1.2)
    w /= w.sum()
    speed = np.array([0.15, 0.3, 0.27, 0.16, 0.08, 0.04])
    return np.round(np.outer(w, speed), 5).tolist()


def run(ctx: BuildContext) -> list[str]:
    cfg = ctx.config
    ss, lat, lon, L = _points(ctx)
    start = ctx.options.event_start or datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
    om = OpenMeteo(cfg.endpoints.open_meteo_forecast, cfg.endpoints.open_meteo_archive, cfg.cache_dir, cfg.tunables.network_timeout_s, cfg.offline)
    mid = len(lat) // 2
    clim = climatology(ctx, om, float(lat[mid]), float(lon[mid]), start)
    ctx.write_json("climatology.json", clim)
    mode = ctx.options.weather or "climatology"
    hours = _hours(start, L)
    times = [int(h.timestamp()) for h in hours]
    wj = None
    try:
        if mode == "forecast":
            if start - datetime.now(timezone.utc) > timedelta(days=15):
                raise ProviderUnavailable("event is beyond the 16-day forecast horizon")
            recs = om.hourly(lat, lon, hours[0], hours[-1], historical=False)
            wj = build_weather_json("forecast", "open-meteo", ss, times, [_normalise(r) for r in recs])
        elif mode.startswith("historical:"):
            day = datetime.fromisoformat(mode.split(":", 1)[1]).replace(tzinfo=timezone.utc)
            shift = day.replace(hour=start.hour, minute=start.minute) - start
            hh = [h + shift for h in hours]
            recs = om.hourly(lat, lon, hh[0], hh[-1], historical=True)
            for r in recs:
                r["time"] = [int(t - shift.total_seconds()) for t in r["time"]]
            wj = build_weather_json("historical", f"open-meteo-era5:{day.date()}", ss, times, [_normalise(r) for r in recs])
        elif mode.startswith("manual:"):
            m = json.loads(Path(mode.split(":", 1)[1]).read_text())
            wj = constant_weather_json("manual", "manual", m, times[0])
        elif mode != "climatology":
            raise ValueError(f"unknown weather mode {mode!r}")
    except ProviderUnavailable as ex:
        ctx.warn(f"{mode} weather unavailable ({ex}); using the climatology 'most likely' scenario", code="weather_fallback")
    if wj is None:
        state = {"u10": clim["windSpeedPercentiles"]["p50"], "dirDeg": clim["modalDirDeg"],
                 "gust10": clim["windSpeedPercentiles"]["p50"] * clim["gustRatio"], "tempC": clim["tempC"]["p50"], "rh": clim["rhMedian"],
                 "pMslHpa": clim["pMslMedianHpa"], "precipMmH": 0.0, "cloudCover": 0.5, "visibilityM": 20000}
        wj = constant_weather_json("climatology", clim["source"], state, times[0])
    wj["eventStart"] = start.isoformat()
    ctx.write_json("weather.json", wj)
    return ["weather.json", "climatology.json"]
