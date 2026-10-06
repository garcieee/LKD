"""The settings are the one place numbers live, so check that they hang together."""
from models.tickets import settings as s

CATEGORIES = {"pothole", "open_manhole", "flooded_drain", "broken_streetlight", "blocked_sidewalk", "other"}


def fresh_report_belief() -> float:
    yes, no = s.BELIEF_PRIOR
    return (yes + 1) / (yes + no + 1)  # one reporter counts as one yes


def test_weights_are_positive_and_sum_to_one():
    assert set(s.WEIGHTS) == {"danger", "reports", "foot_traffic", "waiting"}
    assert all(w > 0 for w in s.WEIGHTS.values())
    assert abs(sum(s.WEIGHTS.values()) - 1) < 1e-9


def test_every_category_has_a_danger_value_between_0_and_1():
    assert set(s.SEVERITY) == CATEGORIES
    assert all(0 < v <= 1 for v in s.SEVERITY.values())


def test_floors_are_for_known_categories_and_stay_below_critical():
    # A lone report must never be Critical by floor alone: Critical needs people to confirm it.
    assert set(s.FLOORS) <= set(s.SEVERITY)
    assert all(0 < f < dict(s.BANDS)["Critical"] for f in s.FLOORS.values())


def test_bands_descend_to_zero():
    thresholds = [t for _, t in s.BANDS]
    assert thresholds == sorted(thresholds, reverse=True) and len(set(thresholds)) == len(thresholds)
    assert thresholds[-1] == 0 and len({name for name, _ in s.BANDS}) == len(s.BANDS)


def test_match_radius_limits_make_sense():
    assert 0 < s.MATCH_MIN_M < s.MATCH_MAX_M
    assert s.MATCH_Z > 0 and s.ACCURACY_TO_SIGMA > 0 and s.STAND_OFF_SIGMA_M >= 0
    assert s.MATCH_MIN_M <= s.DEFAULT_ACCURACY_M <= s.MATCH_MAX_M
    assert s.SUGGEST_RADIUS_M > s.MATCH_MAX_M  # suggest wider than we auto-merge


def test_a_fresh_single_report_is_not_penalised_by_the_belief_gate():
    belief = fresh_report_belief()
    gate = min(1.0, max(s.GATE_MIN, (belief - s.GATE_LOW) / s.GATE_SPAN))
    assert gate == 1.0
    assert 0 < s.GATE_MIN < 1 and s.GATE_LOW >= 0 and s.GATE_LOW + s.GATE_SPAN <= 1


def test_likely_gone_and_stale_thresholds_sit_where_they_should():
    assert 0 < s.LIKELY_GONE_BELOW < fresh_report_belief()
    assert s.STALE_DAYS > s.WAITING_FULL_DAYS  # stale only after the waiting part has maxed out
    # sidewalks and "other" can go stale, potholes and worse never do
    assert s.SEVERITY["blocked_sidewalk"] < s.STALE_BELOW_DANGER <= s.SEVERITY["pothole"]


def test_foot_traffic_settings():
    assert all(0 < w <= 1 for w in s.EXPOSURE_WEIGHTS.values())
    assert 0 < s.EXPOSURE_FLOOR < s.EXPOSURE_DEFAULT < 1
    assert s.EXPOSURE_REACH_M > s.EXPOSURE_FADE_M > 0 and s.EXPOSURE_SCALE > 0


def test_loop_settings():
    assert s.SYNC_EVERY_S > 0 and s.SYNC_MAX_TRIES >= 1
    # Matching reads the cache, so a fixed ticket must stay there for as long as a new report can still reopen it.
    assert s.CACHE_KEEP_DAYS >= s.REOPEN_WINDOW_DAYS
