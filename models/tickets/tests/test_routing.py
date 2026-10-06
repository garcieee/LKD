from models.tickets.classification.routing import office_for
from models.tickets.resources.load import load_offices
from models.tickets.types import CATEGORIES

OFFICES = {"pothole": "Roads", "other": "Front desk"}


def test_a_known_category_goes_to_its_office():
    assert office_for("pothole", OFFICES) == "Roads"


def test_an_unknown_category_falls_back_to_other_and_then_to_unassigned():
    assert office_for("sinkhole", OFFICES) == "Front desk"
    assert office_for("sinkhole", {}) == "Unassigned"
    assert office_for("pothole", {"pothole": ""}) == "Unassigned"  # an empty office is no office


def test_the_shipped_table_covers_every_category_and_hides_its_notes():
    offices = load_offices()
    assert set(offices) == set(CATEGORIES)
    assert all(office_for(category, offices) for category in CATEGORIES)
