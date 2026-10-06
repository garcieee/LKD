import math

import pytest

from models.tickets import settings as s
from models.tickets.matching import geo

AYALA = (14.5547, 121.0244)


def test_distance_to_itself_is_zero_and_symmetric():
    assert geo.distance_m(*AYALA, *AYALA) == 0
    a, b = (14.5547, 121.0244), (14.5600, 121.0300)
    assert geo.distance_m(*a, *b) == pytest.approx(geo.distance_m(*b, *a))


def test_distance_matches_known_lengths():
    assert geo.distance_m(0, 0, 1, 0) == pytest.approx(111_195, abs=60)  # one degree of latitude
    assert geo.distance_m(14.5547, 121.0244, 14.5548, 121.0244) == pytest.approx(11.12, abs=0.05)  # 0.0001 deg
    # a degree of longitude is shorter by cos(latitude)
    assert geo.distance_m(14.5547, 121.0, 14.5547, 121.001) == pytest.approx(111_195 * math.cos(math.radians(14.5547)) / 1000, abs=0.2)


def test_the_box_contains_the_circle_and_is_not_much_bigger():
    r = 60.0
    south, west, north, east = geo.box(*AYALA, r)
    assert south < AYALA[0] < north and west < AYALA[1] < east
    for bearing in range(0, 360, 15):
        # a point 0.99 r away in this direction must be inside the box
        dlat = 0.99 * r * math.cos(math.radians(bearing)) / 111_320
        dlng = 0.99 * r * math.sin(math.radians(bearing)) / (111_320 * math.cos(math.radians(AYALA[0])))
        assert south <= AYALA[0] + dlat <= north and west <= AYALA[1] + dlng <= east
    assert geo.distance_m(south, AYALA[1], north, AYALA[1]) == pytest.approx(2 * r, rel=0.01)


@pytest.mark.parametrize("bad", [None, 0, -5, float("nan"), float("inf")])
def test_a_missing_or_nonsense_accuracy_means_the_default(bad):
    assert geo.sigma_m(bad) == geo.sigma_m(s.DEFAULT_ACCURACY_M)


@pytest.mark.parametrize(
    "acc_a, acc_b, expected",
    [(10, 10, 31.1), (5, 5, 19.1), (20, 20, 58.2), (10, 20, 46.7)],  # 3.03 * sqrt(sa^2 + sb^2 + 2 * 3^2), by hand
)
def test_match_radius_for_typical_accuracies(acc_a, acc_b, expected):
    assert geo.match_radius_m(acc_a, acc_b) == pytest.approx(expected, abs=0.3)


def test_match_radius_is_clamped_symmetric_and_grows_with_error():
    assert geo.match_radius_m(1, 1) == s.MATCH_MIN_M
    assert geo.match_radius_m(500, 500) == s.MATCH_MAX_M
    assert geo.match_radius_m(8, 25) == pytest.approx(geo.match_radius_m(25, 8))
    radii = [geo.match_radius_m(a, 10) for a in (3, 6, 10, 15, 25, 40)]
    assert radii == sorted(radii)
    assert geo.match_radius_m(None, None) == pytest.approx(geo.match_radius_m(s.DEFAULT_ACCURACY_M, s.DEFAULT_ACCURACY_M))


def test_match_ratio_is_zero_on_the_spot_and_one_at_the_radius():
    assert geo.match_ratio(*AYALA, 10, *AYALA, 10) == 0
    r = geo.match_radius_m(10, 10)
    lat_at_radius = AYALA[0] + r / 111_320
    assert geo.match_ratio(*AYALA, 10, lat_at_radius, AYALA[1], 10) == pytest.approx(1.0, abs=0.01)
