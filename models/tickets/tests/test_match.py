import math

import pytest

from models.tickets import settings as s
from models.tickets.matching import geo, match
from models.tickets.types import Sighting, TicketSpot

LAT, LNG = 14.5547, 121.0244
DAY = 86_400.0
NOW = 1_800_000_000.0


def north(metres: float) -> float:
    """A latitude this many metres north of LAT."""
    return LAT + math.degrees(metres / geo.EARTH_RADIUS_M)


def report(category="pothole", at=0.0, acc=10.0) -> Sighting:
    return Sighting("new", category, north(at), LNG, accuracy_m=acc)


def ticket(id="t", category="pothole", at=0.0, acc=10.0, status="open", activity=NOW, fixed_at=None) -> TicketSpot:
    return TicketSpot(id, category, north(at), LNG, acc, status, activity, fixed_at)


def test_joins_the_nearest_ticket_inside_the_radius():
    m = match.find_match(report(), [ticket("far", at=25), ticket("near", at=8)], NOW)
    assert m.ticket_id == "near" and m.distance_m == pytest.approx(8, abs=0.05) and not m.reopens


def test_a_different_category_never_joins_and_neither_does_other():
    assert match.find_match(report("open_manhole"), [ticket(category="pothole")], NOW) is None
    assert match.find_match(report("other"), [ticket(category="other")], NOW) is None


def test_outside_the_radius_starts_a_new_ticket_and_the_radius_follows_the_accuracy():
    assert match.find_match(report(acc=20), [ticket(at=40, acc=20)], NOW) is not None  # radius about 58 m
    assert match.find_match(report(acc=5), [ticket(at=40, acc=5)], NOW) is None  # radius about 19 m
    assert match.find_match(report(), [], NOW) is None


def test_a_recently_fixed_ticket_can_be_joined_and_reopens():
    fixed = ticket("old", status="fixed", fixed_at=NOW - 3 * DAY)
    m = match.find_match(report(), [fixed], NOW)
    assert m.ticket_id == "old" and m.reopens


def test_a_ticket_fixed_long_ago_or_without_a_date_is_ignored():
    long_ago = ticket(status="fixed", fixed_at=NOW - (s.REOPEN_WINDOW_DAYS + 1) * DAY)
    undated = ticket(status="fixed", fixed_at=None)
    assert match.find_match(report(), [long_ago, undated], NOW) is None


def test_an_open_ticket_beats_a_closer_fixed_one():
    fixed_close = ticket("fixed", at=1, status="fixed", fixed_at=NOW - DAY)
    open_far = ticket("open", at=15)
    assert match.find_match(report(), [fixed_close, open_far], NOW).ticket_id == "open"


def test_a_tie_goes_to_the_ticket_with_the_most_recent_activity():
    a = ticket("quiet", at=10, activity=NOW - 9 * DAY)
    b = ticket("busy", at=10, activity=NOW - DAY)
    assert match.find_match(report(), [a, b], NOW).ticket_id == "busy"
    assert match.find_match(report(), [b, a], NOW).ticket_id == "busy"


def test_possible_duplicates_lists_what_staff_may_merge_but_not_what_is_already_merged():
    merged = ticket("merged", at=10)  # inside the radius, same category: find_match takes it
    other_kind = ticket("manhole", category="open_manhole", at=10)
    just_past = ticket("past", at=45)  # same category, beyond 31 m, inside 2 x 31 m
    too_far = ticket("far", at=90)
    got = match.possible_duplicates(report(), [merged, other_kind, just_past, too_far], NOW)
    assert [m.ticket_id for m in got] == ["manhole", "past"]


def test_possible_duplicates_is_sorted_and_capped():
    near = [ticket(f"t{i}", category="open_manhole", at=i + 1) for i in range(8)]
    got = match.possible_duplicates(report(), near[::-1], NOW, limit=3)
    assert [m.ticket_id for m in got] == ["t0", "t1", "t2"]


def test_the_anchor_is_the_most_accurate_sighting():
    spot = ticket(at=0, acc=15)
    better = Sighting("s", "pothole", north(5), LNG, accuracy_m=6)
    worse = Sighting("s", "pothole", north(5), LNG, accuracy_m=30)
    unknown = Sighting("s", "pothole", north(5), LNG, accuracy_m=None)
    assert match.anchor_after(spot, better) == (north(5), LNG, 6)
    assert match.anchor_after(spot, worse) == (spot.lat, spot.lng, 15)
    assert match.anchor_after(spot, unknown) == (spot.lat, spot.lng, 15)
    assert match.anchor_after(ticket(acc=None), worse)[2] == 30  # any real accuracy beats none
