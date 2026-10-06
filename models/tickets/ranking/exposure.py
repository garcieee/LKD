"""Foot traffic around a point, from nearby schools, clinics, stations, malls and markets.

Each place within EXPOSURE_REACH_M pulls with its kind's weight, fading like exp(-distance / EXPOSURE_FADE_M).
The pulls add up and are squashed into 0..1 with 1 - exp(-sum / EXPOSURE_SCALE). Nowhere is quite zero.
"""
import math

from .. import settings as s
from ..matching.geo import EARTH_RADIUS_M, distance_m


def foot_traffic(lat: float, lng: float, places) -> float:
    """0..1 from places given as (lat, lng, kind, ...). No places at all means no data: the neutral default."""
    if not places:
        return s.EXPOSURE_DEFAULT
    dlat = math.degrees(s.EXPOSURE_REACH_M / EARTH_RADIUS_M)
    dlng = dlat / max(math.cos(math.radians(lat)), 1e-6)
    total = 0.0
    for place in places:
        plat, plng, kind = place[0], place[1], place[2]
        weight = s.EXPOSURE_WEIGHTS.get(kind)
        if not weight or abs(plat - lat) > dlat or abs(plng - lng) > dlng:  # cheap box test before the real distance
            continue
        d = distance_m(lat, lng, plat, plng)
        if d <= s.EXPOSURE_REACH_M:
            total += weight * math.exp(-d / s.EXPOSURE_FADE_M)
    return max(s.EXPOSURE_FLOOR, 1 - math.exp(-total / s.EXPOSURE_SCALE))
