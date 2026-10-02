"""Pipeline configuration: provider priorities, API endpoints, cache paths, model tunables (gpx2course.toml)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProviderConfig:
    # Priority-ordered provider names per data kind. The first provider that covers the area wins.
    dem: list[str] = field(default_factory=lambda: ["copernicus", "gpx"])
    landcover: list[str] = field(default_factory=lambda: ["worldcover", "osm"])
    osm: list[str] = field(default_factory=lambda: ["sidecar", "pbf", "overture", "overpass"])
    matcher: list[str] = field(default_factory=lambda: ["valhalla", "nearest-way"])
    weather: list[str] = field(default_factory=lambda: ["open-meteo"])


@dataclass
class Endpoints:
    valhalla_url: str = os.environ.get("VALHALLA_URL", "http://localhost:8002")
    overpass_url: str = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
    open_meteo_forecast: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_archive: str = "https://archive-api.open-meteo.com/v1/archive"
    copernicus_dem: str = "https://copernicus-dem-30m.s3.amazonaws.com"
    worldcover: str = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
    osm_pbf_dir: str = os.environ.get("OSM_PBF_DIR", "")


@dataclass
class Tunables:
    sample_spacing_m: float = 5.0
    wind_spacing_m: float = 10.0
    chunk_length_m: float = 500.0
    near_buffer_m: float = 150.0
    mid_buffer_m: float = 1500.0
    far_buffer_m: float = 10000.0
    wind_fetch_m: float = 2000.0
    crr_base: float = 0.004
    max_grade_pct: float = 25.0
    gap_flag_m: float = 50.0
    max_course_km: float = 400.0
    min_points: int = 50
    weather_spacing_m: float = 5000.0
    climatology_years: int = 15
    network_timeout_s: float = 20.0


@dataclass
class Config:
    providers: ProviderConfig = field(default_factory=ProviderConfig)
    endpoints: Endpoints = field(default_factory=Endpoints)
    tunables: Tunables = field(default_factory=Tunables)
    cache_dir: Path = field(default_factory=lambda: Path(os.environ.get("GPX2COURSE_CACHE", Path.home() / ".cache" / "gpx2course")))
    offline: bool = False
    style_override: str | None = None
    api_keys: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def load(path: str | Path | None) -> "Config":
        cfg = Config()
        if path:
            data = tomllib.loads(Path(path).read_text())
            cfg.apply(data)
        if os.environ.get("GPX2COURSE_OFFLINE") == "1":
            cfg.offline = True
        return cfg

    def apply(self, data: dict[str, Any]) -> None:
        for section, obj in (("providers", self.providers), ("endpoints", self.endpoints), ("tunables", self.tunables)):
            for k, v in data.get(section, {}).items():
                if not hasattr(obj, k):
                    raise ValueError(f"unknown config key {section}.{k}")
                setattr(obj, k, v)
        if "cache_dir" in data:
            self.cache_dir = Path(data["cache_dir"]).expanduser()
        if "style" in data:
            self.style_override = data["style"]
        if "offline" in data:
            self.offline = bool(data["offline"])
        self.api_keys.update(data.get("api_keys", {}))

    def fingerprint(self) -> dict[str, Any]:
        """Parts of the config that affect outputs (used in stage cache keys)."""
        from dataclasses import asdict
        return {"providers": asdict(self.providers), "tunables": asdict(self.tunables), "offline": self.offline, "style": self.style_override}
