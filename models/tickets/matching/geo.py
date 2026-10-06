"""Distance in metres, the search box for the database, and the accuracy-aware match radius.

Two readings of the same hazard differ by GPS error plus where each person stood. Android reports accuracy
as a 68% radius, so sigma = accuracy / 1.51 per axis, and the readings are closer than
MATCH_Z * sqrt(sigma_a**2 + sigma_b**2 + 2 * stand_off**2) with the confidence MATCH_Z stands for (3.03 is 99%).
"""
import math

from .. import settings as s

EARTH_RADIUS_M = 6_371_008.8


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def box(lat: float, lng: float, radius_m: float) -> tuple[float, float, float, float]:
    """(south, west, north, east) in degrees: a box that contains the circle, for the database's R*Tree."""
    dlat = math.degrees(radius_m / EARTH_RADIUS_M)
    dlng = dlat / max(math.cos(math.radians(lat)), 1e-6)
    return lat - dlat, lng - dlng, lat + dlat, lng + dlng


def sigma_m(accuracy_m: float | None) -> float:
    """Per-axis GPS error from the phone's accuracy. Missing, zero, negative or non-finite means the default."""
    ok = accuracy_m is not None and math.isfinite(accuracy_m) and accuracy_m > 0
    return (accuracy_m if ok else s.DEFAULT_ACCURACY_M) / s.ACCURACY_TO_SIGMA


def match_radius_m(accuracy_a: float | None, accuracy_b: float | None) -> float:
    """How close two readings of the same hazard will be, with the confidence of MATCH_Z."""
    sa, sb = sigma_m(accuracy_a), sigma_m(accuracy_b)
    radius = s.MATCH_Z * math.sqrt(sa * sa + sb * sb + 2 * s.STAND_OFF_SIGMA_M**2)
    return min(s.MATCH_MAX_M, max(s.MATCH_MIN_M, radius))


def match_ratio(lat1: float, lng1: float, acc1: float | None, lat2: float, lng2: float, acc2: float | None) -> float:
    """Distance divided by the match radius: 1 or less means the same place. The continuous score for ROC and PR curves."""
    return distance_m(lat1, lng1, lat2, lng2) / match_radius_m(acc1, acc2)
