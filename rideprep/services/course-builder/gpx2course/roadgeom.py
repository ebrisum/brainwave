"""Road cross-section geometry: superelevation (banking) in bends.

Modelled on the Italian design norm (DM 5/11/2001) and similar rural-road practice: crowned (2.5 % both ways) on
straights and gentle curves, single-slope superelevation q in bends — q grows with the lateral demand V²/(127·R) of
the road class's design speed, from 2.5 % up to q_max = 7 %, reached at the class's minimum radius. Urban/minor
streets, roundabouts and junction turns (R < 30 m) stay crowned. A 15 m Gaussian along the road stands in for the
superelevation run-off. Output: bankDeg per sample, positive = right edge lower (banked for a right-hand bend).
"""
from __future__ import annotations

import math

import numpy as np

from .geo import gaussian_smooth

DESIGN_KMH = {"motorway": 110, "trunk": 90, "primary": 80, "secondary": 70, "tertiary": 60, "unclassified": 50, "road": 50,
              "motorway_link": 60, "trunk_link": 50, "primary_link": 50, "secondary_link": 40, "tertiary_link": 40}
Q_MIN, Q_MAX = 0.025, 0.07
DEMAND_SHARE = 0.5      # share of the lateral demand taken by superelevation (rest by side friction)
CROWN_BELOW = 0.035     # demand below which the road stays crowned
MIN_RADIUS_M = 30.0     # tighter turns: roundabouts, junctions → crowned


def superelevation(heading: np.ndarray, radius: np.ndarray, highway, spacing: float, runoff_sigma_m: float = 15.0) -> np.ndarray:
    n = len(heading)
    v = np.array([DESIGN_KMH.get(str(h or ""), 0) for h in highway], dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        demand = np.where(np.isfinite(radius) & (radius > 0), v * v / (127.0 * radius), 0.0)
    q = np.clip(demand * DEMAND_SHARE, Q_MIN, Q_MAX)
    q = np.where((demand >= CROWN_BELOW) & (radius >= MIN_RADIUS_M) & (v > 0), q, 0.0)
    # Turn direction from the heading change over ±10 m (compass heading grows clockwise → right turn)
    k = max(1, int(round(10.0 / spacing)))
    i = np.arange(n)
    dh = (heading[np.clip(i + k, 0, n - 1)] - heading[np.clip(i - k, 0, n - 1)] + math.pi) % (2 * math.pi) - math.pi
    q = q * np.sign(dh)
    q = gaussian_smooth(q, spacing, runoff_sigma_m)
    return np.degrees(np.arctan(q))


def cross_slope_dz(offset_m: np.ndarray | float, bank_deg: np.ndarray | float, crown: float = 0.02) -> np.ndarray:
    """Height change at a lateral offset (+ right) for a crowned road blended into single-slope superelevation."""
    t = np.tan(np.radians(bank_deg))
    w = np.clip(np.abs(t) / Q_MIN, 0.0, 1.0)
    return (1 - w) * (-crown * np.abs(offset_m)) + w * (-t * offset_m)
