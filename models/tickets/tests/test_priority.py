import random

import pytest

from models.tickets import settings as s
from models.tickets.ranking import priority
from models.tickets.types import CATEGORIES, TicketFacts


def facts(category="pothole", n=1, gone=0, days=0.0, x=0.5, danger=False) -> TicketFacts:
    return TicketFacts(category, n, gone, days, x, danger)


def score(**k) -> float:
    return priority.score(facts(**k)).score


# Cases a sensible person agrees on: A must outrank B. They came out of models/tickets/sim/sim_rank.py.
RANKING_CASES = [
    ("open manhole beats pothole, one report each, busy", dict(category="open_manhole", x=0.9), dict(x=0.9)),
    ("6 reporters beat 1", dict(n=6, x=0.8, days=5), dict(n=1, x=0.8, days=5)),
    ("busy street beats quiet street", dict(x=0.9), dict(x=0.2)),
    ("12 days waiting beats 1 day", dict(days=12), dict(days=1)),
    ("lone manhole on a quiet street beats a busy streetlight with 3 reports", dict(category="open_manhole", x=0.2), dict(category="broken_streetlight", n=3, x=0.9, days=3)),
    ("no 'gone' votes beats 3 'gone' votes", dict(), dict(gone=3)),
    ("flooded drain with a danger flag beats a pothole with 4 reports", dict(category="flooded_drain", x=0.6, danger=True), dict(n=4, x=0.6)),
    ("blocked sidewalk, 8 reports, busy beats a lone pothole on a quiet street", dict(category="blocked_sidewalk", n=8, x=0.9, days=4), dict(x=0.2)),
]


@pytest.mark.parametrize("name, a, b", RANKING_CASES, ids=[c[0] for c in RANKING_CASES])
def test_ranking_cases(name, a, b):
    assert score(**a) > score(**b)


@pytest.mark.parametrize(
    "kwargs, expected, band",
    [
        (dict(category="open_manhole", x=0.9), 66.2, "High"),
        (dict(category="open_manhole", n=3, x=0.9, days=1), 77.6, "Critical"),
        (dict(n=5, x=0.8, days=6), 67.5, "High"),
        (dict(x=0.2), 36.1, "Low"),
        (dict(category="broken_streetlight", n=2, x=0.5, days=14), 55.2, "High"),
        (dict(gone=3), 16.6, "Low"),
    ],
)
def test_example_scores(kwargs, expected, band):
    got = priority.score(facts(**kwargs))
    assert got.score == pytest.approx(expected, abs=0.1) and got.band == band


def test_the_floor_lifts_a_lone_manhole_but_never_to_critical():
    got = priority.score(facts(category="open_manhole", x=0.2))
    assert got.floor_applied and got.score == pytest.approx(s.FLOORS["open_manhole"]) and got.band == "High"
    assert not priority.score(facts(category="pothole", x=0.2)).floor_applied


def test_the_floor_shrinks_when_people_say_it_is_gone():
    sure = priority.score(facts(category="open_manhole", x=0.2)).score
    doubted = priority.score(facts(category="open_manhole", x=0.2, gone=6)).score
    assert doubted < sure * 0.6


def test_bands_change_exactly_at_their_thresholds():
    assert [priority.band(v) for v in (0, 39.99, 40, 54.99, 55, 69.99, 70, 100)] == [
        "Low", "Low", "Medium", "Medium", "High", "High", "Critical", "Critical"]


def test_the_breakdown_explains_the_score():
    b = priority.score(facts(category="open_manhole", n=4, days=7, x=0.8, danger=True))
    assert set(b.parts) == {"danger", "reports", "foot_traffic", "waiting"} and all(0 <= v <= 1 for v in b.parts.values())
    assert b.parts["reports"] == pytest.approx(2 / 3) and b.parts["waiting"] == pytest.approx(0.5)
    assert b.bonus == s.DANGER_BONUS and b.band == priority.band(b.score)
    raw = 100 * b.gate * sum(s.WEIGHTS[k] * v for k, v in b.parts.items())
    assert b.score == pytest.approx(min(100, max(raw, b.gate * s.FLOORS["open_manhole"]) + b.bonus))


def test_odd_inputs_are_handled():
    assert score(category="made-up") == score(category="other")  # unknown category counts as "other"
    assert score(n=0) == score(n=1)  # nobody still means the one who reported it
    assert score(x=7.0) == score(x=1.0) and score(x=-1.0) == score(x=0.0) and score(days=-5) == score(days=0)


def test_more_evidence_never_lowers_the_score_and_more_doubt_never_raises_it():
    rng = random.Random(3)
    for _ in range(5000):
        k = dict(category=rng.choice(CATEGORIES), n=rng.randint(1, 12), gone=rng.randint(0, 6),
                 days=rng.uniform(0, 30), x=rng.random(), danger=rng.random() < 0.3)
        base = score(**k)
        assert 0 <= base <= 100
        assert score(**{**k, "n": k["n"] + 1}) >= base - 1e-9
        assert score(**{**k, "days": k["days"] + 1}) >= base - 1e-9
        assert score(**{**k, "x": min(1, k["x"] + 0.1)}) >= base - 1e-9
        assert score(**{**k, "gone": k["gone"] + 1}) <= base + 1e-9
        assert score(**{**k, "danger": True}) >= base - 1e-9
