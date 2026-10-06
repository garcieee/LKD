import numpy as np
import pytest

from models.tickets.eval.matching.chicago import pairs, prepare
from models.tickets.matching import geo

from . import fixtures as fx


def test_positives_are_the_cities_duplicates_with_a_located_parent_in_the_same_group():
    req = fx.requests()
    child, parent, funnel = pairs.positive_pairs(req, fx.groups(req))
    assert {(req.sr[c], req.sr[p]) for c, p in zip(child, parent)} == {("B", "A"), ("C", "A"), ("G", "F"), ("Q", "R")}
    assert funnel == {"duplicates": 6 + 1, "parent_not_in_file": 1, "no_location": 1, "crosses_a_boundary": 1, "kept": 4}


def test_near_negatives_are_open_tickets_under_60_m_in_the_same_group_that_are_not_the_parent():
    req = fx.requests()
    old, new, d = pairs.near_pairs(req, fx.groups(req))
    got = {(req.sr[n], req.sr[o]): dist for o, n, dist in zip(old, new, d)}
    assert got.keys() == {("D", "A"), ("I", "A"), ("I", "D"), ("J", "I"), ("J", "D"), ("H", "I"), ("L", "I"), ("L", "H"), ("N", "K")}
    assert got[("D", "A")] == pytest.approx(30, abs=0.05) and got[("J", "D")] == pytest.approx(50, abs=0.05)
    assert got[("N", "K")] == pytest.approx(3, abs=0.05)
    # left out on purpose: A and D after they closed (H), a duplicate as the other (B, C, G, Q), the parent (B-A, C-A),
    # J-A at 80 m, and K-I (45 m) because K is in another group than I


def test_a_report_may_not_match_a_ticket_that_closed_before_it_arrived_and_a_group_boundary_is_never_crossed():
    req = fx.requests()
    old, new, _ = pairs.near_pairs(req, fx.groups(req))
    got = {(req.sr[n], req.sr[o]) for o, n in zip(old, new)}
    assert ("H", "A") not in got and ("H", "D") not in got  # both closed on day 10, H arrived on day 12
    assert ("K", "I") not in got and ("K", "A") not in got  # K is in group 1


def test_if_any_request_may_be_the_other_the_near_set_gains_the_pairs_with_a_duplicate_as_the_other():
    req = fx.requests()
    ticket = pairs.near_pairs(req, fx.groups(req))
    anyone = pairs.near_pairs(req, fx.groups(req), tickets_only=False)
    names = lambda t: {(req.sr[n], req.sr[o]) for o, n in zip(t[0], t[1])}
    # B (10 m) and C (20 m) are duplicates of A and open until day 10, so D (30 m) and I (50 m) are now near them too
    assert names(anyone) - names(ticket) == {("D", "B"), ("D", "C"), ("I", "B"), ("I", "C")} and names(ticket) <= names(anyone)
    both = pairs.build(req, fx.groups(req), near_tickets_only=False)
    assert int((both["kind"] == pairs.KINDS["near"]).sum()) == 13 and len(pairs.build(req, fx.groups(req))["d"]) == 15


def test_far_negatives_are_open_tickets_100_to_500_m_from_a_positive_child():
    req = fx.requests()
    old, new, d = pairs.far_pairs(req, fx.groups(req), pairs.positive_pairs(req, fx.groups(req))[0], per_pivot=5)
    got = {(req.sr[n], req.sr[o]) for o, n in zip(old, new)}
    assert got == {("G", "A"), ("G", "D"), ("G", "E"), ("Q", "E"), ("Q", "F")}
    assert d.min() >= 100 and d.max() <= 500
    one = pairs.far_pairs(req, fx.groups(req), pairs.positive_pairs(req, fx.groups(req))[0], per_pivot=1)
    assert len(one[0]) == 2 and {req.sr[n] for n in one[1]} == {"G", "Q"}  # B and C have no candidate, G and Q get one each


def test_build_labels_distances_time_gaps_and_origin():
    req = fx.requests()
    data = pairs.build(req, fx.groups(req))
    assert len(data["d"]) == 4 + 2 + 9
    assert int(data["label"].sum()) == 4 and set(data["kind"]) == {0, 1, 2}
    by = {(req.sr[c], req.sr[o]): i for i, (c, o) in enumerate(zip(data["child"], data["other"]))}
    b_a, c_a, q_r = by[("B", "A")], by[("C", "A")], by[("Q", "R")]
    assert data["d"][b_a] == pytest.approx(10, abs=0.05) and data["d"][c_a] == pytest.approx(20, abs=0.05)
    assert data["dt"][b_a] == pytest.approx(1) and data["dt"][c_a] == pytest.approx(2)
    assert data["dt_signed"][q_r] == pytest.approx(-1) and data["dt"][q_r] == pytest.approx(1)  # the parent came a day LATER
    assert data["origin"][b_a] == "Mobile Device" and data["origin"][by[("I", "A")]] == "Phone Call"
    assert (data["dt"] >= 0).all() and np.array_equal(data["group"], fx.groups(req)[data["child"]])
    assert set(data["group"][data["kind"] == 2]) == {0, 1}


def test_no_request_sits_in_two_groups_and_both_ends_of_a_pair_share_one():
    req = fx.requests()
    g = fx.groups(req)
    data = pairs.build(req, g)
    assert (g[data["child"]] == g[data["other"]]).all()
    assert (g[data["child"]] >= 0).all()


def test_the_distance_is_the_matchers_own_haversine():
    req = fx.requests()
    a, b = np.array([0, 1]), np.array([3, 5])
    for x, y, got in zip(a, b, pairs.metres(req, a, b)):
        assert got == geo.distance_m(req.lat[x], req.lng[x], req.lat[y], req.lng[y])


def test_build_all_pools_categories_and_building_twice_gives_the_same_pairs():
    req = fx.requests()
    other = prepare.from_rows("broken_streetlight", fx.rows())
    everything = {"pothole": req, "broken_streetlight": other}
    groups = {c: fx.groups(r) for c, r in everything.items()}
    one, two = pairs.build_all(everything, groups), pairs.build_all(everything, groups)
    assert set(one["category"]) == {"pothole", "broken_streetlight"} and len(one["d"]) == 2 * 15
    assert all(np.array_equal(one[k], two[k]) for k in one)


def test_buffer_counts_use_the_street_numbers():
    req = fx.requests()
    row = {sr: i for i, sr in enumerate(req.sr)}
    got = pairs.buffer_counts(req, np.array([row["B"], row["C"], row["D"], row["E"]]), np.array([row["A"]] * 4))
    assert got == {"inside": 1, "outside": 2, "no_number": 1}  # B 102 vs A 100 yes; C 108 no; D another street; E has no address


def test_a_request_in_two_groups_is_caught():
    req = fx.requests()
    data = pairs.build(req, fx.groups(req))
    data["category"] = np.full(len(data["d"]), "pothole")
    assert pairs.requests_in_two_groups(data) == 0
    data["group"] = data["group"].copy()
    data["group"][data["child"] == data["child"][0]] = 1 - data["group"][0]  # move every pair of one child to the other group
    assert pairs.requests_in_two_groups(data) >= 1


def test_the_split_manifest_lists_every_request_with_its_two_splits(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare, "CACHE", tmp_path)
    req = fx.requests()
    path = pairs.write_manifest({"pothole": req})
    with np.load(path) as z:
        assert list(z["pothole_sr"]) == list(req.sr)
        assert set(z["pothole_time_split"]) == {0} and (z["pothole_geo_split"] >= -1).all()
        assert z["pothole_geo_split"][list(req.sr).index("M")] == -1  # M has no location


def test_boundary_loss_counts_the_duplicates_whose_parent_is_in_another_group():
    req = fx.requests()
    got = pairs.boundary_loss(req, fx.groups(req))
    # group 0 holds B, C, G and Q with their parents; N is in group 1 and its parent A is in group 0 (16 days earlier, 8 m away)
    assert got["train"]["children"] == 4 and got["train"]["kept"] == 4 and got["train"]["dropped"] == 0
    assert got["validation"]["children"] == 1 and got["validation"]["kept"] == 0 and got["validation"]["dropped"] == 1
    assert got["validation"]["median_gap_days_dropped"] == pytest.approx(16) and got["validation"]["share_inside_shipped_radius_dropped"] == 1.0
    assert got["validation"]["median_gap_days_kept"] is None and "test" not in got
    assert got["train"]["median_gap_days_kept"] == pytest.approx(1.0)  # gaps 1, 2, 1, 1 days


def test_the_block_summary_counts_blocks_and_located_requests_per_split():
    req = fx.requests()
    got = pairs.block_summary({"pothole": req}, prepare.geo_split({"pothole": req}))
    assert got["blocks"] == 1 and sum(got["blocks_per_split"].values()) == 1  # all 15 located fixture points share one 0.02-degree block
    assert sum(got["requests_per_split"].values()) == 15
