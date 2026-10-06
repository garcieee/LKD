import math

import pytest

from models.tickets import settings as s
from models.tickets.matching import geo
from models.tickets.ranking import exposure
from models.tickets.resources.load import load_places

LAT, LNG = 14.5547, 121.0244


def place(metres: float, kind: str = "school") -> tuple:
    """A place this many metres north of the test point."""
    return (LAT + math.degrees(metres / geo.EARTH_RADIUS_M), LNG, kind, "")


def expected(*pulls: tuple[float, float]) -> float:
    """The documented formula, written out again: (weight, distance) pairs."""
    total = sum(w * math.exp(-d / s.EXPOSURE_FADE_M) for w, d in pulls)
    return max(s.EXPOSURE_FLOOR, 1 - math.exp(-total / s.EXPOSURE_SCALE))


@pytest.mark.parametrize("none", [None, []])
def test_no_places_means_no_data_so_the_neutral_default(none):
    assert exposure.foot_traffic(LAT, LNG, none) == s.EXPOSURE_DEFAULT


def test_a_school_on_the_spot_and_one_100_m_away():
    assert exposure.foot_traffic(LAT, LNG, [place(0)]) == pytest.approx(expected((1.0, 0)), abs=1e-6)
    assert exposure.foot_traffic(LAT, LNG, [place(100)]) == pytest.approx(expected((1.0, 100)), abs=1e-4)


def test_places_add_up_and_each_kind_has_its_own_weight():
    got = exposure.foot_traffic(LAT, LNG, [place(50, "school"), place(80, "rail"), place(120, "bus")])
    assert got == pytest.approx(expected((1.0, 50), (0.9, 80), (0.4, 120)), abs=1e-4)
    assert exposure.foot_traffic(LAT, LNG, [place(50, "school")]) > exposure.foot_traffic(LAT, LNG, [place(50, "bus")])


def test_far_places_and_unknown_kinds_leave_only_the_floor():
    assert exposure.foot_traffic(LAT, LNG, [place(s.EXPOSURE_REACH_M + 50)]) == s.EXPOSURE_FLOOR
    assert exposure.foot_traffic(LAT, LNG, [place(10, "casino")]) == s.EXPOSURE_FLOOR


def test_closer_is_busier_more_is_busier_and_the_range_holds():
    by_distance = [exposure.foot_traffic(LAT, LNG, [place(d)]) for d in (0, 40, 100, 200, 290)]
    assert by_distance == sorted(by_distance, reverse=True)
    crowd = [exposure.foot_traffic(LAT, LNG, [place(30 + i) for i in range(n)]) for n in (1, 2, 4, 8)]
    assert crowd == sorted(crowd)
    assert all(s.EXPOSURE_FLOOR <= v < 1 for v in by_distance + crowd)


def test_the_documented_calibration_still_holds_on_the_real_places():
    """150 m grid over the city: median about 0.41 and 90th percentile about 0.83 (see settings.py)."""
    places = load_places()
    south, west, north, east = 14.5296, 120.9987, 14.5796, 121.0501
    step_lat = math.degrees(150 / geo.EARTH_RADIUS_M)
    step_lng = step_lat / math.cos(math.radians(LAT))
    values, lat = [], south
    while lat <= north:
        lng = west
        while lng <= east:
            values.append(exposure.foot_traffic(lat, lng, places))
            lng += step_lng
        lat += step_lat
    values.sort()
    assert len(values) > 1300
    assert 0.36 <= values[len(values) // 2] <= 0.46
    assert 0.78 <= values[int(0.9 * len(values))] <= 0.88


def test_ayala_center_is_busy_and_a_river_corner_is_not():
    places = load_places()
    assert exposure.foot_traffic(14.5498, 121.0279, places) > 0.95  # One Ayala, Robinsons, SM Makati
    assert exposure.foot_traffic(14.5296, 121.0501, places) < 0.4  # south-east corner of the city box
