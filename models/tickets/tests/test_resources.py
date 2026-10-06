import json
from pathlib import Path

from models.tickets import settings as s
from models.tickets.resources.load import load_places

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def test_places_are_within_reach_of_the_city_box_and_every_kind_has_a_weight():
    places = load_places()
    assert len(places) == 719
    # OpenStreetMap returns what touches the box, so a campus centre can sit just outside it. Anything farther
    # than the foot-traffic reach could not affect a ticket inside the city anyway.
    pad = s.EXPOSURE_REACH_M / 111_195
    south, west, north, east = 14.5296 - pad, 120.9987 - pad, 14.5796 + pad, 121.0501 + pad
    assert all(south <= lat <= north and west <= lng <= east for lat, lng, _, _ in places)
    assert {kind for _, _, kind, _ in places} <= set(s.EXPOSURE_WEIGHTS)


def test_the_lexicon_has_every_category_and_only_usable_terms():
    from models.tickets.classification.classify import tokens
    from models.tickets.resources.load import load_lexicon
    from models.tickets.types import CATEGORIES

    lexicon = load_lexicon()
    assert set(lexicon["categories"]) == set(CATEGORIES)
    every_term = [t for terms in lexicon["categories"].values() for t in terms] + lexicon["danger"] + lexicon["negators"]
    assert all(tokens(t) for t in every_term)  # nothing that normalises to nothing
    for terms in [*lexicon["categories"].values(), lexicon["danger"]]:
        normal = [" ".join(tokens(t)) for t in terms]
        assert len(normal) == len(set(normal))  # no repeats inside one list


def test_places_file_credits_openstreetmap():
    meta = json.loads((RESOURCES / "places.json").read_text())
    assert "OpenStreetMap" in meta["source"] and "ODbL" in meta["source"]
