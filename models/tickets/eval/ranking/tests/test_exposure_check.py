import numpy as np

from models.tickets import settings as s
from models.tickets.eval.ranking import exposure_check as X

PLACES = [(14.5500, 121.0200, "school", "A"), (14.5600, 121.0300, "mall", "B")]


def test_traffic_at_changes_the_scale_only_inside_the_call():
    point = [(14.5502, 121.0201)]
    busy, calm = X.traffic_at(point, PLACES, 0.5)[0], X.traffic_at(point, PLACES, 2.0)[0]
    assert busy > calm > s.EXPOSURE_FLOOR  # a smaller scale squashes less, so the same pull reads busier
    assert s.EXPOSURE_SCALE == 1.0


def test_dedupe_folds_same_kind_neighbours_into_the_named_one():
    places = [(14.55001, 121.02001, "rail", ""), (14.5500, 121.0200, "rail", "Station"),  # 1.5 m apart: one station
              (14.5500, 121.0200, "school", "Next door"), (14.5600, 121.0300, "rail", "Far")]  # other kind, other place: kept
    assert {p[3] for p in X.dedupe(places)} == {"Station", "Next door", "Far"}


def test_top_spots_keeps_spots_apart_and_names_the_nearest_place():
    points = [(14.5500, 121.0200), (14.5501, 121.0201), (14.5600, 121.0300)]  # the first two are 15 m apart
    spots = X.top_spots(points, np.array([0.9, 0.8, 0.7]), PLACES, count=3)
    assert [round(p["foot_traffic"], 1) for p in spots] == [0.9, 0.7]
    assert spots[0]["nearest"][0]["name"] == "A" and spots[1]["nearest"][0]["name"] == "B"
