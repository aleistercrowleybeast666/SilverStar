"""Origin-local WGS84 conversion shared by receiver-native diagnostics."""
from __future__ import annotations

import math

import numpy as np

_WGS84_A_M = 6378137.0
_WGS84_INV_F = 298.257223563
_RAD_PER_E7 = math.pi / (180.0 * 10_000_000.0)


def GeoLocal_ToEnu(
    lat_e7: np.ndarray, lon_e7: np.ndarray, height_mm: np.ndarray,
    origin: tuple[int, int, int],
) -> np.ndarray:
    """Match the firmware's origin-local WGS84 curvature and height convention."""
    origin_lat, origin_lon, origin_height = origin
    if not (-900_000_000 <= origin_lat <= 900_000_000
            and -1_800_000_000 <= origin_lon <= 1_800_000_000):
        raise ValueError("gnss_origin_invalid")
    flattening = 1.0 / _WGS84_INV_F
    eccentricity_squared = flattening * (2.0 - flattening)
    latitude = origin_lat * _RAD_PER_E7
    sin_lat = math.sin(latitude)
    denominator = 1.0 - eccentricity_squared * sin_lat * sin_lat
    prime_vertical = _WGS84_A_M / math.sqrt(denominator)
    meridian = _WGS84_A_M * (1.0 - eccentricity_squared) / denominator ** 1.5
    origin_height_m = origin_height * .001
    east_scale = (prime_vertical + origin_height_m) * math.cos(latitude) * _RAD_PER_E7
    north_scale = (meridian + origin_height_m) * _RAD_PER_E7
    if east_scale <= 0 or north_scale <= 0:
        raise ValueError("gnss_origin_invalid")
    delta_lon = np.asarray(lon_e7, dtype=np.int64) - origin_lon
    delta_lon = np.where(delta_lon > 1_800_000_000, delta_lon - 3_600_000_000, delta_lon)
    delta_lon = np.where(delta_lon < -1_800_000_000, delta_lon + 3_600_000_000, delta_lon)
    return np.column_stack((
        delta_lon * east_scale,
        (np.asarray(lat_e7, dtype=np.int64) - origin_lat) * north_scale,
        (np.asarray(height_mm, dtype=np.int64) - origin_height) * .001,
    ))
