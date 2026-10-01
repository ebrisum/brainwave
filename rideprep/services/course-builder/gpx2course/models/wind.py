"""Wind model maths shared by the wind stage and tests (mirrors packages/physics/src/wind; WIND_MODEL.md)."""
from __future__ import annotations

import math

import numpy as np

Z0_REF = 0.03
BLEND_H = 60.0
RIDER_H = 1.2
Z0_CAP = 0.30


def crop_z0(month: int) -> float:
    return 0.1 + 0.05 * math.cos((month - 7) / 12 * 2 * math.pi)


def z0_table(month: int) -> np.ndarray:
    """Lookup array indexed by WorldCover class (0..255) → z0 (m)."""
    t = np.full(256, Z0_REF)
    t[80] = 0.0002
    t[70] = 0.001
    t[60] = 0.005
    t[100] = 0.01
    t[30] = 0.03
    t[90] = 0.05
    t[40] = crop_z0(month)
    t[20] = 0.20
    t[50] = 0.70
    t[10] = 1.0
    t[95] = 1.0
    return t


def f_rough(z0_eff, zr: float = RIDER_H):
    z0 = np.clip(z0_eff, 1e-5, Z0_CAP)
    up = math.log(BLEND_H / Z0_REF) / math.log(10 / Z0_REF)
    return up * np.log(zr / z0) / np.log(BLEND_H / z0)


def shelter_r(x, H, phi):
    """Relative speed behind an obstacle (vectorised). x: distance (m), H: height (m), phi: porosity."""
    x = np.asarray(x, dtype=float)
    H = np.asarray(H, dtype=float)
    phi = np.asarray(phi, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        u_min = 0.15 + 0.85 * phi
        L = (12 + 20 * phi) * H
        xh = x / np.where(H > 0, H, 1)
        f = np.where(xh < 3, 0.7 + 0.1 * xh, np.where(x < L, 1 - (x - 3 * H) / np.where(L - 3 * H > 0, L - 3 * H, 1), 0.0))
        f = np.clip(f, 0, 1)
        r = 1 - (1 - u_min) * f
    return np.where(H > 0, r, 1.0)


def is_leaf_on(month: int, day: int, lat: float) -> bool:
    doy = round((month - 1) * 30.44 + day)
    if lat < 0:
        doy = (doy + 182) % 365
    a = abs(lat)
    if a < 23:
        return True
    shift = round((a - 52) / 2 * 7)
    return 105 + shift <= doy < 305 - shift


def porosity(kind: str, leaf_type: str | None, leaf_on: bool) -> float:
    if kind in ("building", "wall"):
        return 0.0
    if kind == "hedge":
        return 0.4
    lt = (leaf_type or "broadleaved").lower()
    if kind == "single_tree":
        return 0.5 if leaf_on or lt == "needleleaved" else 0.7
    if lt == "needleleaved":
        return 0.3
    if lt == "mixed":
        return 0.3 if leaf_on else 0.45
    return 0.3 if leaf_on else 0.6
