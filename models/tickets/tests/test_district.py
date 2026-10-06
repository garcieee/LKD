"""district_of on the shipped boundaries (resources/districts.json) and on shapes small enough to check by eye.

Each point below was computed from districts.json (the middle of the barangay's widest span across its middle
latitude) and checked to lie in that barangay and in no other."""
import math

import pytest

from models.tickets.classification.routing import district_of
from models.tickets.resources.load import load_districts

DISTRICTS = load_districts()
INSIDE = [
    ("Bangkal", 14.54383, 121.01405, 1),
    ("Bel-Air", 14.56065, 121.02157, 1),
    ("Carmona", 14.57551, 121.01877, 1),
    ("Dasmariñas", 14.54118, 121.02592, 1),
    ("Forbes Park", 14.54627, 121.03903, 1),
    ("Kasilawan", 14.5772, 121.01504, 1),
    ("La Paz", 14.56893, 121.00888, 1),
    ("Magallanes", 14.53586, 121.01786, 1),
    ("Olympia", 14.57196, 121.02123, 1),
    ("Palanan", 14.56043, 121.00256, 1),
    ("Pio del Pilar", 14.55434, 121.01207, 1),
    ("Poblacion", 14.5676, 121.02888, 1),
    ("San Antonio", 14.56251, 121.01022, 1),
    ("San Isidro", 14.55399, 121.00531, 1),
    ("San Lorenzo", 14.55168, 121.02169, 1),
    ("Santa Cruz", 14.56747, 121.01546, 1),
    ("Singkamas", 14.57228, 121.01067, 1),
    ("Tejeros", 14.57173, 121.01365, 1),
    ("Urdaneta", 14.55584, 121.02957, 1),
    ("Valenzuela", 14.57017, 121.02336, 1),
    ("Guadalupe Nuevo", 14.56278, 121.04692, 2),
    ("Guadalupe Viejo", 14.5643, 121.04156, 2),
    ("Pinagkaisahan", 14.55781, 121.0404, 2),
]


@pytest.mark.parametrize("name, lat, lng, district", INSIDE)
def test_a_point_inside_each_barangay_gets_its_district(name, lat, lng, district):
    assert district_of(lat, lng, DISTRICTS) == district
    assert [b[1] for b in DISTRICTS if district_of(lat, lng, [b]) is not None] == [name]  # that barangay alone


def test_the_file_holds_the_23_barangays_of_makati_after_the_embo_ruling():
    districts = {name: d for d, name, _, _ in DISTRICTS}
    assert len(DISTRICTS) == 23 and set(districts) == {name for name, *_ in INSIDE}
    assert sorted(name for name, d in districts.items() if d == 2) == ["Guadalupe Nuevo", "Guadalupe Viejo", "Pinagkaisahan"]
    assert all(ring[0] == ring[-1] and len(ring) >= 4 for *_, rings in DISTRICTS for ring in rings)


@pytest.mark.parametrize("lat, lng", [
    (14.5508, 121.0509),  # Bonifacio Global City, Taguig
    (14.5500, 120.9500),  # Manila Bay
    (14.56567, 121.0194),  # the Manila South Cemetery: the City of Manila's exclave inside Makati
    (math.nan, 121.02),
])
def test_places_outside_makati_have_no_district(lat, lng):
    assert district_of(lat, lng, DISTRICTS) is None


def test_the_box_only_narrows_the_search_the_ring_decides():
    # An L in [lng, lat]: the notch at the top right is inside the box but outside the shape.
    ell = [[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2], [0, 0]]
    shapes = [(7, "L", (0.0, 0.0, 2.0, 2.0), [ell])]
    assert district_of(0.5, 1.5, shapes) == 7 and district_of(1.5, 0.5, shapes) == 7  # both arms
    assert district_of(1.5, 1.5, shapes) is None  # the notch
    assert district_of(0.5, 2.5, shapes) is None and district_of(-0.1, 0.5, shapes) is None
