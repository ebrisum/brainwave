"""The one place where package ENU metres are converted to/from Unreal Engine coordinates.

Package: right-handed ENU in metres (x east, y north, z up). Unreal: left-handed, Z-up, centimetres, X forward.
UE.X = E·100, UE.Y = −N·100, UE.Z = U·100 (matches CesiumGeoreference's ENU→UE convention with X=east, Y=south).
"""
from __future__ import annotations

import numpy as np

CM = 100.0


def enu_to_ue(x, y, z):
    return np.asarray(x, dtype=np.float64) * CM, -np.asarray(y, dtype=np.float64) * CM, np.asarray(z, dtype=np.float64) * CM


def ue_to_enu(X, Y, Z):
    return np.asarray(X, dtype=np.float64) / CM, -np.asarray(Y, dtype=np.float64) / CM, np.asarray(Z, dtype=np.float64) / CM


def compass_to_ue_yaw_deg(bearing_rad):
    """Compass bearing (clockwise from north) → UE yaw in degrees (rotation about Z from +X toward +Y)."""
    return np.degrees(np.asarray(bearing_rad)) - 90.0
