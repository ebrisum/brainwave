"""Stage 1 input parsing: GPX 1.1 (tracks, routes, waypoints), TCX and FIT."""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np


class IngestError(ValueError):
    pass


@dataclass
class RawCourse:
    name: str
    lat: np.ndarray
    lon: np.ndarray
    ele: np.ndarray  # NaN where missing
    time: np.ndarray  # epoch seconds, NaN where missing
    pois: list[dict] = field(default_factory=list)
    segment_breaks: list[int] = field(default_factory=list)  # indices where a new track segment starts
    source_format: str = "gpx"
    has_barometric: bool = False


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_time(s: str | None) -> float:
    if not s:
        return math.nan
    try:
        return datetime.fromisoformat(s.strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        return math.nan


def parse_gpx(data: bytes, name_hint: str) -> RawCourse:
    root = ET.fromstring(data)
    lat, lon, ele, tim, breaks, pois = [], [], [], [], [], []
    name = None
    for el in root.iter():
        t = _local(el.tag)
        if t == "metadata":
            for c in el:
                if _local(c.tag) == "name" and c.text:
                    name = c.text.strip()
        elif t == "wpt":
            poi = {"lat": float(el.get("lat")), "lon": float(el.get("lon")), "name": "", "type": "waypoint"}
            for c in el:
                ct = _local(c.tag)
                if ct in ("name", "type", "sym", "desc") and c.text:
                    poi[ct] = c.text.strip()
            pois.append(poi)
    # Tracks first; fall back to routes
    segs = [e for e in root.iter() if _local(e.tag) == "trkseg"]
    point_tag = "trkpt"
    if not segs:
        segs = [e for e in root.iter() if _local(e.tag) == "rte"]
        point_tag = "rtept"
    for seg in segs:
        breaks.append(len(lat))
        for p in seg:
            if _local(p.tag) != point_tag:
                continue
            lat.append(float(p.get("lat")))
            lon.append(float(p.get("lon")))
            e, tm = math.nan, math.nan
            for c in p:
                ct = _local(c.tag)
                if ct == "ele" and c.text:
                    e = float(c.text)
                elif ct == "time":
                    tm = _parse_time(c.text)
            ele.append(e)
            tim.append(tm)
        if not name:
            for c in seg if point_tag == "rtept" else []:
                if _local(c.tag) == "name" and c.text:
                    name = c.text.strip()
    if not name:
        for e in root.iter():
            if _local(e.tag) == "trk":
                for c in e:
                    if _local(c.tag) == "name" and c.text:
                        name = c.text.strip()
                break
    ele_a = np.array(ele, dtype=float)
    tim_a = np.array(tim, dtype=float)
    # Recorded files with timestamps usually carry barometric altitude; planned routes do not.
    has_baro = bool(np.isfinite(tim_a).mean() > 0.9 and np.isfinite(ele_a).mean() > 0.9)
    return RawCourse(name or name_hint, np.array(lat), np.array(lon), ele_a, tim_a, pois, breaks[1:], "gpx", has_baro)


def parse_tcx(data: bytes, name_hint: str) -> RawCourse:
    root = ET.fromstring(data)
    lat, lon, ele, tim, pois = [], [], [], [], []
    for tp in (e for e in root.iter() if _local(e.tag) == "Trackpoint"):
        la = lo = None
        e, tm = math.nan, math.nan
        for c in tp.iter():
            ct = _local(c.tag)
            if ct == "LatitudeDegrees":
                la = float(c.text)
            elif ct == "LongitudeDegrees":
                lo = float(c.text)
            elif ct == "AltitudeMeters":
                e = float(c.text)
            elif ct == "Time":
                tm = _parse_time(c.text)
        if la is not None and lo is not None:
            lat.append(la); lon.append(lo); ele.append(e); tim.append(tm)
    for cp in (e for e in root.iter() if _local(e.tag) == "CoursePoint"):
        d = {"type": "waypoint", "name": ""}
        for c in cp.iter():
            ct = _local(c.tag)
            if ct == "LatitudeDegrees":
                d["lat"] = float(c.text)
            elif ct == "LongitudeDegrees":
                d["lon"] = float(c.text)
            elif ct == "Name" and c.text:
                d["name"] = c.text.strip()
            elif ct == "PointType" and c.text:
                d["type"] = c.text.strip()
        if "lat" in d:
            pois.append(d)
    name = next((c.text for c in root.iter() if _local(c.tag) in ("Name", "Id") and c.text), name_hint)
    return RawCourse(name, np.array(lat), np.array(lon), np.array(ele), np.array(tim), pois, [], "tcx", True)


def parse_fit(path: Path, name_hint: str) -> RawCourse:
    import fitdecode

    lat, lon, ele, tim, pois = [], [], [], [], []
    semi = 180.0 / 2**31
    with fitdecode.FitReader(str(path)) as fr:
        for frame in fr:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            if frame.name == "record":
                la = frame.get_value("position_lat", fallback=None)
                lo = frame.get_value("position_long", fallback=None)
                if la is None or lo is None:
                    continue
                alt = frame.get_value("enhanced_altitude", fallback=None)
                if alt is None:
                    alt = frame.get_value("altitude", fallback=None)
                ts = frame.get_value("timestamp", fallback=None)
                lat.append(la * semi); lon.append(lo * semi)
                ele.append(float(alt) if alt is not None else math.nan)
                tim.append(ts.timestamp() if ts is not None else math.nan)
            elif frame.name == "course_point":
                la = frame.get_value("position_lat", fallback=None)
                lo = frame.get_value("position_long", fallback=None)
                if la is not None and lo is not None:
                    pois.append({"lat": la * semi, "lon": lo * semi, "name": str(frame.get_value("name", fallback="") or ""),
                                 "type": str(frame.get_value("type", fallback="waypoint"))})
    return RawCourse(name_hint, np.array(lat), np.array(lon), np.array(ele), np.array(tim), pois, [], "fit", True)


def read_course(path: str | Path) -> RawCourse:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".gpx":
        rc = parse_gpx(p.read_bytes(), p.stem)
    elif suffix == ".tcx":
        rc = parse_tcx(p.read_bytes(), p.stem)
    elif suffix == ".fit":
        rc = parse_fit(p, p.stem)
    else:
        raise IngestError(f"unsupported file type {suffix!r} (expected .gpx, .tcx or .fit)")
    if len(rc.lat) == 0:
        raise IngestError("no track or route points found")
    return rc
