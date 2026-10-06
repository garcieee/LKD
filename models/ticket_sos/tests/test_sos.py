"""sos.py: the SOS rules the engine uses, and that no hazard's score can climb above an SOS."""
import pytest

from models.ticket_sos import sos
from models.tickets.ranking import priority
from models.tickets.types import CATEGORIES, TicketFacts


def test_three_kinds_in_the_order_the_dashboard_shows_them_with_their_hints():
    assert list(sos.KINDS.items()) == [("police", "Crime, violence or a threat"),
                                       ("medical", "Injury, collapse or illness"),
                                       ("fire_rescue", "Fire, flood or someone trapped")]


def test_only_an_sos_is_an_sos():
    assert sos.is_sos({"category": "sos"})
    assert not any(sos.is_sos({"category": category}) for category in CATEGORIES)


def test_the_flags_are_the_whole_breakdown_with_no_office():
    assert sos.flags(["gps_accuracy_poor"]) == {"sos": True, "review": ["gps_accuracy_poor"]}
    assert sos.flags([]) == {"sos": True, "review": []}


@pytest.mark.parametrize("kind", ["police", "medical", "fire_rescue"])
def test_a_known_kind_passes(kind):
    assert sos.check_kind(kind) == kind


@pytest.mark.parametrize("kind", ["", "Police", "fire-rescue", "fire", "sos", None, 1, ["police"]])
def test_anything_else_is_refused(kind):
    with pytest.raises(ValueError, match="Unknown SOS kind"):
        sos.check_kind(kind)


def test_an_sos_is_critical_and_no_hazard_scores_above_it():
    assert (sos.CATEGORY, sos.PRIORITY, sos.BAND) == ("sos", 100.0, "Critical")
    assert priority.band(sos.PRIORITY) == sos.BAND
    for category in CATEGORIES:  # the worst case: many people, a year open, the busiest street, a danger flag
        worst = TicketFacts(category, reporters=1000, days_open=365.0, foot_traffic=1.0, danger=True)
        assert priority.score(worst).score <= sos.PRIORITY
