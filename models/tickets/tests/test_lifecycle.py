import pytest

from models.tickets import settings as s
from models.tickets.ranking import lifecycle as life


def test_a_fresh_single_report_is_80_percent_sure_and_nobody_at_all_is_75():
    assert life.belief(1, 0) == pytest.approx(0.8)
    assert life.belief(0, 0) == pytest.approx(0.75)


def test_belief_rises_with_yes_falls_with_no_and_stays_a_probability():
    ups = [life.belief(n, 0) for n in range(0, 12)]
    downs = [life.belief(1, n) for n in range(0, 12)]
    assert ups == sorted(ups) and downs == sorted(downs, reverse=True)
    assert all(0 < b < 1 for b in ups + downs)
    assert life.belief(-3, -2) == life.belief(0, 0)  # nonsense counts are treated as zero


def test_the_gate_is_open_for_a_fresh_report_and_never_below_its_floor():
    assert life.gate(life.belief(1, 0)) == 1.0
    assert life.gate(0.0) == s.GATE_MIN and life.gate(s.GATE_LOW) == s.GATE_MIN
    assert life.gate(1.0) == 1.0
    gates = [life.gate(b / 20) for b in range(0, 21)]
    assert gates == sorted(gates) and all(s.GATE_MIN <= g <= 1 for g in gates)


@pytest.mark.parametrize("yes, no, gone", [(1, 0, False), (1, 3, False), (1, 5, True), (4, 8, True), (6, 3, False)])
def test_likely_gone_needs_clearly_more_no_than_yes(yes, no, gone):
    assert life.likely_gone(life.belief(yes, no)) is gone


def test_only_low_danger_tickets_go_stale_and_only_after_the_wait():
    assert life.is_stale("blocked_sidewalk", s.STALE_DAYS) and life.is_stale("other", 90)
    assert not life.is_stale("blocked_sidewalk", s.STALE_DAYS - 0.1)
    assert not life.is_stale("pothole", 365) and not life.is_stale("open_manhole", 365)
    assert life.is_stale("never-heard-of-it", s.STALE_DAYS)  # unknown categories count as "other"
